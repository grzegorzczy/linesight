"""E4-06: baseline bez ML dla kondycji napędu – poprzeczka dla modelu z E4-07.

Uruchomienie (z głównego folderu, .venv):  python anomaly\\baseline.py [data\\drive_raw.csv]
Wynik: tabela w konsoli, data/baseline_results.csv, data/baseline.png.

B1  EWMA na momencie średnim: z = λ·x + (1 − λ)·z; średnią i odchylenie z treningu. Najprostsze, co zrobiłby
    automatyk (karta kontrolna). Słabość: zimny start podnosi moment tak jak zużycie.
B2  Regresja moment ~ temperatura (wielomian 2. stopnia, na treningu; temperatura przycięta do zakresu treningu), EWMA na reszcie (różnica między zmierzonym a oczekiwanym
    przy tej temperaturze). Zna wpływ temperatury, więc zimny start nie powinien alarmować. Słabość: patrzy tylko
    na moment średni, nie na kształt cyklu (szczyt, rozrzut).
EWMA zaczyna od średniej na początku każdego odcinka pracy (restart karty po postoju).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import load  # noqa: E402
from metrics import evaluate, table, threshold  # noqa: E402

LAMBDA = 0.05     # wygładzanie EWMA: ok. 40 sztuk pamięci (2/λ), czyli ok. 1 min pracy


def ewma(x, segments, lam=LAMBDA, start=0.0):
    out = np.empty_like(x)
    z, prev = start, None
    for i, (v, s) in enumerate(zip(x, segments)):
        if s != prev:
            z, prev = start, s
        z = lam * v + (1 - lam) * z
        out[i] = z
    return out


def b1_score(df):
    tr = df[df.split == "train"]
    mu, sd = tr.torque_mean.mean(), tr.torque_mean.std()
    return ewma((df.torque_mean.to_numpy() - mu) / sd, df.segment.to_numpy())


def b2_score(df):
    tr = df[df.split == "train"]
    lo, hi = tr.temp.min(), tr.temp.max()
    coef = np.polyfit(tr.temp, tr.torque_mean, 2)       # moment ≈ a·T² + b·T + c (zależność nieliniowa)
    temp = np.clip(df.temp.to_numpy(), lo, hi)         # bez ekstrapolacji poza zakres treningu
    resid = df.torque_mean.to_numpy() - np.polyval(coef, temp)
    sd = np.std(resid[(df.split == "train").to_numpy()])
    print("B2: moment = {:.5f}·T² + {:.4f}·T + {:.3f}, T w [{:.1f}, {:.1f}] °C, reszta σ = {:.3f} Nm".format(
        *coef, lo, hi, sd))
    return ewma(resid / sd, df.segment.to_numpy())


def plot(df, eps, scores, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = (df.t.to_numpy() - df.t.iat[0]) / 60.0
    fig, ax = plt.subplots(len(scores) + 1, 1, figsize=(14, 3 * (len(scores) + 1)), sharex=True)
    ax[0].plot(t, df.torque_mean, ".", ms=1, label="moment średni [Nm]")
    ax0b = ax[0].twinx()
    ax0b.plot(t, df.temp, color="tab:orange", lw=1, label="temperatura [°C]")
    ax[0].set_ylabel("Nm")
    ax0b.set_ylabel("°C")
    ax[0].legend(loc="upper left")
    for (name, s, thr), a in zip(scores, ax[1:]):
        a.plot(t, s, lw=0.8, label=name)
        a.axhline(thr, color="red", ls="--", lw=1, label="próg")
        if name.startswith("AE"):            # błąd odtworzenia: od ok. 0,2 w pracy normalnej do kilkuset przy zużyciu
            a.set_yscale("log")
        a.legend(loc="upper left")
    for a in ax:
        for e0, e1 in eps:
            a.axvspan((e0 - df.t.iat[0]) / 60, (e1 - df.t.iat[0]) / 60, color="red", alpha=0.1)
        for sp in ("val", "test"):
            first = np.flatnonzero((df.split == sp).to_numpy())
            if first.size:
                a.axvline(t[first[0]], color="gray", lw=0.8)
    ax[-1].set_xlabel("minuty sesji (czerwone tło = zużycie; szare linie = początek val / test)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/drive_raw.csv"
    df, eps = load(path)
    print("Sztuki: {} (train {}, val {}, test {}), epizody zużycia: {}".format(
        len(df), *(int((df.split == s).sum()) for s in ("train", "val", "test")), len(eps)))
    results, curves = [], []
    for name, fn in (("B1 EWMA moment", b1_score), ("B2 regresja temp + EWMA", b2_score)):
        s = fn(df)
        thr = threshold(df, s)
        curves.append((name, s, thr))
        for sp in ("val", "test"):
            results.append((name, evaluate(df, s, thr, sp, eps)))
    tab = table(results)
    print(tab.to_string(index=False))
    Path("data").mkdir(exist_ok=True)
    tab.to_csv("data/baseline_results.csv", index=False)
    plot(df, eps, curves, "data/baseline.png")
    print("Zapisano data/baseline_results.csv, data/baseline.png")


if __name__ == "__main__":
    main()
