#!/bin/bash
# E1-08: benchmark silników TensorRT przy stałych zegarach (Jetson Nano, TensorRT 8.2.1).
# Uruchom z ~/linesight:  bash jetson/bench_engines.sh   (poprosi o hasło sudo – zegary)
# Wynik: models/bench_<data>/ – log trtexec na silnik, tegrastats, zegary.
TRTEXEC=/usr/src/tensorrt/bin/trtexec
ENGINES="yolo26n_v1_384x640_fp16 yolo26n_v1_384x640_fp32 yolo26n_v1_640x640_fp16 yolo26n_v1_640x640_fp32"
cd "$(dirname "$0")/../models" || exit 1
OUT=bench_$(date +%Y%m%d_%H%M)
mkdir -p "$OUT"

sudo nvpmodel -q | tee "$OUT/nvpmodel.txt"     # oczekiwane: MAXN (tryb 0)
sudo jetson_clocks --store                     # zapis obecnych zegarów (przywrócenie na końcu)
sudo jetson_clocks                             # CPU, GPU, EMC na stałe maksimum, wentylator max
sudo jetson_clocks --show > "$OUT/clocks.txt"

tegrastats --interval 500 --logfile "$OUT/tegrastats.log" &   # RAM, GPU %, temperatury co 0,5 s
TS=$!

for e in $ENGINES; do
  echo "=== $e  $(date +%H:%M:%S)" | tee -a "$OUT/marks.txt"
  # 2 s rozgrzewki, 20 s pomiaru; spin-wait = stabilniejszy pomiar czasu
  $TRTEXEC --loadEngine=$e.engine --warmUp=2000 --duration=20 --useSpinWait > "$OUT/$e.log" 2>&1
  grep -E "&&&& (PASSED|FAILED)|Throughput|Latency: min|GPU Compute Time: min" "$OUT/$e.log"
  sleep 5   # przerwa: GPU wraca do temperatury spoczynkowej
done

kill $TS
sudo jetson_clocks --restore
echo "Wyniki: models/$OUT"
