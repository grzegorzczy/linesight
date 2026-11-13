#!/bin/bash
# E2-04: surowe nagranie z kamery (bez inferencji) do testów powtarzalnych.
#   bash record_raw.sh [plik]   – Ctrl+C kończy nagranie i domyka plik (domyślnie /tmp/raw.mp4)
# Te same ustawienia kamery co w potoku (YUY2 640x360@30, WB 5500 K). Kodowanie H.264 sprzętowo,
# 8 Mbit/s, żeby kompresja jak najmniej zmieniała obraz względem obrazu na żywo.
set -e
DEV=${DEV:-/dev/video0}
OUT=${1:-/tmp/raw.mp4}
gst-launch-1.0 -e v4l2src device=$DEV \
  extra-controls=c,white_balance_temperature_auto=0,white_balance_temperature=5500 \
  ! video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 \
  ! nvvideoconvert ! "video/x-raw(memory:NVMM),format=I420" \
  ! nvv4l2h264enc bitrate=8000000 ! h264parse ! qtmux ! filesink location="$OUT"
echo "Zapisano: $OUT"
