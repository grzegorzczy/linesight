"""E1-04: paczka zdjęć do wgrania na Ultralytics Platform z ustalonym podziałem.

Podział train/val/test robimy sami, przed etykietowaniem:
  - warstwowo po sesjach (bottle, missing_cap, fallen, mixed, empty) – każda
    część zbioru ma zdjęcia z każdej sesji w tych samych proporcjach,
  - ze stałym ziarnem losowania – podział da się odtworzyć,
  - zapisany w training/splits/split_<wersja>.csv (w repozytorium) – zbiór
    testowy jest zamrożony i nie zmienia się między treningami.

Platform zachowuje podział z folderów train/ val/ test/ w paczce ZIP.

Uruchomienie (laptop, folder projektu, aktywne .venv):
  python training\\make_upload_zip.py
"""
import argparse
import csv
import random
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "upload"
SPLITS_DIR = ROOT / "training" / "splits"

VAL_FRAC = 0.2
TEST_FRAC = 0.1
SEED = 42


def split_session(files, rng):
    """Dzieli zdjęcia jednej sesji: ok. 70% train, 20% val, 10% test (min. 1 w val i test)."""
    files = sorted(files)
    rng.shuffle(files)
    n = len(files)
    n_test = max(1, round(n * TEST_FRAC))
    n_val = max(1, round(n * VAL_FRAC))
    return {
        "test": files[:n_test],
        "val": files[n_test:n_test + n_val],
        "train": files[n_test + n_val:],
    }


def main():
    p = argparse.ArgumentParser(description="Paczka ZIP z podziałem train/val/test")
    p.add_argument("--version", default="v1", help="wersja zbioru, np. v1")
    args = p.parse_args()

    sessions = sorted(d for d in RAW.iterdir() if d.is_dir())
    if not sessions:
        raise SystemExit("Brak sesji w {}".format(RAW))

    rng = random.Random(SEED)
    rows = []
    for session in sessions:
        parts = split_session(list(session.glob("*.jpg")), rng)
        for split, files in parts.items():
            for f in files:
                rows.append((f, session.name, split))

    names = [f.name for f, _, _ in rows]
    if len(names) != len(set(names)):
        raise SystemExit("Powtarzające się nazwy plików między sesjami – przerwano")

    OUT.mkdir(parents=True, exist_ok=True)
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = OUT / "linesight_{}.zip".format(args.version)
    csv_path = SPLITS_DIR / "split_{}.csv".format(args.version)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for f, _, split in rows:
            zf.write(f, arcname="{}/{}".format(split, f.name))   # JPEG już jest skompresowany

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "session", "split"])
        for f, session, split in sorted(rows, key=lambda r: (r[2], r[1], r[0].name)):
            w.writerow([f.name, session, split])

    # Podsumowanie: sesja x podział
    print("{:<32} {:>6} {:>5} {:>5} {:>6}".format("sesja", "train", "val", "test", "razem"))
    totals = {"train": 0, "val": 0, "test": 0}
    for session in sessions:
        c = {s: sum(1 for _, se, sp in rows if se == session.name and sp == s) for s in totals}
        for s in totals:
            totals[s] += c[s]
        print("{:<32} {:>6} {:>5} {:>5} {:>6}".format(
            session.name, c["train"], c["val"], c["test"], sum(c.values())))
    print("{:<32} {:>6} {:>5} {:>5} {:>6}".format(
        "RAZEM", totals["train"], totals["val"], totals["test"], sum(totals.values())))
    print("\nZIP: {} ({:.1f} MB)".format(zip_path, zip_path.stat().st_size / 1e6))
    print("CSV: {}".format(csv_path))


if __name__ == "__main__":
    main()
