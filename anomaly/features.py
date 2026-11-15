"""E4-07/E4-08: cechy okna sztuk – wspólny kod treningu (anomaly/model.py) i wdrożenia (diag/drive_health.py).

Jeden plik dla obu stron, żeby cechy liczone na żywo były identyczne z tymi z treningu (training-serving skew:
inna kolejność cech albo inne odchylenie standardowe i model dostaje dane, których nigdy nie widział).
Bez torcha i pandas – tylko numpy.
"""
import numpy as np

W = 32            # okno: 32 sztuki ≈ 50 s pracy
WIN_FEATURES = ["torque_mean_avg", "torque_peak_avg", "current_avg", "temp", "torque_mean_std",
                "torque_peak_std", "peak_to_mean"]


def window_features(x, seg, w=W):
    """Cechy okna w sztuk kończącego się na każdej sztuce (w obrębie odcinka pracy); NaN, gdy okno niepełne.
    x: [N, 4] kolumny jak data.FEATURES (moment średni, szczytowy, prąd, temperatura); seg: numer odcinka pracy."""
    out = np.full((len(x), len(WIN_FEATURES)), np.nan, dtype=np.float32)
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        for k in range(w - 1, len(idx)):
            win = x[idx[k - w + 1:k + 1]]
            out[idx[k]] = [win[:, 0].mean(), win[:, 1].mean(), win[:, 2].mean(), win[-1, 3],
                           win[:, 0].std(), win[:, 1].std(), (win[:, 1] / win[:, 0]).mean()]
    return out


def health_pct(ratio):
    """Kondycja napędu [%] z wyniku modelu podzielonego przez próg (skala logarytmiczna, dla operatora):
    wynik ≤ 0,3 progu -> 100 %, równy progowi -> ok. 66 %, ≥ 10 progów -> 0 %."""
    r = np.clip(np.asarray(ratio, dtype=float), 0.3, 10.0)
    return 100.0 * (1.0 - np.log10(r / 0.3) / np.log10(10.0 / 0.3))
