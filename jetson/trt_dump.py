#!/usr/bin/env python3
"""E1-08: inferencja silnikiem TensorRT na folderze zdjęć, zapis surowych wyjść sieci.

Jetson, Python 3.6 (JetPack 4.6.1), TensorRT 8.2. Bez pycuda: pamięć GPU obsługujemy
przez ctypes, bezpośrednio z biblioteki CUDA Runtime (libcudart), która jest w JetPacku.

Użycie (z ~/linesight):
    python3 jetson/trt_dump.py <silnik.engine> <folder_ze_zdjęciami> <wynik.npz>

Wynik .npz: names (nazwy plików), outputs (N, 7, kandydaci) – surowe wyjście sieci
w pikselach wejścia sieci, ratio i pad (do cofnięcia letterboxa), czasy w ms.
Dekodowanie, NMS i mAP liczymy na laptopie tym samym kodem co dla PyTorcha.
"""
import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import tensorrt as trt

# --- CUDA Runtime przez ctypes (zamiast pycuda) ---
try:
    cudart = ctypes.CDLL("libcudart.so")
except OSError:
    cudart = ctypes.CDLL("/usr/local/cuda/lib64/libcudart.so")
cudart.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
cudart.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
cudart.cudaFree.argtypes = [ctypes.c_void_p]
H2D, D2H = 1, 2  # cudaMemcpyHostToDevice, cudaMemcpyDeviceToHost


def check(err, what):
    if err != 0:
        raise RuntimeError("{} zwróciło błąd CUDA {}".format(what, err))


def gpu_alloc(nbytes):
    ptr = ctypes.c_void_p()
    check(cudart.cudaMalloc(ctypes.byref(ptr), nbytes), "cudaMalloc")
    return ptr


# --- przygotowanie zdjęcia: to samo co LetterBox w ultralytics (wyśrodkowanie, szare pasy 114) ---
def letterbox(img, h, w):
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


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    engine_path, img_dir, out_path = sys.argv[1], Path(sys.argv[2]), sys.argv[3]

    logger = trt.Logger(trt.Logger.WARNING)
    with open(engine_path, "rb") as f:
        engine = trt.Runtime(logger).deserialize_cuda_engine(f.read())
    context = engine.create_execution_context()

    # Bindings: indeks 0 = wejście [1,3,H,W], indeks 1 = wyjście [1,7,N] (sprawdzane niżej)
    shapes = [tuple(engine.get_binding_shape(i)) for i in range(engine.num_bindings)]
    dtypes = [trt.nptype(engine.get_binding_dtype(i)) for i in range(engine.num_bindings)]
    assert engine.binding_is_input(0) and not engine.binding_is_input(1), "nieoczekiwana kolejność wejść/wyjść"
    _, _, H, W = shapes[0]
    print("silnik: wejście {} {}, wyjście {} {}".format(shapes[0], dtypes[0].__name__, shapes[1], dtypes[1].__name__))

    host_out = np.empty(shapes[1], dtype=dtypes[1])
    in_bytes = int(np.prod(shapes[0])) * np.dtype(dtypes[0]).itemsize
    d_in, d_out = gpu_alloc(in_bytes), gpu_alloc(host_out.nbytes)
    bindings = [d_in.value, d_out.value]

    files = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    names, outputs, ratios, pads, t_pre, t_inf = [], [], [], [], [], []
    for i, p in enumerate(files):
        t0 = time.perf_counter()
        img = cv2.imread(str(p))
        lb, r, pad = letterbox(img, H, W)
        x = np.ascontiguousarray(lb[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        x = np.ascontiguousarray(x, dtype=dtypes[0])
        t1 = time.perf_counter()
        check(cudart.cudaMemcpy(d_in, x.ctypes.data_as(ctypes.c_void_p), in_bytes, H2D), "cudaMemcpy H2D")
        context.execute_v2(bindings)  # synchroniczne: wraca po zakończeniu obliczeń
        check(cudart.cudaMemcpy(host_out.ctypes.data_as(ctypes.c_void_p), d_out, host_out.nbytes, D2H), "cudaMemcpy D2H")
        t2 = time.perf_counter()
        if i > 0:  # pierwsze zdjęcie = rozgrzewka, bez czasu
            t_pre.append((t1 - t0) * 1000)
            t_inf.append((t2 - t1) * 1000)
        names.append(p.name)
        outputs.append(host_out[0].astype(np.float32).copy())
        ratios.append(r)
        pads.append(pad)

    for d in (d_in, d_out):
        cudart.cudaFree(d)
    np.savez_compressed(out_path, names=np.array(names), outputs=np.stack(outputs),
                        ratio=np.array(ratios), pad=np.array(pads),
                        t_pre=np.array(t_pre), t_inf=np.array(t_inf))
    print("{} zdjęć -> {}".format(len(names), out_path))
    print("czas na zdjęcie (mediana): przygotowanie {:.1f} ms, kopiowanie + silnik {:.1f} ms".format(
        np.median(t_pre), np.median(t_inf)))
    o = outputs[0]
    print("kontrola: wyjście min {:.3f} max {:.3f}, najwyższa pewność klasy {:.3f}".format(o.min(), o.max(), o[4:].max()))


if __name__ == "__main__":
    main()
