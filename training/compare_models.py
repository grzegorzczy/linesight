"""E6-08: porównanie modeli na dwóch testach i bramka jakości przed publikacją w rejestrze.

Testy (z części 'test' zbioru v2, rozdzielone po nazwie sesji z eksportu NDJSON):
  - test_old: 21 zdjęć z 10.11 (zamrożony test v1) – czy v2 nie zapomniał starej domeny,
  - test_new: 40 losowych zdjęć z capture.py w nowym świetle (16.11) – czy v2 jest lepszy tam, gdzie v1 się waha.
Oba modele liczymy w PyTorch (best.pt) przy conf=0.001, imgsz 640 – tak samo jak mAP w train.py.

Bramka (gate.json obok wag kandydata; registry.py publish dołącza ją do metrics.json, promote ją sprawdza):
  - test_old: mAP50-95 kandydata >= bazowy - 0,02   (tolerancja: 21 zdjęć to mała próba),
  - test_new: mAP50-95 kandydata >= bazowy + 0,02   (musi być realna poprawa, nie szum).

Uruchomienie (laptop, .venv):
  python training\\compare_models.py --data data\\datasets\\linesight_v2-c8f8f70f\\data.yaml --ndjson data\\export\\linesight_v2.ndjson --baseline v1 --candidate v2
"""
import argparse
import json
from pathlib import Path

import yaml
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "detect"
SUBSETS = {"test_old": lambda f: f.startswith("20261110_"), "test_new": lambda f: "newdomain_test" in f}
TOL_OLD = 0.02
MIN_GAIN_NEW = 0.02


def original_names(ndjson):
    """Platform nazywa pliki skrótem treści; oryginalną nazwę (z sesją) bierzemy z NDJSON."""
    out = {}
    with open(ndjson, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("type") == "image" and r.get("url"):
                out[Path(r["url"].split("?")[0]).stem] = r["file"]
    return out


def metrics(m, names):
    out = {"all": {"P": m.box.mp, "R": m.box.mr, "mAP50": m.box.map50, "mAP50-95": m.box.map}}
    for i, c in enumerate(m.box.ap_class_index):
        p, r, ap50, ap = m.box.class_result(i)
        out[names[int(c)]] = {"P": p, "R": r, "mAP50": ap50, "mAP50-95": ap}
    return {k: {kk: round(float(vv), 3) for kk, vv in v.items()} for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser(description="v1 vs v2 na starym i nowym teście + bramka")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--ndjson", type=Path, required=True)
    ap.add_argument("--baseline", default="v1")
    ap.add_argument("--candidate", default="v2")
    a = ap.parse_args()

    cfg = yaml.safe_load(a.data.read_text(encoding="utf-8"))
    root = Path(cfg.get("path") or a.data.parent)
    if not root.is_absolute():
        root = a.data.parent / root
    test_dir = root / cfg.get("test", "images/test")
    names_map = original_names(a.ndjson)
    out_dir = RUNS / "yolo26n_{}".format(a.candidate) / "compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    imgs = sorted(p for p in test_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    yamls = {}
    for sub, pick in SUBSETS.items():
        # pliki w zbiorze YOLO: <skrót>_<nr>.jpg, a w NDJSON adres kończy się na <skrót>.jpg
        chosen = [p for p in imgs if pick(names_map.get(p.stem.rsplit("_", 1)[0], ""))]
        lst = out_dir / "{}.txt".format(sub)
        lst.write_text("\n".join(str(p.resolve()) for p in chosen) + "\n", encoding="utf-8")
        y = out_dir / "{}.yaml".format(sub)
        y.write_text(yaml.safe_dump({"path": str(root.resolve()), "train": "images/train",
                                     "val": str(lst.resolve()), "names": cfg["names"]},
                                    allow_unicode=True), encoding="utf-8")
        yamls[sub] = (y, len(chosen))
        print("{}: {} zdjęć".format(sub, len(chosen)))
    if any(n == 0 for _, n in yamls.values()):
        raise SystemExit("Pusty podzbiór testowy – sprawdź --ndjson i nazwy sesji")

    res = {}
    for ver in (a.baseline, a.candidate):
        w = RUNS / "yolo26n_{}".format(ver) / "weights" / "best.pt"
        model = YOLO(str(w))
        for sub, (y, _) in yamls.items():
            m = model.val(data=str(y), split="val", imgsz=640, batch=16, conf=0.001, plots=False,
                          verbose=False, project=str(out_dir), name="{}_{}".format(ver, sub), exist_ok=True)
            res.setdefault(ver, {})[sub] = metrics(m, model.names)

    b, c = res[a.baseline], res[a.candidate]
    d_old = c["test_old"]["all"]["mAP50-95"] - b["test_old"]["all"]["mAP50-95"]
    d_new = c["test_new"]["all"]["mAP50-95"] - b["test_new"]["all"]["mAP50-95"]
    rules = {
        "test_old: nie gorzej niż -{:.2f} mAP50-95".format(TOL_OLD): d_old >= -TOL_OLD,
        "test_new: co najmniej +{:.2f} mAP50-95".format(MIN_GAIN_NEW): d_new >= MIN_GAIN_NEW,
    }
    gate = {"baseline": a.baseline, "candidate": a.candidate, "passed": all(rules.values()),
            "rules": rules, "delta": {"test_old": round(d_old, 3), "test_new": round(d_new, 3)},
            "n_images": {k: n for k, (_, n) in yamls.items()}, "results": res}
    (out_dir.parent / "gate.json").write_text(json.dumps(gate, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n{:<10} {:<8} {:>6} {:>6} {:>7} {:>9}".format("test", "model", "P", "R", "mAP50", "mAP50-95"))
    for sub in SUBSETS:
        for ver in (a.baseline, a.candidate):
            v = res[ver][sub]["all"]
            print("{:<10} {:<8} {:>6.3f} {:>6.3f} {:>7.3f} {:>9.3f}".format(sub, ver, v["P"], v["R"], v["mAP50"], v["mAP50-95"]))
    print("\ntest_new według klas (mAP50-95): " + "; ".join(
        "{} {} -> {}".format(k, b["test_new"].get(k, {}).get("mAP50-95"), c["test_new"][k]["mAP50-95"])
        for k in c["test_new"] if k != "all"))
    for r, ok in rules.items():
        print("[{}] {}".format("OK  " if ok else "BŁĄD", r))
    print("BRAMKA: {}  ->  {}".format("PRZESZŁA" if gate["passed"] else "NIE PRZESZŁA", out_dir.parent / "gate.json"))


if __name__ == "__main__":
    main()
