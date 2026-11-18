#!/bin/bash
# E7-04: H.264 vs H.265 na sprzętowym koderze Jetsona Nano (NVENC), ta sama treść, kilka bitrate'ów.
#
# Jetson:  bash ~/linesight/jetson/codec_bench.sh ~/linesight_clips/20261116-171024_fallen_id26.mp4
#
# Referencję (patrz niżej) dekoduje nvv4l2decoder (NVDEC), koduje nvv4l2h264enc / nvv4l2h265enc
# w trybie CBR (control-rate=1), GOP 30 klatek, H.264 w profilu High, H.265 Main. Jakość: PSNR i SSIM ffmpeg względem referencji (klatka po klatce).
# Uwaga: źródło jest już skompresowane – wynik porównuje kodeki między sobą, nie jakość bezwzględną.
# Składnia elementów według „Accelerated GStreamer” dla L4T R32 (JetPack 4.6.1).
set -e
export LC_NUMERIC=C   # printf %f z kropką dziesiętną (polska lokalizacja oczekuje przecinka)
SRC="$1"
OUT=${2:-/tmp/codec_bench}
BITRATES=${BITRATES:-"500000 1000000 2000000"}
# preset-level kodera (L4T R32): 1 UltraFast (domyślny), 2 Fast, 3 Medium, 4 Slow; puste = domyślny
PRESET=${PRESET:-}
PRESET_ARG=${PRESET:+preset-level=$PRESET}
[ -f "$SRC" ] || { echo "Podaj plik źródłowy MP4 (H.264)"; exit 1; }
mkdir -p "$OUT"
# Referencja: klipy zdarzeń (bufor kołowy sklejany ffmpeg concat) mają nieregularne znaczniki czasu
# (r_frame_rate 12000/1). Porównanie wprost ze źródłem parowało złe klatki – PSNR stały ~31-34 dB niezależnie od
# bitrate'u, zarówno po czasie, jak i po numerze klatki. Dlatego najpierw czysta referencja: stałe 30 FPS, H.264
# High prawie bez strat (crf 10). Ten sam plik idzie do kodera i do porównania.
REF="$OUT/ref.mp4"
ffmpeg -v error -y -i "$SRC" -an -vf "setpts=N/(30*TB)" -r 30 -c:v libx264 -preset fast -crf 10 \
  -pix_fmt yuv420p -profile:v high "$REF"
CMP="[0:v]split[a1][a2];[1:v]split[b1][b2];[a1][b1]psnr;[a2][b2]ssim"

count() { ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$1"; }
frames=$(count "$REF")
src_kbps=$(ffprobe -v error -select_streams v:0 -show_entries format=bit_rate -of csv=p=0 "$REF")
echo "źródło: $SRC ($(count "$SRC") klatek)"
echo "preset-level: ${PRESET:-domyślny}"
echo "referencja: $REF, klatek: $frames, bitrate: $((src_kbps / 1000)) kb/s"
printf "%-6s %8s %10s %8s %8s %8s %8s %8s %7s\n" kodek kb/s_cel kb/s_wyn MB czas_s FPS PSNR_dB SSIM klatek

for codec in h264 h265; do
  # domyślny profil H.264 w nvv4l2h264enc to Baseline (0) – bez ramek B i CABAC; High (4) to uczciwe porównanie
  # z H.265 Main (domyślny 0)
  if [ $codec = h264 ]; then prof=4; else prof=0; fi
  for br in $BITRATES; do
    f="$OUT/${codec}_${br}${PRESET:+_p$PRESET}.mp4"
    t0=$(date +%s.%N)
    gst-launch-1.0 -q filesrc location="$REF" ! qtdemux ! queue ! h264parse ! nvv4l2decoder ! \
      nvv4l2${codec}enc bitrate=$br control-rate=1 iframeinterval=30 profile=$prof $PRESET_ARG ! ${codec}parse ! qtmux ! \
      filesink location="$f" -e > /dev/null 2>&1
    t1=$(date +%s.%N)
    secs=$(python3 -c "print($t1 - $t0)")
    kbps=$(ffprobe -v error -select_streams v:0 -show_entries format=bit_rate -of csv=p=0 "$f")
    mb=$(python3 -c "print('%.2f' % ($(stat -c %s "$f") / 1048576))")
    q=$(ffmpeg -nostats -i "$f" -i "$REF" -lavfi "$CMP" -f null - 2>&1)
    psnr=$(echo "$q" | grep -o 'average:[0-9.inf]*' | head -1 | cut -d: -f2)
    ssim=$(echo "$q" | grep -o 'All:[0-9.]*' | head -1 | cut -d: -f2)
    printf "%-6s %8d %10d %8s %8.1f %8.0f %8s %8s %7s\n" $codec $((br / 1000)) $((kbps / 1000)) $mb $secs \
      $(python3 -c "print($frames / $secs)") "$psnr" "$ssim" "$(count "$f")"
  done
done
echo "pliki: $OUT"
