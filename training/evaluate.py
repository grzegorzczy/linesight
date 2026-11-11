"""E1-06: analiza wytrenowanego modelu – co, gdzie i dlaczego się myli.

Analizę robimy na VAL (na nim wolno podejmować decyzje). TEST ma jedną liczbę
w summary.json z train.py i nie dobieramy na nim niczego.

Kroki:
  1. val przy conf=0.001 (standard liczenia mAP): P, R, mAP na klasę, krzywe,
     czasy; z krzywej F1 wybieramy próg pewności (conf) do wdrożenia,
  2. val przy wybranym progu z visualize=True: obrazki TP / FP / FN, macierz pomyłek
     i metryki dla każdego zdjęcia -> lista najgorszych zdjęć (z nazwą sesji),
  3. mapy aktywacji (LayerCAM, predict visualize=True) dla najgorszych zdjęć
     i kilku losowych: gdzie sieć „patrzy”, podejmując decyzję,
  4. raport Markdown: runs/detect/<nazwa>/analysis/report.md.

Uruchomienie (laptop, folder projektu, aktywne .venv):
  python training\\evaluate.py                       # najnowszy przebieg
  python training\\evaluate.py --run runs\\detect\\yolo26n_v1
"""
import argparse
import json
import random
from pathlib import Path

import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "detect"
NDJSON = ROOT / "data" / "export" / "linesight.ndjson"
N_WORST = 8
N_RANDOM = 6
SEED = 42


def parse_args():
    p = argparse.ArgumentParser(description="Analiza modelu LineSight na zbiorze val")
    p.add_argument("--run", type=Path, default=None, help="folder przebiegu (domyślnie najnowszy z summary.json)")
    p.add_argument("--ndjson", type=Path, default=NDJSON, help="eksport z Platform (oryginalne nazwy zdjęć)")
    return p.parse_args()


def latest_run():
    runs = sorted(RUNS.glob("*/summary.json"), key=lambda f: f.stat().st_mtime)
    if not runs:
        raise SystemExit("Brak przebiegu z summary.json w {} – najpierw training\\train.py".format(RUNS))
    return runs[-1].parent


def original_names(ndjson):
    """Platform nazywa pliki skrótem treści; oryginalną nazwę z sesji bierzemy z NDJSON."""
    if not ndjson.is_file():
        return {}
    out = {}
    with open(ndjson, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("type") == "image" and r.get("url"):
                out[Path(r["url"].split("?")[0]).stem] = r["file"]
    return out


def per_class(m, names):
    rows = {"all": (m.box.mp, m.box.mr, m.box.map50, m.box.map)}
    for i, c in enumerate(m.box.ap_class_index):
        rows[names[int(c)]] = m.box.class_result(i)
    return rows


def md_table(rows):
    lines = ["| klasa | P | R | mAP50 | mAP50-95 |", "|---|---|---|---|---|"]
    for cls, v in rows.items():
        lines.append("| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(cls, *v))
    return lines


def best_conf(m, names):
    """Próg pewności z maksimum F1 (średnia po klasach) + F1 każdej klasy przy tym progu."""
    f1 = np.asarray(m.box.f1_curve)            # (klasy, 1000 progów)
    px = np.asarray(m.box.px)                  # progi 0..1
    i = int(f1.mean(0).argmax())
    per = {names[int(c)]: float(f1[k, i]) for k, c in enumerate(m.box.ap_class_index)}
    return float(px[i]), float(f1.mean(0)[i]), per


def main():
    args = parse_args()
    run = args.run.resolve() if args.run else latest_run()
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    data, best = summary["data"], run / "weights" / "best.pt"
    out = run / "analysis"
    model = YOLO(str(best))
    names = model.names
    orig = original_names(args.ndjson)

    def nice(img_name):
        stem = Path(img_name).stem.rsplit("_", 1)[0]
        return orig.get(stem, img_name)

    # 1. Metryki i próg pewności
    m = model.val(data=data, split="val", project=str(out), name="val_metrics", exist_ok=True, plots=True)
    rows = per_class(m, names)
    conf, f1, f1_per = best_conf(m, names)
    speed = m.speed

    # 2. Analiza błędów przy wybranym progu
    m2 = model.val(data=data, split="val", conf=conf, visualize=True, project=str(out),
                   name="val_errors", exist_ok=True, plots=True)
    img = m2.box.image_metrics
    worst = sorted(img.items(), key=lambda kv: (kv[1]["f1"], -(kv[1]["fp"] + kv[1]["fn"])))[:N_WORST]
    errors = {"fp": sum(v["fp"] for v in img.values()), "fn": sum(v["fn"] for v in img.values()),
              "tp": sum(v["tp"] for v in img.values())}

    # 3. Mapy aktywacji: najgorsze + losowe zdjęcia z val
    val_dir = Path(data).parent / "images" / "val"
    worst_paths = [val_dir / name for name, _ in worst]
    rest = sorted(p for p in val_dir.iterdir() if p not in worst_paths)
    picked = worst_paths + random.Random(SEED).sample(rest, min(N_RANDOM, len(rest)))
    model.predict(source=[str(p) for p in picked], conf=conf, visualize=True, save=True,
                  project=str(out), name="cam", exist_ok=True, verbose=False)

    # 4. Raport
    test = summary["test"]
    lines = [
        "# Analiza modelu: {}".format(run.name), "",
        "Wagi: `{}` · epoki: {} z {} · zbiór: `{}`".format(
            best.relative_to(ROOT), summary["epochs_run"], summary["epochs_max"], Path(data).parent.name), "",
        "## VAL (43 zdjęcia, conf=0.001)", "", *md_table(rows), "",
        "## TEST (21 zdjęć, jednorazowo – z train.py)", "",
        *md_table({k: (v["P"], v["R"], v["mAP50"], v["mAP50-95"]) for k, v in test.items()}), "",
        "## Próg pewności do wdrożenia", "",
        "Maksimum średniego F1 na val: **conf = {:.2f}** (F1 = {:.3f}).".format(conf, f1), "",
        "| klasa | F1 przy tym progu |", "|---|---|",
        *["| {} | {:.3f} |".format(k, v) for k, v in f1_per.items()], "",
        "Przy tym progu na val: TP = {tp}, FP = {fp} (fałszywe alarmy), FN = {fn} (przeoczenia).".format(**errors), "",
        "## Czasy na laptopie (ms na zdjęcie)", "",
        "preprocessing {preprocess:.1f} · inferencja {inference:.1f} · postprocessing {postprocess:.1f}".format(
            **{k: speed.get(k, 0.0) for k in ("preprocess", "inference", "postprocess")}), "",
        "## Najgorsze zdjęcia val (IoU 0.5, conf = {:.2f})".format(conf), "",
        "| zdjęcie | F1 | TP | FP | FN |", "|---|---|---|---|---|",
        *["| {} | {:.2f} | {} | {} | {} |".format(nice(n), v["f1"], v["tp"], v["fp"], v["fn"]) for n, v in worst], "",
        "## Pliki", "",
        "- `val_metrics/`: macierz pomyłek, krzywe PR / F1 / P / R, predykcje vs etykiety",
        "- `val_errors/`: obrazki TP / FP / FN dla każdego zdjęcia, macierz pomyłek przy progu conf",
        "- `cam/`: mapy aktywacji (`*_cam.jpg`) i predykcje dla {} najgorszych i {} losowych zdjęć".format(
            len(worst_paths), len(picked) - len(worst_paths)),
        "",
        "Mapowanie nazw w `cam/` (skrót -> oryginał): " + ", ".join(
            "{} -> {}".format(Path(p).stem, nice(Path(p).name)) for p in picked),
    ]
    report = out / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))
    print("\nRaport: {}".format(report))


if __name__ == "__main__":
    main()
