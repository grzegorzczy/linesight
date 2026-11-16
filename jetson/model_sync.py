#!/usr/bin/env python3
"""E6-05: synchronizacja modelu z rejestru w Cloud Storage (Jetson Nano, Python 3.6, TensorRT 8.2).

  python3 jetson/model_sync.py           sprawdź deployments/<urządzenie>.json; jeśli wskazuje inną wersję:
                                         pobierz ONNX, sprawdź sha256, zbuduj silnik FP16 (trtexec), test,
                                         przełącz models/current.engine
  python3 jetson/model_sync.py status    co jest wdrożone lokalnie i co wskazuje chmura
  python3 jetson/model_sync.py rollback  awaryjnie, bez sieci: wróć do poprzedniego silnika z dysku

Pliki (~/linesight/models/):
  registry/<model>/<wersja>/model.onnx, model_<H>x<W>_fp16.engine, build.log, test.log, meta.json
  current.engine  dowiązanie symboliczne do silnika wdrożonej wersji (czyta je DeepStream: nvinfer_yolo26.txt)
  current.json    co wdrożone + poprzednia wersja (do rollbacku)

Zasady:
  - silnik budujemy NA JETSONIE z ONNX (silnik TensorRT jest związany z GPU i wersją TensorRT, nie przenosi się),
  - przełączamy dopiero po udanym teście, atomowo (os.replace na dowiązaniu) – DeepStream nigdy nie widzi połowy,
  - nie budujemy, gdy działa linesight_app.py (4 GB RAM wspólne z GPU; budowa silnika potrzebuje ~1-1,5 GB),
  - powrót do wersji, która już jest na dysku, nie wymaga pobierania ani budowy (sprawdzamy sha256 w meta.json),
  - po przełączeniu trzeba zrestartować linesight_app.py (nvinfer ładuje silnik przy starcie).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gcs  # noqa: E402

DEVICE = os.environ.get("LINESIGHT_DEVICE", "jetson-01")
MODELS = os.path.expanduser("~/linesight/models")
STORE = os.path.join(MODELS, "registry")
CURRENT = os.path.join(MODELS, "current.engine")
STATE = os.path.join(MODELS, "current.json")
NVINFER_CFG = os.path.join(HERE, "..", "deepstream", "configs", "nvinfer_yolo26.txt")
TRTEXEC = "/usr/src/tensorrt/bin/trtexec"
MIN_QPS = 15.0   # bramka testu: silnik działa i nie jest drastycznie wolniejszy (v1: ~34 qps przy jetson_clocks)


def log(msg):
    print("[{}] {}".format(time.strftime("%H:%M:%S"), msg), flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (IOError, ValueError):
        return None


def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def app_running():
    return subprocess.run(["pgrep", "-f", "linesight_app.py"], stdout=subprocess.DEVNULL).returncode == 0


def engine_name(dep):
    h, w = dep["deploy"]["input_hw"]
    return "model_{}x{}_{}.engine".format(h, w, dep["deploy"]["precision"])


def build_and_test(vdir, dep):
    onnx_path = os.path.join(vdir, "model.onnx")
    engine = os.path.join(vdir, engine_name(dep))
    cmd = [TRTEXEC, "--onnx=" + onnx_path, "--saveEngine=" + engine,
           "--workspace={}".format(dep["deploy"]["workspace_mb"])]   # składnia TRT 8.2 (nowsze: --memPoolSize)
    if dep["deploy"]["precision"] == "fp16":
        cmd.append("--fp16")
    log("budowa silnika (kilka minut): " + " ".join(cmd[1:]))
    t0 = time.time()
    with open(os.path.join(vdir, "build.log"), "w") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=3600).returncode
    if rc != 0 or not os.path.isfile(engine):
        raise SystemExit("budowa nieudana (kod {}), log: {}".format(rc, os.path.join(vdir, "build.log")))
    log("silnik gotowy w {:.0f} s, {:.1f} MB".format(time.time() - t0, os.path.getsize(engine) / 1e6))

    # test: silnik się ładuje i liczy; przepustowość powyżej progu
    out = subprocess.run([TRTEXEC, "--loadEngine=" + engine, "--warmUp=1000", "--duration=5"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600).stdout.decode(errors="replace")
    with open(os.path.join(vdir, "test.log"), "w") as f:
        f.write(out)
    m = re.search(r"Throughput: ([\d.]+) qps", out)
    qps = float(m.group(1)) if m else 0.0
    if "&&&& PASSED" not in out or qps < MIN_QPS:
        raise SystemExit("test nieudany: {} qps (próg {}), log: {}".format(qps, MIN_QPS, os.path.join(vdir, "test.log")))
    log("test OK: {:.1f} qps".format(qps))
    return engine, qps


def switch(engine, state):
    """Atomowa podmiana dowiązania: nowe dowiązanie pod nazwą tymczasową, potem os.replace (rename(2))."""
    tmp = CURRENT + ".tmp"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(os.path.relpath(engine, MODELS), tmp)
    os.replace(tmp, CURRENT)
    save(STATE, state)


def check_conf(dep):
    with open(NVINFER_CFG) as f:
        m = re.search(r"^pre-cluster-threshold=([\d.]+)", f.read(), re.M)
    if m and abs(float(m.group(1)) - dep["deploy"]["conf"]) > 1e-6:
        log("UWAGA: conf w rejestrze {} ≠ pre-cluster-threshold {} w nvinfer_yolo26.txt".format(
            dep["deploy"]["conf"], m.group(1)))


def sync():
    dep = json.loads(gcs.get(gcs.MODELS, "deployments/{}.json".format(DEVICE)).decode())
    cur = load(STATE)
    want = "{}/{}".format(dep["model"], dep["version"])
    if cur and cur["sha256"] == dep["sha256"] and os.path.exists(CURRENT):
        log("aktualny: {} ({}) – nic do zrobienia".format(want, cur["sha256"][:12]))
        return 0
    log("chmura wskazuje {} (powód: {}), lokalnie {}".format(
        want, dep.get("reason") or "-", "{}/{}".format(cur["model"], cur["version"]) if cur else "brak"))

    vdir = os.path.join(STORE, dep["model"], dep["version"])
    os.makedirs(vdir, exist_ok=True)
    meta = load(os.path.join(vdir, "meta.json"))
    engine = os.path.join(vdir, engine_name(dep))
    if meta and meta["sha256"] == dep["sha256"] and os.path.isfile(engine):
        log("ta wersja jest już na dysku i przeszła test – bez pobierania i budowy")
        qps = meta.get("qps")
    else:
        if app_running():
            raise SystemExit("działa linesight_app.py – zatrzymaj go (Ctrl+C), budowa silnika potrzebuje RAM")
        onnx_path = os.path.join(vdir, "model.onnx")
        t0 = time.time()
        n = gcs.download(gcs.MODELS, dep["onnx"], onnx_path)
        log("pobrano {} ({:.1f} MB, {:.1f} s)".format(dep["onnx"], n / 1e6, time.time() - t0))
        got = sha256(onnx_path)
        if got != dep["sha256"]:
            os.remove(onnx_path)
            raise SystemExit("sha256 się nie zgadza: {} ≠ {} – plik usunięty".format(got[:12], dep["sha256"][:12]))
        log("sha256 zgodny")
        engine, qps = build_and_test(vdir, dep)
        save(os.path.join(vdir, "meta.json"), {"sha256": dep["sha256"], "qps": qps, "built": time.strftime("%Y-%m-%dT%H:%M:%S")})

    state = {k: dep[k] for k in ("model", "version", "sha256", "deploy")}
    state.update(engine=os.path.relpath(engine, MODELS), qps=qps, synced=time.strftime("%Y-%m-%dT%H:%M:%S"),
                 previous=cur and {k: v for k, v in cur.items() if k != "previous"})
    switch(engine, state)
    check_conf(dep)
    log("PRZEŁĄCZONO current.engine -> {}; zrestartuj linesight_app.py".format(state["engine"]))
    return 0


def rollback():
    cur = load(STATE)
    prev = cur and cur.get("previous")
    if not prev or not os.path.isfile(os.path.join(MODELS, prev["engine"])):
        raise SystemExit("brak poprzedniego silnika na dysku")
    new = dict(prev, previous={k: v for k, v in cur.items() if k != "previous"},
               synced=time.strftime("%Y-%m-%dT%H:%M:%S"))
    switch(os.path.join(MODELS, prev["engine"]), new)
    log("ROLLBACK: {}/{} -> {}/{}; zrestartuj linesight_app.py".format(
        cur["model"], cur["version"], prev["model"], prev["version"]))
    log("chmura dalej wskazuje nowszą wersję – następny sync ją przywróci; trwały rollback: "
        "registry.py promote --version {} na laptopie".format(prev["version"]))


def status():
    cur = load(STATE)
    link = os.readlink(CURRENT) if os.path.islink(CURRENT) else None
    print("lokalnie:  {}  current.engine -> {}".format(
        "{}/{} ({} qps, {})".format(cur["model"], cur["version"], cur.get("qps"), cur["synced"]) if cur else "brak", link))
    print("poprzednia: {}".format("{}/{}".format(cur["previous"]["model"], cur["previous"]["version"])
                                 if cur and cur.get("previous") else "brak"))
    dep = json.loads(gcs.get(gcs.MODELS, "deployments/{}.json".format(DEVICE)).decode())
    print("chmura:    {}/{} (wskazana {})".format(dep["model"], dep["version"], dep["promoted"]))


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "sync"
    sys.exit({"sync": sync, "status": status, "rollback": rollback}[arg]() or 0)
