"""E6-04: rejestr wersji modelu w Cloud Storage (laptop, .venv, ADC użytkownika).

Układ w gs://linesight-514914-models:
  <model>/<wersja>/model.onnx          plik ONNX (niezmienny – zapis tylko, gdy nie istnieje)
  <model>/<wersja>/metrics.json        metryki, sha256, commit, zbiór, parametry wdrożenia; zapisywany OSTATNI,
                                       więc jego obecność = wersja kompletna (opublikowana)
  deployments/<urządzenie>.json        którą wersję ma uruchomić urządzenie (+ poprzednia, do rollbacku)

Komendy (folder projektu, aktywne .venv):
  python cloud\\registry.py publish --version v1 --onnx models\\yolo26n_v1_384x640.onnx --run runs\\detect\\yolo26n_v1
  python cloud\\registry.py list
  python cloud\\registry.py promote --version v1 --device jetson-01
  python cloud\\registry.py show --device jetson-01
"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import onnx
import yaml
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage

PROJECT = "linesight-514914"
BUCKET = "linesight-514914-models"
ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit():
    """Commit kodu, z którego publikujemy; '+dirty', gdy są niezacommitowane zmiany w śledzonych plikach."""
    run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    commit = run("rev-parse", "--short", "HEAD") or "unknown"
    return commit + ("+dirty" if run("status", "--porcelain", "--untracked-files=no") else "")


def onnx_info(path):
    m = onnx.load(str(path))
    shape = lambda vi: [d.dim_value or d.dim_param for d in vi.type.tensor_type.shape.dim]
    return {
        "opset": max(o.version for o in m.opset_import if o.domain in ("", "ai.onnx")),
        "inputs": {i.name: shape(i) for i in m.graph.input},
        "outputs": {o.name: shape(o) for o in m.graph.output},
    }


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def bucket():
    return storage.Client(project=PROJECT).bucket(BUCKET)


def read_json(b, name):
    try:
        return json.loads(b.blob(name).download_as_bytes())
    except NotFound:
        return None


def cmd_publish(a):
    b = bucket()
    prefix = "{}/{}/".format(a.model, a.version)
    if b.blob(prefix + "metrics.json").exists():
        raise SystemExit("{} już opublikowana – wersje są niezmienne, użyj nowej (np. v2)".format(prefix))

    summary = json.loads((a.run / "summary.json").read_text(encoding="utf-8"))
    data_yaml = Path(summary["data"])
    names = yaml.safe_load(data_yaml.read_text(encoding="utf-8")).get("names") if data_yaml.is_file() else None
    digest = sha256(a.onnx)
    info = onnx_info(a.onnx)
    inp = next(iter(info["inputs"].values()))   # [1, 3, H, W]

    meta = {
        "model": a.model,
        "version": a.version,
        "created": now(),
        "git_commit": git_commit(),
        "notes": a.notes,
        "onnx": dict(object=prefix + "model.onnx", sha256=digest, bytes=a.onnx.stat().st_size,
                     source_file=a.onnx.name, **info),
        "deploy": {"input_hw": [inp[2], inp[3]], "precision": "fp16", "workspace_mb": 2048, "conf": a.conf},
        "names": names,
        "dataset": {"id": data_yaml.parent.name, "split": a.split},
        "train": {k: summary.get(k) for k in ("model_start", "epochs_run", "imgsz", "batch", "seed")},
        "metrics": {"val": summary.get("val"), "test": summary.get("test")},
    }

    blob = b.blob(prefix + "model.onnx")
    blob.metadata = {"sha256": digest}
    try:
        blob.upload_from_filename(str(a.onnx), content_type="application/octet-stream", if_generation_match=0)
        print("wysłano  gs://{}/{}  ({:.1f} MB)".format(BUCKET, blob.name, a.onnx.stat().st_size / 1e6))
    except PreconditionFailed:   # przerwana publikacja: ONNX jest, metrics.json nie – wznawiamy, jeśli to ten sam plik
        blob.reload()
        if (blob.metadata or {}).get("sha256") != digest:
            raise SystemExit("{} istnieje i ma inny sha256 – nie nadpisuję".format(blob.name))
        print("ONNX już w rejestrze (ten sam sha256) – dopisuję metrics.json")
    b.blob(prefix + "metrics.json").upload_from_string(
        json.dumps(meta, indent=2, ensure_ascii=False), content_type="application/json", if_generation_match=0)
    t = meta["metrics"]["test"]["all"]
    print("opublikowano {}  sha256 {}…  test mAP50 {}  mAP50-95 {}".format(
        prefix, digest[:12], t["mAP50"], t["mAP50-95"]))


def versions(b, model):
    out = []
    for blob in b.list_blobs(prefix=model + "/"):
        if blob.name.endswith("/metrics.json"):
            out.append(json.loads(blob.download_as_bytes()))
    return sorted(out, key=lambda m: m["created"])


def cmd_list(a):
    b = bucket()
    deployed = {}
    for blob in b.list_blobs(prefix="deployments/"):
        d = json.loads(blob.download_as_bytes())
        deployed.setdefault(d["version"], []).append(Path(blob.name).stem)
    print("{:<8} {:<20} {:<12} {:>9} {:>11}  {}".format("wersja", "utworzona", "commit", "test mAP50", "mAP50-95", "wdrożona na"))
    for m in versions(b, a.model):
        t = m["metrics"]["test"]["all"]
        print("{:<8} {:<20} {:<12} {:>9.3f} {:>11.3f}  {}".format(
            m["version"], m["created"][:19], m["git_commit"], t["mAP50"], t["mAP50-95"],
            ", ".join(deployed.get(m["version"], [])) or "-"))


def cmd_promote(a):
    b = bucket()
    meta = read_json(b, "{}/{}/metrics.json".format(a.model, a.version))
    if meta is None:
        raise SystemExit("{}/{} nie jest opublikowana (brak metrics.json)".format(a.model, a.version))
    name = "deployments/{}.json".format(a.device)
    current = read_json(b, name)
    if current and current["version"] == a.version:
        raise SystemExit("{} już ma {}".format(a.device, a.version))
    dep = {
        "device": a.device,
        "model": a.model,
        "version": a.version,
        "onnx": meta["onnx"]["object"],
        "sha256": meta["onnx"]["sha256"],
        "deploy": meta["deploy"],
        "promoted": now(),
        "reason": a.reason,
        "previous": current and {k: current[k] for k in ("model", "version", "onnx", "sha256", "deploy")},
    }
    b.blob(name).upload_from_string(json.dumps(dep, indent=2), content_type="application/json")
    print("{}: {} -> {}".format(a.device, current["version"] if current else "(brak)", a.version))


def cmd_show(a):
    print(json.dumps(read_json(bucket(), "deployments/{}.json".format(a.device)), indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="Rejestr modeli LineSight w Cloud Storage")
    p.add_argument("--model", default="yolo26n")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("publish", help="wyślij nową wersję (ONNX + metrics.json)")
    s.add_argument("--version", required=True)
    s.add_argument("--onnx", type=Path, required=True)
    s.add_argument("--run", type=Path, required=True, help="runs\\detect\\<przebieg> z summary.json")
    s.add_argument("--conf", type=float, default=0.45, help="próg pewności do wdrożenia")
    s.add_argument("--split", default="training/splits/split_v1.csv")
    s.add_argument("--notes", default="")
    sub.add_parser("list", help="wersje z metrykami i wdrożeniami")
    s = sub.add_parser("promote", help="wskaż wersję dla urządzenia")
    s.add_argument("--version", required=True)
    s.add_argument("--device", default="jetson-01")
    s.add_argument("--reason", default="")
    s = sub.add_parser("show", help="aktualne wskazanie dla urządzenia")
    s.add_argument("--device", default="jetson-01")
    a = p.parse_args()
    {"publish": cmd_publish, "list": cmd_list, "promote": cmd_promote, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
