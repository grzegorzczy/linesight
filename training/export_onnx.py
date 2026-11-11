"""E1-07: eksport best.pt do ONNX (opset 13) w dwóch rozmiarach wejścia.

Uruchom z głównego folderu projektu, z aktywnym .venv:
    python training\\export_onnx.py

Wynik: models\\yolo26n_v1_640x640.onnx i models\\yolo26n_v1_384x640.onnx
(*.onnx jest w .gitignore). Pliki idą na Jetsona, tam trtexec buduje silniki.
"""
import shutil
from pathlib import Path

import onnx
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "runs" / "detect" / "yolo26n_v1" / "weights" / "best.pt"
OUT = ROOT / "models"
OPSET = 13  # TensorRT 8.2 obsługuje operatory do opsetu 13 (sprawdzone w E1-02)

# (wysokość, szerokość). Kamera daje 640x360; 384 = najbliższa wielokrotność 32 (stride sieci).
SIZES = {"640x640": (640, 640), "384x640": (384, 640)}


def dims(value_info):
    return [d.dim_value for d in value_info.type.tensor_type.shape.dim]


def main():
    OUT.mkdir(exist_ok=True)
    for name, imgsz in SIZES.items():
        # Nowy obiekt przy każdym eksporcie: export() zmienia model w pamięci (fuse, tryb eval).
        model = YOLO(str(WEIGHTS))
        src = model.export(format="onnx", opset=OPSET, imgsz=imgsz,
                           simplify=True, dynamic=False)
        dst = OUT / f"yolo26n_v1_{name}.onnx"
        shutil.move(src, dst)  # export zapisuje zawsze jako best.onnx obok best.pt

        m = onnx.load(str(dst))
        onnx.checker.check_model(m)
        opset = [o.version for o in m.opset_import if o.domain in ("", "ai.onnx")][0]
        print(f"\n{dst.name}: opset {opset}, wejście {dims(m.graph.input[0])}, "
              f"wyjście {dims(m.graph.output[0])}, {dst.stat().st_size / 1e6:.1f} MB")
        print("  klasy:", model.names)


if __name__ == "__main__":
    main()
