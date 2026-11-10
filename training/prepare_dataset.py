"""E1-04 -> E1-06: zbiór z Ultralytics Platform (NDJSON) -> foldery YOLO na laptopie + kontrola.

Platform eksportuje zbiór jako plik NDJSON: pierwsza linia to opis zbioru (klasy),
kolejne – po jednej linii na zdjęcie (plik, podział, ramki, link do pobrania).
Funkcja convert_ndjson_to_yolo z ultralytics pobiera zdjęcia i zapisuje je w układzie:

  data/datasets/<nazwa>-<hash>/
    data.yaml                 <- ścieżka do podania przy treningu
    images/{train,val,test}/
    labels/{train,val,test}/  <- jeden .txt na zdjęcie: "klasa x y w h" (0-1)

Potem skrypt sprawdza zbiór:
  - liczba zdjęć, zdjęć z ramkami i ramek na klasę w każdej części,
  - zgodność z zamrożonym podziałem training/splits/split_v1.csv,
  - zdjęcia bez ramek spoza sesji 'empty' (zapomniane etykiety).

Uruchomienie (laptop, folder projektu, aktywne .venv):
  python training\\prepare_dataset.py data\\export\\linesight.ndjson
"""
import argparse
import asyncio
import csv
from collections import Counter
from pathlib import Path

from ultralytics.data.converter import convert_ndjson_to_yolo
from ultralytics.utils import YAML

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets"
SPLIT_CSV = ROOT / "training" / "splits" / "split_v1.csv"
SPLITS = ("train", "val", "test")


def read_labels(label_file):
    """Lista ID klas z pliku etykiet YOLO (pusty lub brak pliku = zdjęcie bez obiektów)."""
    if not label_file.is_file():
        return []
    return [int(line.split()[0]) for line in label_file.read_text().splitlines() if line.strip()]


def main():
    p = argparse.ArgumentParser(description="NDJSON z Ultralytics Platform -> foldery YOLO + kontrola")
    p.add_argument("ndjson", type=Path, help="plik .ndjson pobrany z Platform")
    args = p.parse_args()

    yaml_path = Path(asyncio.run(convert_ndjson_to_yolo(args.ndjson, output_path=OUT)))
    ds = yaml_path.parent
    names = YAML.load(yaml_path)["names"]
    print("\nZbiór: {}\nKlasy: {}\n".format(ds, names))

    # 1. Liczby w każdej części
    exported = {}            # nazwa pliku -> podział
    unlabeled = []
    header = "{:<6} {:>7} {:>11}".format("część", "zdjęcia", "z ramkami") + "".join(
        " {:>12}".format(names[i]) for i in sorted(names))
    print(header)
    total = Counter()
    for split in SPLITS:
        img_dir = ds / "images" / split
        if not img_dir.is_dir():
            continue
        images = sorted(f for f in img_dir.iterdir() if f.is_file())
        classes = Counter()
        labeled = 0
        for img in images:
            exported[img.name] = split
            ids = read_labels(ds / "labels" / split / (img.stem + ".txt"))
            if ids:
                labeled += 1
                classes.update(ids)
            elif "_empty_" not in img.name:
                unlabeled.append("{}/{}".format(split, img.name))
        total.update(classes)
        total["_images"] += len(images)
        total["_labeled"] += labeled
        print("{:<6} {:>7} {:>11}".format(split, len(images), labeled) + "".join(
            " {:>12}".format(classes[i]) for i in sorted(names)))
    print("{:<6} {:>7} {:>11}".format("razem", total["_images"], total["_labeled"]) + "".join(
        " {:>12}".format(total[i]) for i in sorted(names)))

    # 2. Zgodność z zamrożonym podziałem
    if SPLIT_CSV.is_file():
        with open(SPLIT_CSV, encoding="utf-8") as fh:
            planned = {row["file"]: row["split"] for row in csv.DictReader(fh)}
        missing = sorted(f for f in planned if f not in exported)
        extra = sorted(f for f in exported if f not in planned)
        moved = sorted(f for f in planned if f in exported and exported[f] != planned[f])
        print("\nPodział vs {}:".format(SPLIT_CSV.name))
        print("  brak w eksporcie : {}".format(
            ", ".join("{} ({})".format(f, planned[f]) for f in missing) or "-"))
        print("  spoza podziału   : {}".format(", ".join(extra) or "-"))
        print("  w innej części   : {}".format(
            ", ".join("{} ({} -> {})".format(f, planned[f], exported[f]) for f in moved) or "-"))

    # 3. Zapomniane etykiety
    print("\nBez ramek spoza sesji 'empty': {}".format(", ".join(unlabeled) or "-"))
    print("\nDo treningu: data={}".format(yaml_path))


if __name__ == "__main__":
    main()
