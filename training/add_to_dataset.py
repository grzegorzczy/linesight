"""E6-08: nowa wersja zbioru = poprzednia (zamrożona) + nowe sesje; paczka ZIP tylko z nowymi zdjęciami.

Zasady podziału nowych zdjęć:
  - sesja z 'newdomain_test' w nazwie -> w całości 'test': zdjęcia losowe z capture.py w nowych warunkach,
    NIE wybrane przez model (test złożony z klatek, na których v1 się myli, z góry przesądzałby porównanie),
  - pozostałe nowe sesje (niepewne klatki z Jetsona) -> 80 % train / 20 % val, bez test,
  - wiersze poprzedniej wersji (split_v1.csv) przepisujemy bez zmian: stary test zostaje zamrożony,
    więc v1 i v2 porównujemy na dokładnie tych samych zdjęciach.

Niepewne klatki: --al-from kopiuje *.jpg z data/frames_inbox/<urządzenie>/<dzień>/ do data/raw/<--al-session>/
z prefiksem nazwy sesji (jak capture.py), żeby nazwy były unikalne w całym zbiorze.
Uwaga: kolejne niepewne klatki dzieli 2-5 s, więc sąsiednie są do siebie podobne – podział losowy daje
zawyżone val (prawie te same klatki w train i val). Dlatego o v2 rozstrzyga niezależny test nowej domeny.

Uruchomienie (laptop, folder projektu, .venv):
  python training\\add_to_dataset.py --base v1 --version v2 --al-from data\\frames_inbox\\jetson-01 --al-session 20261116_al_uncertain
"""
import argparse
import csv
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "upload"
SPLITS_DIR = ROOT / "training" / "splits"
VAL_FRAC = 0.2
SEED = 42


def copy_al_frames(src, session):
    dest = RAW / session
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(Path(src).glob("*/*.jpg")):
        target = dest / "{}_{}".format(session, f.name)
        if not target.exists():
            shutil.copy2(f, target)
            n += 1
    print("niepewne klatki: skopiowano {} nowych do {} (razem {})".format(n, dest, len(list(dest.glob("*.jpg")))))


def main():
    p = argparse.ArgumentParser(description="Nowa wersja zbioru: poprzednia + nowe sesje")
    p.add_argument("--base", default="v1")
    p.add_argument("--version", required=True)
    p.add_argument("--al-from", type=Path, help="data/frames_inbox/<urządzenie> – niepewne klatki z chmury")
    p.add_argument("--al-session", default=None, help="nazwa sesji dla niepewnych klatek w data/raw")
    a = p.parse_args()

    if a.al_from:
        if not a.al_session:
            raise SystemExit("--al-from wymaga --al-session")
        copy_al_frames(a.al_from, a.al_session)

    with open(SPLITS_DIR / "split_{}.csv".format(a.base), encoding="utf-8") as fh:
        base = list(csv.DictReader(fh))
    known = {r["session"] for r in base}
    new_sessions = sorted(d for d in RAW.iterdir() if d.is_dir() and d.name not in known)
    if not new_sessions:
        raise SystemExit("Brak nowych sesji w {}".format(RAW))

    rng = random.Random(SEED)
    new_rows = []
    for s in new_sessions:
        files = sorted(s.glob("*.jpg"))
        if "newdomain_test" in s.name:
            parts = {"test": files}
        else:
            rng.shuffle(files)
            n_val = max(1, round(len(files) * VAL_FRAC))
            parts = {"val": files[:n_val], "train": files[n_val:]}
        for split, fs in parts.items():
            new_rows += [(f, s.name, split) for f in fs]

    names = [r["file"] for r in base] + [f.name for f, _, _ in new_rows]
    if len(names) != len(set(names)):
        raise SystemExit("Powtarzające się nazwy plików – przerwano")

    OUT.mkdir(parents=True, exist_ok=True)
    zip_path = OUT / "linesight_{}_nowe.zip".format(a.version)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for f, _, split in new_rows:
            zf.write(f, arcname="{}/{}".format(split, f.name))

    csv_path = SPLITS_DIR / "split_{}.csv".format(a.version)
    rows = [(r["file"], r["session"], r["split"]) for r in base] + [(f.name, s, sp) for f, s, sp in new_rows]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "session", "split"])
        for r in sorted(rows, key=lambda r: (r[2], r[1], r[0])):
            w.writerow(r)

    print("{:<36} {:>6} {:>5} {:>5}".format("nowa sesja", "train", "val", "test"))
    for s in new_sessions:
        c = Counter(sp for _, se, sp in new_rows if se == s.name)
        print("{:<36} {:>6} {:>5} {:>5}".format(s.name, c["train"], c["val"], c["test"]))
    c = Counter(r[2] for r in rows)
    print("\nzbiór {}: train {} / val {} / test {} (w tym stary test {} bez zmian)".format(
        a.version, c["train"], c["val"], c["test"], sum(1 for r in base if r["split"] == "test")))
    print("ZIP (tylko nowe zdjęcia): {} ({:.1f} MB)".format(zip_path, zip_path.stat().st_size / 1e6))
    print("CSV: {}".format(csv_path))


if __name__ == "__main__":
    main()
