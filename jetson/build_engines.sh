#!/bin/bash
# E1-07: budowa silników TensorRT z plików ONNX (Jetson Nano, TensorRT 8.2.1).
# Uruchom z ~/linesight:  nohup bash jetson/build_engines.sh > models/build_all.log 2>&1 &
# Wejście: models/yolo26n_v1_<rozmiar>.onnx  (skopiowane z laptopa)
# Wyjście: models/yolo26n_v1_<rozmiar>_<precyzja>.engine + log trtexec dla każdego silnika
TRTEXEC=/usr/src/tensorrt/bin/trtexec
cd "$(dirname "$0")/../models" || exit 1

for size in 384x640 640x640; do
  for prec in fp32 fp16; do
    name=yolo26n_v1_${size}_${prec}
    flag=""
    [ "$prec" = fp16 ] && flag="--fp16"
    echo "=== $name  start $(date +%H:%M:%S)"
    # --workspace w MB: składnia TRT 8.2 (nowsze wersje: --memPoolSize). 1024 vs 2048 porównamy w E1-08.
    $TRTEXEC --onnx=yolo26n_v1_${size}.onnx --saveEngine=${name}.engine \
      $flag --workspace=1024 > ${name}.log 2>&1
    grep -E "&&&& (PASSED|FAILED)" ${name}.log
    grep -E "Throughput|GPU Compute Time: min" ${name}.log
    echo "    koniec $(date +%H:%M:%S)"
  done
done
ls -lh *.engine
