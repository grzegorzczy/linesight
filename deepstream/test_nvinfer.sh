#!/bin/bash
# E2-03: kamera -> nvinfer (YOLO26n FP16) w gst-launch.
#   ./test_nvinfer.sh fps        – pomiar FPS potoku z inferencją (wyjście do fakesink)
#   ./test_nvinfer.sh mp4 [plik] – zapis 640x360 z ramkami do MP4 (Ctrl+C kończy i domyka plik)
# Uruchamiać z katalogu deepstream/ (ścieżka do konfiguracji jest względna).
set -e
cd "$(dirname "$0")"
DEV=${DEV:-/dev/video0}
SRC="v4l2src device=$DEV extra-controls=c,white_balance_temperature_auto=0,white_balance_temperature=5500 \
 ! video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 \
 ! nvvideoconvert ! video/x-raw(memory:NVMM),format=NV12 \
 ! m.sink_0 nvstreammux name=m batch-size=1 width=640 height=360 live-source=1 \
 ! nvinfer config-file-path=configs/nvinfer_yolo26.txt"

case "$1" in
  fps)
    stdbuf -oL gst-launch-1.0 -v $SRC ! fpsdisplaysink video-sink=fakesink text-overlay=false sync=false \
      | grep --line-buffered "last-message" ;;
  mp4)
    OUT=${2:-/tmp/e2-03.mp4}
    gst-launch-1.0 -e $SRC \
      ! nvvideoconvert ! "video/x-raw(memory:NVMM),format=RGBA" ! nvdsosd \
      ! nvvideoconvert ! "video/x-raw(memory:NVMM),format=I420" \
      ! nvv4l2h264enc bitrate=4000000 ! h264parse ! qtmux ! filesink location="$OUT"
    echo "Zapisano: $OUT" ;;
  *) echo "użycie: $0 fps | mp4 [plik]"; exit 1 ;;
esac
