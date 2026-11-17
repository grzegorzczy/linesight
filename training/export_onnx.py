"""E1-07: eksport best.pt do ONNX (opset 13) w dwóch rozmiarach wejścia.

Uruchom z głównego folderu projektu, z aktywnym .venv:
    python training\\export_onnx.py          # głowica z NMS (one-to-many), 640x640 i 384x640
    python training\\export_onnx.py --e2e    # test: głowica end-to-end bez NMS (one-to-one), 384x640
    python training\\export_onnx.py --version v2 --only 384x640   # E6-08: runs/detect/yolo26n_v2 -> yolo26n_v2_384x640.onnx

Wynik: models\\yolo26n_v1_640x640.onnx i models\\yolo26n_v1_384x640.onnx
(*.onnx jest w .gitignore). Pliki idą na Jetsona, tam trtexec buduje silniki.
"""
import shutil
import sys
from pathlib import Path

import onnx
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "models"
OPSET = 13  # TensorRT 8.2 obsługuje operatory do opsetu 13 (sprawdzone w E1-02)

# (wysokość, szerokość). Kamera daje 640x360; 384 = najbliższa wielokrotność 32 (stride sieci).
SIZES = {"640x640": (640, 640), "384x640": (384, 640)}


def dims(value_info):
    return [d.dim_value for d in value_info.type.tensor_type.shape.dim]


def main():
    OUT.mkdir(exist_ok=True)
    argv = sys.argv[1:]
    e2e = "--e2e" in argv
    version = argv[argv.index("--version") + 1] if "--version" in argv else "v1"
    weights = ROOT / "runs" / "detect" / "yolo26n_{}".format(version) / "weights" / "best.pt"
    # nms=False włącza w ultralytics gałąź end2end (one-to-one, bez NMS); domyślnie (None) eksport
    # bierze głowicę one-to-many, której wynik wymaga NMS.
    sizes = {"384x640_e2e": (384, 640)} if e2e else SIZES
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
        sizes = {only: sizes[only]}
    for name, imgsz in sizes.items():
        # Nowy obiekt przy każdym eksporcie: export() zmienia model w pamięci (fuse, tryb eval).
        model = YOLO(str(weights))
        src = model.export(format="onnx", opset=OPSET, imgsz=imgsz,
                           simplify=True, dynamic=False, **({"nms": False} if e2e else {}))
        dst = OUT / f"yolo26n_{version}_{name}.onnx"
        shutil.move(src, dst)  # export zapisuje zawsze jako best.onnx obok best.pt

        m = onnx.load(str(dst))
        onnx.checker.check_model(m)
        opset = [o.version for o in m.opset_import if o.domain in ("", "ai.onnx")][0]
        print(f"\n{dst.name}: opset {opset}, wejście {dims(m.graph.input[0])}, "
              f"wyjście {dims(m.graph.output[0])}, {dst.stat().st_size / 1e6:.1f} MB")
        print("  klasy:", model.names)
        ops = sorted({n.op_type for n in m.graph.node})
        print("  operatory:", ", ".join(ops))


if __name__ == "__main__":
    main()
