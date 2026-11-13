"""E1-08: dokładność silników TensorRT (surowe wyjścia z Jetsona) vs ten sam model ONNX.

Uruchom z głównego folderu projektu, z aktywnym .venv:
    python training\\eval_trt.py

Wejście: models\\out_384x640_<fp16|fp32>_<val|test>.npz  (z jetson/trt_dump.py, skopiowane scp)
Odniesienie: models\\yolo26n_v1_384x640.onnx uruchomiony tu przez onnxruntime (FP32, CPU);
yolo26n_v1_640x640.onnx rozdziela wpływ rozmiaru wejścia od wpływu wyeksportowanej głowicy.
Wszystkie warianty przechodzą przez ten sam letterbox, ten sam NMS (conf 0.001, IoU 0.7)
i to samo liczenie mAP – różnica pokazuje wyłącznie wpływ TensorRT i FP16.
"""
from pathlib import Path
import json

import cv2
import numpy as np
import onnxruntime as ort
import torch
from ultralytics.utils.metrics import ap_per_class, box_iou
from ultralytics.utils.nms import non_max_suppression

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "data" / "datasets" / "linesight-5b628dbc"
MODELS = ROOT / "models"
ONNX = MODELS / "yolo26n_v1_384x640.onnx"
ONNX_640 = MODELS / "yolo26n_v1_640x640.onnx"  # do rozdzielenia: wpływ rozmiaru wejścia vs głowicy
SUMMARY = ROOT / "runs" / "detect" / "yolo26n_v1" / "summary.json"
NAMES = ["bottle", "missing_cap", "fallen"]
IOUV = np.linspace(0.5, 0.95, 10)
CONF_DEPLOY = 0.48  # próg z E1-06


def letterbox(img, h, w):
    """Identycznie jak w jetson/trt_dump.py (i LetterBox w ultralytics)."""
    ih, iw = img.shape[:2]
    r = min(h / ih, w / iw)
    nh, nw = int(round(ih * r)), int(round(iw * r))
    if (nh, nw) != (ih, iw):
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    dh, dw = (h - nh) / 2, (w - nw) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img, r, (left, top)


def onnx_outputs(split, path=ONNX):
    """Surowe wyjścia modelu ONNX dla każdego zdjęcia: {nazwa: (wyjście [7,N], ratio, pad)}."""
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    _, _, H, W = inp.shape
    res = {}
    for p in sorted((DS / "images" / split).iterdir()):
        lb, r, pad = letterbox(cv2.imread(str(p)), H, W)
        x = np.ascontiguousarray(lb[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        res[p.name] = (sess.run(None, {inp.name: x})[0][0], r, pad)
    return res


def trt_outputs(path):
    d = np.load(path)
    return {str(n): (o, float(r), tuple(p)) for n, o, r, p in zip(d["names"], d["outputs"], d["ratio"], d["pad"])}


def load_labels(split, name, w, h):
    f = DS / "labels" / split / (Path(name).stem + ".txt")
    rows = np.loadtxt(f, ndmin=2) if f.exists() and f.stat().st_size else np.zeros((0, 5))
    cx, cy, bw, bh = rows[:, 1] * w, rows[:, 2] * h, rows[:, 3] * w, rows[:, 4] * h
    return rows[:, 0].astype(int), np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)


def match(pred_cls, true_cls, iou):
    """Dopasowanie predykcji do etykiet – jak DetectionValidator.match_predictions w ultralytics.
    Predykcje w kolejności malejącej pewności; każda etykieta może być trafiona raz na próg IoU."""
    correct = np.zeros((len(pred_cls), len(IOUV)), bool)
    iou = iou * (true_cls[:, None] == pred_cls)  # inna klasa = brak trafienia
    matched = np.zeros((iou.shape[0], len(IOUV)), bool)
    for j in np.flatnonzero((iou >= IOUV.min()).any(0)):
        available = np.where(matched, 0, iou[:, j, None])
        k = available.argmax(0)
        correct[j] = available[k, range(len(IOUV))] >= IOUV
        matched[k, range(len(IOUV))] |= correct[j]
    return correct


def counts(correct, conf, n_targets, c):
    """TP/FP/FN przy progu c i IoU 0,5. Dopasowanie szło w kolejności pewności,
    więc odcięcie słabszych predykcji nie zmienia trafień silniejszych."""
    keep = conf >= c
    tp = int(correct[keep, 0].sum())
    return tp, int(keep.sum()) - tp, n_targets - tp


def evaluate(split, raw):
    stats = []
    for name, (out, r, pad) in raw.items():
        h, w = cv2.imread(str(DS / "images" / split / name)).shape[:2]
        tcls, tbox = load_labels(split, name, w, h)
        det = non_max_suppression(torch.from_numpy(out[None]).float(), conf_thres=0.001, iou_thres=0.7,
                                  max_det=300, nc=len(NAMES))[0].numpy()
        boxes = det[:, :4].copy()
        boxes[:, [0, 2]] -= pad[0]  # cofnięcie letterboxa: pasy, potem skala
        boxes[:, [1, 3]] -= pad[1]
        boxes /= r
        conf, pcls = det[:, 4], det[:, 5].astype(int)
        iou = (box_iou(torch.from_numpy(tbox).float(), torch.from_numpy(boxes).float()).numpy()
               if len(tbox) and len(boxes) else np.zeros((len(tbox), len(boxes))))
        stats.append((match(pcls, tcls, iou), conf, pcls, tcls))
    correct, conf, pcls, tcls = [np.concatenate(x, 0) for x in zip(*stats)]
    _, _, p, r, _, ap, uc, _, _, f1_curve, x, _ = ap_per_class(correct, conf, pcls, tcls, names=dict(enumerate(NAMES)))
    best = float(x[f1_curve.mean(0).argmax()])  # próg z maksimum średniego F1 (jak w E1-06)
    return dict(P=p.mean(), R=r.mean(), mAP50=ap[:, 0].mean(), mAP5095=ap.mean(),
                deploy=counts(correct, conf, len(tcls), CONF_DEPLOY), best=best,
                at_best=counts(correct, conf, len(tcls), best),
                per_class={NAMES[c]: float(ap[i].mean()) for i, c in enumerate(uc)})


def raw_diff(a, b):
    """Największa różnica surowych wyjść między dwoma wariantami (te same zdjęcia)."""
    box = max(np.abs(a[n][0][:4] - b[n][0][:4]).max() for n in a)
    score = max(np.abs(a[n][0][4:] - b[n][0][4:]).max() for n in a)
    return box, score


def main():
    ref = json.loads(SUMMARY.read_text(encoding="utf-8"))
    for split in ("val", "test"):
        variants = {"ONNX 640x640 (laptop)": onnx_outputs(split, ONNX_640),
                    "ONNX FP32 (laptop)": onnx_outputs(split)}
        for prec in ("fp32", "fp16"):
            f = MODELS / f"out_384x640_{prec}_{split}.npz"
            if f.exists():
                variants[f"TensorRT {prec.upper()} (Jetson)"] = trt_outputs(f)
            else:
                print(f"brak {f.name} – pomijam")

        pt = ref[split]["all"]
        print(f"\n=== {split.upper()} ({len(variants['ONNX FP32 (laptop)'])} zdjęć) ===")
        print(f"{'wariant':<26}{'P':>7}{'R':>7}{'mAP50':>8}{'mAP50-95':>10}   TP/FP/FN @{CONF_DEPLOY}   najlepszy próg -> TP/FP/FN")
        print(f"{'PyTorch 640 (E1-06)':<26}{pt['P']:>7.3f}{pt['R']:>7.3f}{pt['mAP50']:>8.3f}{pt['mAP50-95']:>10.3f}   –")
        results = {}
        for name, raw in variants.items():
            m = results[name] = evaluate(split, raw)
            print(f"{name:<26}{m['P']:>7.3f}{m['R']:>7.3f}{m['mAP50']:>8.3f}{m['mAP5095']:>10.3f}   "
                  f"{'/'.join(map(str, m['deploy'])):<14}{m['best']:.2f} -> {'/'.join(map(str, m['at_best']))}")
        print("mAP50-95 na klasę: " + " | ".join(
            f"{n}: " + ", ".join(f"{c} {v:.3f}" for c, v in m["per_class"].items()) for n, m in results.items()))

        base = variants["ONNX FP32 (laptop)"]
        for name, raw in variants.items():
            if name.startswith("TensorRT"):
                b, s = raw_diff(base, raw)
                print(f"różnica surowych wyjść {name} vs ONNX: ramki max {b:.3f} px, pewności max {s:.4f}")


if __name__ == "__main__":
    main()
