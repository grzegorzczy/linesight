"""E1-06: trening detektora YOLO26n na laptopie + ocena na zamrożonym zbiorze testowym.

Co robi:
  1. trening od wag COCO (transfer learning) na naszym zbiorze, ocena na val co epokę,
     zapis najlepszych wag (best.pt) według mAP50-95 na val,
  2. ocena best.pt na val i – jeden raz – na test (zdjęcia, których model nie widział),
  3. wyniki w runs/detect/<nazwa>/summary.json + wykresy i macierze pomyłek.

Stałe ziarno i deterministic=True – ten sam trening da (prawie) te same liczby.

Uruchomienie (laptop, folder projektu, aktywne .venv):
  python training\\train.py
  python training\\train.py --epochs 150 --name yolo26n_v1_e150
"""
import argparse
import json
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "data" / "datasets"
RUNS = ROOT / "runs" / "detect"
SEED = 42


def parse_args():
    p = argparse.ArgumentParser(description="Trening YOLO26n na zbiorze LineSight")
    p.add_argument("--data", type=Path, default=None,
                   help="data.yaml (domyślnie: najnowszy data/datasets/linesight-*/data.yaml)")
    p.add_argument("--model", default="yolo26n.pt", help="wagi startowe (COCO)")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--patience", type=int, default=30,
                   help="stop, gdy mAP na val nie rośnie przez tyle epok")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--name", default="yolo26n_v1", help="nazwa przebiegu w runs/detect/")
    return p.parse_args()


def latest_data_yaml():
    yamls = sorted(DATASETS.glob("linesight-*/data.yaml"), key=lambda f: f.stat().st_mtime)
    if not yamls:
        raise SystemExit("Brak zbioru w {} – najpierw training\\prepare_dataset.py".format(DATASETS))
    return yamls[-1]


def metrics_dict(m, names):
    """Precision, recall, mAP50, mAP50-95: średnio i dla każdej klasy."""
    out = {"all": {"P": m.box.mp, "R": m.box.mr, "mAP50": m.box.map50, "mAP50-95": m.box.map}}
    for i, c in enumerate(m.box.ap_class_index):
        p, r, ap50, ap = m.box.class_result(i)
        out[names[int(c)]] = {"P": p, "R": r, "mAP50": ap50, "mAP50-95": ap}
    return {k: {kk: round(float(vv), 3) for kk, vv in v.items()} for k, v in out.items()}


def print_table(title, table):
    print("\n{}".format(title))
    print("{:<12} {:>6} {:>6} {:>7} {:>9}".format("klasa", "P", "R", "mAP50", "mAP50-95"))
    for cls, v in table.items():
        print("{:<12} {:>6.3f} {:>6.3f} {:>7.3f} {:>9.3f}".format(
            cls, v["P"], v["R"], v["mAP50"], v["mAP50-95"]))


def main():
    args = parse_args()
    data = args.data or latest_data_yaml()
    print("Zbiór: {}".format(data))

    # 1. Trening
    model = YOLO(args.model)
    model.train(
        data=str(data),
        epochs=args.epochs,
        patience=args.patience,
        imgsz=args.imgsz,
        batch=args.batch,
        seed=SEED,
        deterministic=True,
        workers=4,                      # Windows: mniej procesów ładujących = mniej RAM
        project=str(RUNS),
        name=args.name,
        exist_ok=False,                 # nie nadpisujemy poprzedniego przebiegu
        plots=True,
    )
    save_dir = Path(model.trainer.save_dir)
    best = save_dir / "weights" / "best.pt"

    # 2. Ocena najlepszych wag: val, potem jeden raz test
    best_model = YOLO(str(best))
    names = best_model.names
    common = dict(data=str(data), imgsz=args.imgsz, batch=args.batch, project=str(save_dir), plots=True)
    val = metrics_dict(best_model.val(split="val", name="eval_val", **common), names)
    test = metrics_dict(best_model.val(split="test", name="eval_test", **common), names)

    # 3. Podsumowanie
    summary = {
        "model_start": args.model,
        "data": str(data),
        "epochs_max": args.epochs,
        "epochs_run": model.trainer.epoch + 1,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "seed": SEED,
        "best_weights": str(best),
        "val": val,
        "test": test,
    }
    (save_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print_table("VAL (43 zdjęcia, best.pt)", val)
    print_table("TEST (21 zdjęć, jednorazowo)", test)
    print("\nEpoki: {} z {}".format(summary["epochs_run"], args.epochs))
    print("Wagi: {}".format(best))
    print("Wyniki: {}".format(save_dir))


if __name__ == "__main__":        # Windows: wymagane przez procesy ładujące dane
    main()
