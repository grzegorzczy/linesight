"""E4-06: zbiór „jedna sztuka = jeden wiersz” z surowych sygnałów napędu, podział wg czasu, epizody zużycia.

Wejście: CSV (t, name, value) – eksport z bazy (docs/etap-4-diagnostyka.md, „Eksport”) albo anomaly/sim.py.

Łączenie sygnałów: most wysyła każdą zmienną osobno i tylko przy zmianie. Kotwicą jest licznik sztuk
(zmienia się zawsze); dla każdej sztuki bierzemy wartość momentu / prądu najbliższą w czasie (±0,3 s – ta sama
próbka OPC UA), a gdy jej nie ma – ostatnią znaną (wartość się nie zmieniła, więc most jej nie wysłał).
Temperatura, zużycie, stan – ostatnia znana wartość.

Podział wg czasu, nie losowo: sąsiednie sztuki są prawie identyczne, losowe tasowanie przeniosłoby informację
z testu do treningu (przeciek), a model w produkcji też widzi tylko przeszłość.
    train – wszystko przed pierwszym epizodem zużycia (tylko praca normalna, z zimnymi startami),
    val   – od początku 1. epizodu do początku 2. (próg alarmu z części normalnej, epizod 1 do podglądu),
    test  – od początku 2. epizodu do końca (epizody 2 i 3 + praca normalna, w tym zimny start z --extra:
            fałszywe alarmy).
"""
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["torque_mean", "torque_peak", "current", "temp"]
SIGNALS = {"rTorqueMean_Nm": "torque_mean", "rTorquePeak_Nm": "torque_peak", "rCurrent_A": "current",
           "rMotorTemp_C": "temp", "rSimWear": "wear", "xInjWear": "wearing", "iStateCurrent": "state"}
PER_PIECE = ["torque_mean", "torque_peak", "current"]


def load_raw(path):
    raw = pd.read_csv(path)
    raw["t"] = raw["t"].astype(float)
    return raw.sort_values("t", kind="stable")


def pieces(raw, max_gap_s=10.0):
    """Tabela sztuk: t, piece, cechy, wear (prawda symulacji), wearing, segment (numer odcinka pracy)."""
    base = raw[raw.name == "udiProdProcessed"][["t", "value"]].rename(columns={"value": "piece"})
    base = base.reset_index(drop=True)
    for sig, col in SIGNALS.items():
        s = raw[raw.name == sig][["t", "value"]].rename(columns={"value": col}).reset_index(drop=True)
        if s.empty:
            base[col] = np.nan
            continue
        back = pd.merge_asof(base[["t"]], s, on="t", direction="backward")[col]
        if col in PER_PIECE:   # wartość z tej samej próbki (±0,3 s), inaczej ostatnia znana
            near = pd.merge_asof(base[["t"]], s, on="t", direction="nearest", tolerance=0.3)[col]
            base[col] = near.fillna(back)
        else:
            base[col] = back
    # Licznik sztuk rośnie tylko w Execute, więc każda sztuka to praca. Stan służy tylko do kontroli: przed pierwszą
    # zmianą stanu w eksporcie go nie znamy (most wysyła zmiany, a linia była w Execute już przed oknem eksportu,
    # 15.11 – bez tego odpadało pierwsze 30 min sesji).
    base["state"] = base["state"].fillna(6)
    base = base[base["state"] == 6].dropna(subset=FEATURES).reset_index(drop=True)
    # nowy odcinek pracy po przerwie między sztukami (postój) albo skoku licznika (wgranie programu, cofnięcie).
    # Pojedyncza brakująca sztuka (licznik +2, ok. 3 s) to zgubiona wiadomość, nie postój – 15.11: 7 na ok. 9000.
    dp = base["piece"].diff()
    new_seg = (base["t"].diff() > max_gap_s) | (dp < 1) | (dp > 5)
    base["segment"] = new_seg.cumsum()
    base["wear"] = base["wear"].fillna(0.0)
    base["wearing"] = base["wearing"].fillna(0.0) > 0.5
    return base


def episodes(df):
    """Epizody zużycia: [(t_start, t_end)] z ciągłych odcinków wearing == True."""
    w = df["wearing"].to_numpy()
    starts = np.flatnonzero(w & ~np.r_[False, w[:-1]])
    ends = np.flatnonzero(w & ~np.r_[w[1:], False])
    return [(df["t"].iat[a], df["t"].iat[b]) for a, b in zip(starts, ends)]


def split(df):
    """Dodaje kolumnę split (train / val / test) wg epizodów zużycia; potrzebne co najmniej 2 epizody."""
    eps = episodes(df)
    if len(eps) < 2:
        raise ValueError("potrzebne co najmniej 2 epizody zużycia, jest {}".format(len(eps)))
    df = df.copy()
    df["split"] = np.where(df["t"] < eps[0][0], "train", np.where(df["t"] < eps[1][0], "val", "test"))
    return df, eps


def load(path):
    df, eps = split(pieces(load_raw(path)))
    return df, eps


if __name__ == "__main__":
    import sys
    df, eps = load(sys.argv[1] if len(sys.argv) > 1 else "data/drive_raw.csv")
    print(df.groupby("split").agg(sztuki=("t", "size"), odcinki=("segment", "nunique"),
                                  zuzycie=("wearing", "sum"), temp_min=("temp", "min"), temp_max=("temp", "max")))
    print("epizody zużycia:", ["{:.1f} min".format((b - a) / 60) for a, b in eps])
    out = Path("data/drive_dataset.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print("Zapisano", out)
