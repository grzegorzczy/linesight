#!/bin/bash
# E7-04: H.264 vs H.265 na sprzętowym koderze Jetsona Nano (NVENC), ta sama treść, kilka bitrate'ów.
#
# Jetson:  bash ~/linesight/jetson/codec_bench.sh ~/linesight_clips/20261116-171024_fallen_id26.mp4
#
# Źródło (klip zdarzenia, H.264 z NVENC) dekoduje nvv4l2decoder (NVDEC), koduje nvv4l2h264enc / nvv4l2h265enc
# w trybie CBR (control-rate=1), GOP 30 klatek, H.264 w profilu High, H.265 Main. Jakość: PSNR i SSIM ffmpeg względem źródła (klatka po klatce).
# Uwaga: źródło jest już skompresowane – wynik porównuje kodeki między sobą, nie jakość bezwzględną.
# Składnia elementów według „Accelerated GStreamer” dla L4T R32 (JetPack 4.6.1).
set -e
export LC_NUMERIC=C   # printf %f z kropką dziesiętną (polska lokalizacja oczekuje przecinka)
SRC="$1"
OUT=${2:-/tmp/codec_bench}
BITRATES=${BITRATES:-"500000 1000000 2000000"}
[ -f "$SRC" ] || { echo "Podaj plik źródłowy MP4 (H.264)"; exit 1; }
mkdir -p "$OUT"

frames=$(ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$SRC")
src_kbps=$(ffprobe -v error -select_streams v:0 -show_entries format=bit_rate -of csv=p=0 "$SRC")
echo "źródło: $SRC, klatek: $frames, bitrate: $((src_kbps / 1000)) kb/s"
printf "%-6s %8s %10s %8s %8s %8s %8s %8s\n" kodek kb/s_cel kb/s_wyn MB czas_s FPS PSNR_dB SSIM

for codec in h264 h265; do
  # domyślny profil H.264 w nvv4l2h264enc to Baseline (0) – bez ramek B i CABAC; High (4) to uczciwe porównanie
  # z H.265 Main (domyślny 0)
  if [ $codec = h264 ]; then prof=4; else prof=0; fi
  for br in $BITRATES; do
    f="$OUT/${codec}_${br}.mp4"
    t0=$(date +%s.%N)
    gst-launch-1.0 -q filesrc location="$SRC" ! qtdemux ! queue ! h264parse ! nvv4l2decoder ! \
      nvv4l2${codec}enc bitrate=$br control-rate=1 iframeinterval=30 profile=$prof ! ${codec}parse ! qtmux ! \
      filesink location="$f" -e > /dev/null 2>&1
    t1=$(date +%s.%N)
    secs=$(python3 -c "print($t1 - $t0)")
    kbps=$(ffprobe -v error -select_streams v:0 -show_entries format=bit_rate -of csv=p=0 "$f")
    mb=$(python3 -c "print('%.2f' % ($(stat -c %s "$f") / 1048576))")
    q=$(ffmpeg -nostats -i "$f" -i "$SRC" -lavfi "[0:v][1:v]psnr;[0:v][1:v]ssim" -f null - 2>&1)
    psnr=$(echo "$q" | grep -o 'average:[0-9.inf]*' | head -1 | cut -d: -f2)
    ssim=$(echo "$q" | grep -o 'All:[0-9.]*' | head -1 | cut -d: -f2)
    printf "%-6s %8d %10d %8s %8.1f %8.0f %8s %8s\n" $codec $((br / 1000)) $((kbps / 1000)) $mb $secs \
      $(python3 -c "print($frames / $secs)") "$psnr" "$ssim"
  done
done
echo "pliki: $OUT"
