#!/usr/bin/env python3
"""E6-06: wysyłka niepewnych klatek z Jetsona do gs://linesight-514914-frames (Python 3.6, klient gcs.py).

Osobny proces, nie wątek w linesight_app.py: sieć (timeouty, brak tokenu) nie może blokować potoku wideo,
a klatki czekające na dysku przeżywają restart aplikacji i brak internetu.

  python3 jetson/upload_frames.py          pętla: co 30 s wysyła kompletne pary .jpg + .json
  python3 jetson/upload_frames.py --once   jeden przebieg (test)

Obiekty: <urządzenie>/<RRRR-MM-DD>/<nazwa>.jpg i .json (JSON wysyłany drugi – w chmurze para kompletna, gdy jest
JSON). Po wysyłce pliki lokalne idą do <dir>/sent/ (zostają do ręcznego sprzątnięcia; w chmurze reguła 30 dni).
412 (obiekt już jest – np. przerwa po wysłaniu, przed przeniesieniem) traktujemy jak sukces: niczego nie nadpisujemy.
"""
import argparse
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs  # noqa: E402

DEVICE = os.environ.get("LINESIGHT_DEVICE", "jetson-01")


def log(msg):
    print("[{}] {}".format(time.strftime("%H:%M:%S"), msg), flush=True)


def put(local, name, ctype):
    with open(local, "rb") as f:
        data = f.read()
    try:
        gcs.upload(gcs.FRAMES, name, data, ctype)
    except gcs.GcsError as e:
        if e.code != 412:
            raise
    return len(data)


def run_once(root):
    pending = sorted(p for p in glob.glob(os.path.join(root, "2*", "*.json")))
    sent = n_bytes = 0
    for js in pending:
        base = js[:-5]
        day_dir = os.path.basename(os.path.dirname(js))          # RRRRMMDD
        day = "{}-{}-{}".format(day_dir[:4], day_dir[4:6], day_dir[6:])
        name = "{}/{}/{}".format(DEVICE, day, os.path.basename(base))
        try:
            n_bytes += put(base + ".jpg", name + ".jpg", "image/jpeg")
            n_bytes += put(js, name + ".json", "application/json")
        except (gcs.GcsError, OSError) as e:   # OSError: brak sieci / brokera; spróbujemy w następnym przebiegu
            log("przerwano na {}: {}".format(os.path.basename(base), e))
            break
        dest = os.path.join(root, "sent", day_dir)
        os.makedirs(dest, exist_ok=True)
        for ext in (".jpg", ".json"):
            os.replace(base + ext, os.path.join(dest, os.path.basename(base) + ext))
        sent += 1
    if pending:
        log("wysłano {}/{} par ({:.1f} MB) do gs://{}/{}/".format(sent, len(pending), n_bytes / 1e6, gcs.FRAMES, DEVICE))
    return sent, len(pending)


def main():
    ap = argparse.ArgumentParser(description="Wysyłka niepewnych klatek do Cloud Storage")
    ap.add_argument("--dir", default=os.path.expanduser("~/linesight_uncertain"))
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if a.once:
        run_once(a.dir)
        return
    log("wysyłka z {} co {} s (Ctrl+C kończy)".format(a.dir, a.interval))
    while True:
        try:
            run_once(a.dir)
        except Exception as e:   # pętla ma przeżyć każdy błąd – spróbuje znowu za chwilę
            log("błąd: {}".format(e))
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
