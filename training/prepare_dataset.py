"""E1-04 -> E1-06: zbiór z Ultralytics Platform (NDJSON) -> foldery YOLO na laptopie + kontrola.

Platform eksportuje zbiór jako plik NDJSON: pierwsza linia to opis zbioru (klasy),
kolejne – po jednej linii na zdjęcie: oryginalna nazwa pliku, podział, ramki, link.
Funkcja convert_ndjson_to_yolo z ultralytics pobiera zdjęcia i zapisuje je w układzie:

  data/datasets/<nazwa>-<hash>/
    data.yaml                 <- ścieżka do podania przy treningu
    images/{train,val,test}/  <- nazwy plików = skrót treści (hash) z Platform
    labels/{train,val,test}/  <- jeden .txt na zdjęcie: "klasa x y w h" (0-1)

Kontrolę robimy na rekordach NDJSON (tam są oryginalne nazwy z sesji):
  - liczba zdjęć, zdjęć z ramkami i ramek na klasę w każdej części,
  - zgodność z zamrożonym podziałem training/splits/split_v1.csv,
  - zdjęcia bez ramek spoza sesji 'empty' (zapomniane etykiety).

Uruchomienie (laptop, folder projektu, aktywne .venv):
  python training\\prepare_dataset.py data\\export\\linesight.ndjson
"""
import argparse
import asyncio
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from ultralytics.data.converter import convert_ndjson_to_yolo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets"
SPLIT_CSV = ROOT / "training" / "splits" / "split_v1.csv"
SPLITS = ("train", "val", "test")


def read_ndjson(path):
    with open(path, encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh if line.strip()]
    names = {int(k): v for k, v in lines[0].get("class_names", {}).items()}
    return names, lines[1:]


def report(names, records):
    stats = defaultdict(Counter)
    unlabeled = []
    for r in records:
        boxes = r.get("annotations", {}).get("boxes", [])
        s = stats[r["split"]]
        s["_images"] += 1
        if boxes:
            s["_labeled"] += 1
        elif "_empty_" not in r["file"]:
            unlabeled.append("{} ({})".format(r["file"], r["split"]))
        s.update(int(b[0]) for b in boxes)

    cols = ["_images", "_labeled"] + sorted(names)
    head = ["zdjęcia", "z ramkami"] + [names[i] for i in sorted(names)]
    print("{:<6}".format("część") + "".join(" {:>12}".format(h) for h in head))
    total = Counter()
    for split in SPLITS:
        total.update(stats[split])
        print("{:<6}".format(split) + "".join(" {:>12}".format(stats[split][c]) for c in cols))
    print("{:<6}".format("razem") + "".join(" {:>12}".format(total[c]) for c in cols))
    return unlabeled


def compare_split(records):
    if not SPLIT_CSV.is_file():
        print("\nBrak {} – pomijam porównanie podziału".format(SPLIT_CSV))
        return
    with open(SPLIT_CSV, encoding="utf-8") as fh:
        planned = {row["file"]: row["split"] for row in csv.DictReader(fh)}
    exported = {r["file"]: r["split"] for r in records}
    missing = sorted(f for f in planned if f not in exported)
    extra = sorted(f for f in exported if f not in planned)
    moved = sorted(f for f in planned if f in exported and exported[f] != planned[f])
    print("\nPodział vs {}:".format(SPLIT_CSV.name))
    print("  brak w eksporcie : {}".format(
        ", ".join("{} ({})".format(f, planned[f]) for f in missing) or "-"))
    print("  spoza podziału   : {}".format(", ".join(extra) or "-"))
    print("  w innej części   : {}".format(
        ", ".join("{} ({} -> {})".format(f, planned[f], exported[f]) for f in moved) or "-"))


def main():
    p = argparse.ArgumentParser(description="NDJSON z Ultralytics Platform -> foldery YOLO + kontrola")
    p.add_argument("ndjson", type=Path, help="plik .ndjson pobrany z Platform")
    args = p.parse_args()

    names, records = read_ndjson(args.ndjson)
    print("Klasy: {}\n".format(names))
    unlabeled = report(names, records)
    compare_split(records)
    print("\nBez ramek spoza sesji 'empty': {}".format(", ".join(unlabeled) or "-"))

    yaml_path = Path(asyncio.run(convert_ndjson_to_yolo(args.ndjson, output_path=OUT)))
    print("\nDo treningu: data={}".format(yaml_path))


if __name__ == "__main__":
    main()
