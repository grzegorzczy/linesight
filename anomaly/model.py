"""E4-07: model kondycji napędu w PyTorch – autoenkoder cech okna, własna pętla treningowa.

Uruchomienie (z głównego folderu, .venv z torch):  python anomaly\\model.py [data\\drive_raw.csv]
Wynik: tabela B1 / B2 / AE w konsoli, data/model_results.csv, data/model.png (B2 vs AE), data/model_train.png
       (krzywe uczenia), models/drive_ae.onnx + models/drive_ae.json (normalizacja, okno, próg – wdrożenie w E4-08).

Idea. Okno ostatnich W = 32 sztuk (ok. 50 s) opisuję 7 cechami: średni moment średni, średni moment szczytowy,
średni prąd, temperatura, rozrzut (odchylenie) momentu średniego i szczytowego, średni stosunek szczyt/średni.
Autoenkoder (7 -> 16 -> 2 -> 16 -> 7) uczy się na pracy normalnej – z zimnymi startami – odtwarzać te cechy przez
„wąskie gardło” 2 liczb, czyli zapamiętuje, jak normalnie od siebie zależą (np. wyższy moment, gdy zimno).
Zużycie łamie te zależności (szczyt rośnie szybciej niż średni, rośnie rozrzut) -> rośnie błąd odtworzenia.
Wynik na sztukę = błąd odtworzenia cech okna, które się na niej kończy; alarm i próg jak w baseline (metrics.py).

Dlaczego cechy okna, a nie surowe okno (W x 4 wartości)? Sprawdzone 15.11: autoenkoder surowego okna uczy się
głównie odtwarzać szum pojedynczych sztuk, którego nie da się przewidzieć – wykrywał zużycie przy 29–30 %,
gorzej niż regresja B2 (16–19 %). Uśrednienie w oknie usuwa szum, zostaje to, co ma znaczenie.
Wybór W i rozmiaru gardła: po wynikach na walidacji (W 16/32, gardło 2/3), nie na teście.

Pętla treningowa (bez gotowego Trainera):
  epoka: model.train() -> dla każdej paczki z DataLoadera: zero_grad, forward, MSE, backward, step
         model.eval() + torch.no_grad() -> strata na walidacji (praca normalna z części val)
  early stopping: zapamiętuję wagi z najlepszą stratą walidacyjną; stop po PATIENCE epokach bez poprawy.
"""
import copy
import json
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline import b1_score, b2_score, plot  # noqa: E402
from data import FEATURES, load  # noqa: E402
from metrics import HOLD, evaluate, normal_mask, table, threshold  # noqa: E402

W = 32
LATENT = 2
EPOCHS = 500
PATIENCE = 30
BATCH = 64
LR = 1e-3
SEED = 0
WIN_FEATURES = ["torque_mean_avg", "torque_peak_avg", "current_avg", "temp", "torque_mean_std",
                "torque_peak_std", "peak_to_mean"]


def window_features(x, seg, w=W):
    """Cechy okna w sztuk kończącego się na każdej sztuce (w obrębie odcinka pracy); NaN, gdy okno niepełne.
    x: kolumny jak FEATURES (moment średni, szczytowy, prąd, temperatura)."""
    out = np.full((len(x), len(WIN_FEATURES)), np.nan, dtype=np.float32)
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        for k in range(w - 1, len(idx)):
            win = x[idx[k - w + 1:k + 1]]
            out[idx[k]] = [win[:, 0].mean(), win[:, 1].mean(), win[:, 2].mean(), win[-1, 3],
                           win[:, 0].std(), win[:, 1].std(), (win[:, 1] / win[:, 0]).mean()]
    return out


class WindowDataset(Dataset):
    """Cechy okien po normalizacji; autoenkoder: wejście = cel."""

    def __init__(self, z):
        self.z = torch.from_numpy(z.astype(np.float32))

    def __len__(self):
        return len(self.z)

    def __getitem__(self, i):
        return self.z[i]


class AE(nn.Module):
    def __init__(self, n=len(WIN_FEATURES), latent=LATENT):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(n, 16), nn.Tanh(), nn.Linear(16, latent), nn.Tanh())
        self.decoder = nn.Sequential(nn.Linear(latent, 16), nn.Tanh(), nn.Linear(16, n))

    def forward(self, x):
        return self.decoder(self.encoder(x))


def train(model, ds_tr, ds_va):
    torch.manual_seed(SEED)
    loader = DataLoader(ds_tr, batch_size=BATCH, shuffle=True)   # tasowanie okien w treningu jest OK: podział
    xv = ds_va.z                                                  # train/val/test i tak jest wg czasu
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = nn.MSELoss()
    best, best_state, wait, hist = float("inf"), None, 0, []
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total = 0.0
        for xb in loader:
            opt.zero_grad()
            loss = loss_fn(model(xb), xb)
            loss.backward()
            opt.step()
            total += loss.item() * len(xb)
        model.eval()
        with torch.no_grad():
            val = loss_fn(model(xv), xv).item()
        hist.append((total / len(ds_tr), val))
        improved = val < best - 1e-5
        if improved:
            best, best_state, wait = val, copy.deepcopy(model.state_dict()), 0
        else:
            wait += 1
        if epoch % 25 == 0:
            print("epoka {:3d}  strata trening {:.4f}  walidacja {:.4f}  (najlepsza {:.4f})".format(epoch, *hist[-1], best))
        if wait >= PATIENCE:
            print("early stopping po epoce {}: najlepsza walidacja {:.4f} w epoce {}".format(epoch, best, epoch - PATIENCE))
            break
    model.load_state_dict(best_state)
    return hist


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/drive_raw.csv"
    torch.manual_seed(SEED)
    df, eps = load(path)
    feats = window_features(df[FEATURES].to_numpy(dtype=np.float32), df.segment.to_numpy())
    ok = ~np.isnan(feats[:, 0])
    tr = (df.split == "train").to_numpy() & ok
    va = (df.split == "val").to_numpy() & normal_mask(df) & ok
    mu, sd = feats[tr].mean(0), feats[tr].std(0)            # normalizacja z treningu (bez przecieku)
    z = (feats - mu) / sd
    ds_tr, ds_va = WindowDataset(z[tr]), WindowDataset(z[va])
    print("Okna: trening {}, walidacja (normalne) {}; cechy: {}".format(len(ds_tr), len(ds_va), ", ".join(WIN_FEATURES)))

    model = AE()
    print("Parametry modelu:", sum(p.numel() for p in model.parameters()))
    hist = train(model, ds_tr, ds_va)
    model.eval()
    with torch.no_grad():
        za = torch.from_numpy(np.nan_to_num(z).astype(np.float32))
        s_ae = ((model(za) - za) ** 2).mean(dim=1).numpy()
    s_ae[~ok] = np.nan

    results, curves = [], []
    for name, s in (("B1 EWMA moment", b1_score(df)), ("B2 regresja temp + EWMA", b2_score(df)),
                    ("AE autoenkoder cech okna", s_ae)):
        thr = threshold(df, s)
        curves.append((name, s, thr))
        for sp in ("val", "test"):
            results.append((name, evaluate(df, s, thr, sp, eps)))
    tab = table(results)
    print(tab.to_string(index=False))

    Path("data").mkdir(exist_ok=True)
    Path("models").mkdir(exist_ok=True)
    tab.to_csv("data/model_results.csv", index=False)
    plot(df, eps, curves[1:], "data/model.png")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(7, 4))
    plt.plot([h[0] for h in hist], label="trening")
    plt.plot([h[1] for h in hist], label="walidacja")
    plt.yscale("log")
    plt.xlabel("epoka")
    plt.ylabel("MSE")
    plt.legend()
    plt.tight_layout()
    plt.savefig("data/model_train.png", dpi=110)

    kw = dict(input_names=["features"], output_names=["recon"], dynamic_axes={"features": {0: "n"}, "recon": {0: "n"}},
              opset_version=17)
    try:
        torch.onnx.export(model, za[:1], "models/drive_ae.onnx", dynamo=False, **kw)   # eksporter TorchScript
    except TypeError:                                                                 # starszy torch bez `dynamo`
        torch.onnx.export(model, za[:1], "models/drive_ae.onnx", **kw)
    json.dump({"window": W, "features": FEATURES, "window_features": WIN_FEATURES, "mean": mu.tolist(),
               "std": sd.tolist(), "threshold": curves[2][2], "hold": HOLD}, open("models/drive_ae.json", "w"), indent=2)
    print("Zapisano data/model_results.csv, data/model.png, data/model_train.png, models/drive_ae.onnx, models/drive_ae.json")


if __name__ == "__main__":
    main()
