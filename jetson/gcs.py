#!/usr/bin/env python3
"""E6-03: minimalny klient Cloud Storage dla Jetsona (Python 3.6, tylko biblioteka standardowa).

Token OAuth (1 h) pobieramy z brokera na laptopie (cloud/token_broker.py), który podszywa się pod konto usługi
jetson-edge. Z Cloud Storage rozmawiamy bezpośrednio przez JSON API (REST):
  pobranie:  GET  https://storage.googleapis.com/storage/v1/b/<bucket>/o/<obiekt>?alt=media
  lista:     GET  https://storage.googleapis.com/storage/v1/b/<bucket>/o?prefix=...
  wysyłka:   POST https://storage.googleapis.com/upload/storage/v1/b/<bucket>/o?uploadType=media&name=...
             z ifGenerationMatch=0 – zapis tylko, gdy obiekt o tej nazwie jeszcze nie istnieje (bez nadpisywania).
Dlaczego bez google-cloud-storage: ostatnia wersja dla Pythona 3.6 (2.0.0) jest z 2022 r. i ciągnie protobuf/api-core;
trzy wywołania REST są prostsze i niczego nie instalujemy.

Konfiguracja (zmienne środowiskowe):
  LINESIGHT_BROKER  adres brokera, domyślnie http://192.168.0.203:8010
  LINESIGHT_BROKER_SECRET  sekret; albo plik ~/.config/linesight/broker_secret (chmod 600)

Test uprawnień:  python3 ~/linesight/jetson/gcs.py selftest
"""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BROKER = os.environ.get("LINESIGHT_BROKER", "http://192.168.0.203:8010")
API = "https://storage.googleapis.com/storage/v1"
UPLOAD = "https://storage.googleapis.com/upload/storage/v1"
MODELS = "linesight-514914-models"
FRAMES = "linesight-514914-frames"
SECRET_FILE = os.path.expanduser("~/.config/linesight/broker_secret")

_token = {"value": None, "until": 0.0}


class GcsError(Exception):
    def __init__(self, code, body):
        super().__init__("HTTP {}: {}".format(code, body[:200]))
        self.code = code


def _secret():
    s = os.environ.get("LINESIGHT_BROKER_SECRET")
    if s:
        return s.strip()
    with open(SECRET_FILE) as f:
        return f.read().strip()


def token():
    """Token z pamięci procesu; nowy z brokera, gdy zostało < 5 min ważności."""
    if _token["value"] and time.time() < _token["until"] - 300:
        return _token["value"]
    req = urllib.request.Request(BROKER + "/token", headers={"Authorization": "Bearer " + _secret()})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode())
    _token.update(value=d["access_token"], until=time.time() + d["expires_in"])
    return _token["value"]


def _call(method, url, data=None, headers=None, timeout=60):
    h = {"Authorization": "Bearer " + token()}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise GcsError(e.code, e.read().decode(errors="replace"))


def _obj(name):
    return urllib.parse.quote(name, safe="")   # "a/b.onnx" -> "a%2Fb.onnx" (nazwa obiektu w ścieżce URL)


def list_names(bucket, prefix=""):
    url = "{}/b/{}/o?fields=items(name,size,md5Hash)&prefix={}".format(API, bucket, urllib.parse.quote(prefix))
    return [i["name"] for i in json.loads(_call("GET", url).decode()).get("items", [])]


def get(bucket, name, timeout=300):
    """Zawartość obiektu w pamięci (małe pliki: JSON, ONNX ~10 MB)."""
    return _call("GET", "{}/b/{}/o/{}?alt=media".format(API, bucket, _obj(name)), timeout=timeout)


def download(bucket, name, dest):
    """Pobranie do pliku tymczasowego i zamiana nazwy – przerwane pobieranie nie zostawia połowy pliku pod dest."""
    data = get(bucket, name)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return len(data)


def upload(bucket, name, data, content_type="application/octet-stream"):
    """Tworzy obiekt; 412, gdy taki już istnieje (ifGenerationMatch=0 – nigdy nie nadpisujemy)."""
    url = "{}/b/{}/o?uploadType=media&ifGenerationMatch=0&name={}".format(
        UPLOAD, bucket, urllib.parse.quote(name, safe=""))
    return json.loads(_call("POST", url, data=data, headers={"Content-Type": content_type}).decode())


def delete(bucket, name):
    _call("DELETE", "{}/b/{}/o/{}".format(API, bucket, _obj(name)))


def _expect(label, fn, want):
    """want = 'ok', kod HTTP (np. 403) albo krotka dopuszczalnych kodów."""
    try:
        res = fn()
        got = "ok"
    except GcsError as e:
        res, got = None, e.code
    good = got in want if isinstance(want, tuple) else got == want
    shown = "/".join(map(str, want)) if isinstance(want, tuple) else want
    print("[{}] {:<52} oczekiwane {:<7} jest {}".format("OK  " if good else "BŁĄD", label, shown, got))
    return good, res


def selftest():
    t0 = time.time()
    token()
    print("token z {} w {:.2f} s".format(BROKER, time.time() - t0))
    name = "selftest/{}-{}.txt".format(socket.gethostname(), time.strftime("%Y%m%d-%H%M%S"))
    body = "selftest z Jetsona\n".encode()
    results = [
        _expect("lista models/selftest/", lambda: list_names(MODELS, "selftest/"), "ok"),
        _expect("pobranie models/selftest/hello.txt", lambda: download(MODELS, "selftest/hello.txt", "/tmp/hello.txt"), "ok"),
        _expect("wysłanie frames/" + name, lambda: upload(FRAMES, name, body, "text/plain"), "ok"),
        _expect("ponowne wysłanie tej samej nazwy (nadpisanie)", lambda: upload(FRAMES, name, body, "text/plain"), (403, 412)),
        _expect("odczyt z frames", lambda: download(FRAMES, name, "/tmp/frame.txt"), 403),
        _expect("lista frames", lambda: list_names(FRAMES), 403),
        _expect("usunięcie z frames", lambda: delete(FRAMES, name), 403),
        _expect("wysłanie do models (podmiana modelu)", lambda: upload(MODELS, "selftest/x.txt", body), 403),
    ]
    ok = all(r[0] for r in results)
    print("WYNIK: {}".format("wszystko zgodne z uprawnieniami" if ok else "są niezgodności"))
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        sys.exit(selftest())
    print(__doc__)
