"""E2-03: DeepStream (nvinfer + parser .so) vs TensorRT FP16 uruchamiany z Pythona (E1-08).

Uruchom z głównego folderu projektu, z aktywnym .venv:
    python training\\eval_ds.py

Wejście: models\\ds_<val|test>.json (z jetson/ds_dump.py) i models\\out_384x640_fp16_<val|test>.npz (E1-08).
Ten sam silnik, te same zdjęcia, ta sama metryka (score z eval_trt.py). Różnią się: dekodowanie JPEG
i konwersja kolorów (GStreamer + nvvideoconvert zamiast OpenCV), kolor pasów letterboxa
i NMS (nvinfer cluster-mode=2 zamiast ultralytics).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_trt import CONF_DEPLOY, MODELS, NAMES, raw_to_dets, score, trt_outputs  # noqa: E402


def iou_xyxy(a, b):
    lt, rb = np.maximum(a[:, None, :2], b[None, :, :2]), np.minimum(a[:, None, 2:4], b[None, :, 2:4])
    inter = np.prod(np.clip(rb - lt, 0, None), 2)
    area = lambda x: np.prod(x[:, 2:4] - x[:, :2], 1)  # noqa: E731
    return inter / (area(a)[:, None] + area(b)[None] - inter + 1e-9)


def agreement(ds, trt, c=CONF_DEPLOY):
    """Decyzje przy progu wdrożeniowym: pary tej samej klasy z IoU >= 0,5, ramki bez pary, różnice."""
    pairs = only_ds = only_trt = 0
    box_diff = conf_diff = 0.0
    for name in trt:
        a = np.asarray(ds.get(name, []), np.float32).reshape(-1, 6)
        b = np.asarray(trt[name], np.float32).reshape(-1, 6)
        a, b = a[a[:, 4] >= c], b[b[:, 4] >= c]
        used = set()
        if len(a) and len(b):
            iou = iou_xyxy(a, b) * (a[:, None, 5] == b[None, :, 5])
            for i in np.argsort(-a[:, 4]):
                j = int(iou[i].argmax())
                if iou[i, j] >= 0.5 and j not in used:
                    used.add(j)
                    pairs += 1
                    box_diff = max(box_diff, float(np.abs(a[i, :4] - b[j, :4]).max()))
                    conf_diff = max(conf_diff, abs(float(a[i, 4] - b[j, 4])))
        only_ds += len(a) - len(used)
        only_trt += len(b) - len(used)
    return pairs, only_ds, only_trt, box_diff, conf_diff


def main():
    for split in ("val", "test"):
        f_ds, f_trt = MODELS / f"ds_{split}.json", MODELS / f"out_384x640_fp16_{split}.npz"
        if not (f_ds.exists() and f_trt.exists()):
            print(f"brak {f_ds.name} lub {f_trt.name} – pomijam {split}")
            continue
        ds = json.loads(f_ds.read_text(encoding="utf-8"))["dets"]
        trt = {n: raw_to_dets(o, r, p) for n, (o, r, p) in trt_outputs(f_trt).items()}
        print(f"\n=== {split.upper()} ({len(trt)} zdjęć) ===")
        print(f"{'wariant':<28}{'P':>7}{'R':>7}{'mAP50':>8}{'mAP50-95':>10}   TP/FP/FN @{CONF_DEPLOY}")
        for name, dets in (("TensorRT FP16 + Python", trt), ("DeepStream nvinfer FP16", ds)):
            m = score(split, dets)
            print(f"{name:<28}{m['P']:>7.3f}{m['R']:>7.3f}{m['mAP50']:>8.3f}{m['mAP5095']:>10.3f}   "
                  f"{'/'.join(map(str, m['deploy']))}   "
                  + ", ".join(f"{c} {v:.3f}" for c, v in m["per_class"].items()))
        pairs, only_ds, only_trt, bd, cd = agreement(ds, trt)
        print(f"decyzje @{CONF_DEPLOY}: wspólne {pairs}, tylko DeepStream {only_ds}, tylko Python {only_trt}; "
              f"max różnica ramki {bd:.2f} px, pewności {cd:.4f}")


if __name__ == "__main__":
    main()
