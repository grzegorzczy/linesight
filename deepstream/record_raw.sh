#!/bin/bash
# E2-04: surowe nagranie z kamery (bez inferencji) do testów powtarzalnych + podgląd na laptopie.
#   bash record_raw.sh [plik]   – Ctrl+C kończy nagranie i domyka plik (domyślnie /tmp/raw.mp4)
# Podgląd: ten sam strumień H.264 idzie przez RTP/UDP na laptop (VLC + jetson.sdp, port 5000, jak w E1-01).
#   PREVIEW=""  bash record_raw.sh ...   – bez podglądu;  PREVIEW=<ip> – inny adres laptopa
# Te same ustawienia kamery co w potoku (YUY2 640x360@30, WB 5500 K). Kodowanie H.264 sprzętowo,
# 8 Mbit/s, żeby kompresja jak najmniej zmieniała obraz względem obrazu na żywo.
set -e
DEV=${DEV:-/dev/video0}
OUT=${1:-/tmp/raw.mp4}
PREVIEW=${PREVIEW-192.168.0.203}
TO_LAPTOP=""
if [ -n "$PREVIEW" ]; then
  TO_LAPTOP="t. ! queue ! rtph264pay config-interval=1 pt=96 ! udpsink host=$PREVIEW port=5000 sync=false"
  echo "Podgląd: VLC na $PREVIEW, plik jetson.sdp (port 5000)"
fi
gst-launch-1.0 -e v4l2src device=$DEV \
  extra-controls=c,white_balance_temperature_auto=0,white_balance_temperature=5500 \
  ! video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 \
  ! nvvideoconvert ! "video/x-raw(memory:NVMM),format=I420" \
  ! nvv4l2h264enc bitrate=8000000 insert-sps-pps=1 iframeinterval=30 ! h264parse ! tee name=t \
  t. ! queue ! qtmux ! filesink location="$OUT" \
  $TO_LAPTOP
echo "Zapisano: $OUT"
