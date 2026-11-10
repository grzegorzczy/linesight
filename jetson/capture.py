#!/usr/bin/env python3
"""E1-03: zbieranie zdjęć do zbioru danych.

Jetson Nano, JetPack 4.6.1, Python 3.6, OpenCV z JetPacka (z obsługą GStreamera).

Jedna kamera, dwa wyjścia przez GStreamer `tee`:
  1. appsink -> OpenCV -> zapis JPEG co --interval sekund,
  2. (opcjonalnie) H.264 RTP/UDP -> VLC na laptopie = podgląd na żywo.

Przykład:
  python3 jetson/capture.py --tag mixed --count 100 --interval 1.5

Ctrl+C kończy w dowolnym momencie i zwalnia kamerę.
"""
import argparse
import datetime
import subprocess
import sys
import time
from pathlib import Path

import cv2

DEVICE = "/dev/video0"
WIDTH, HEIGHT, FPS = 640, 360, 30
WB_KELVIN = 5500              # balans bieli ustalony w E1-01
LAPTOP_IP = "192.168.0.203"
PREVIEW_PORT = 5000
WARMUP_S = 2.0                # automatyczna ekspozycja potrzebuje chwili po starcie
JPEG_QUALITY = 95
OUT_ROOT = Path.home() / "dataset" / "raw"


def parse_args():
    p = argparse.ArgumentParser(description="Zbieranie zdjęć z kamery do zbioru danych")
    p.add_argument("--tag", required=True,
                   help="co jest w sesji: bottle, missing_cap, fallen, mixed, empty")
    p.add_argument("--count", type=int, default=100, help="ile zdjęć zapisać")
    p.add_argument("--interval", type=float, default=1.5, help="sekundy między zdjęciami")
    p.add_argument("--start-delay", type=float, default=5.0,
                   help="sekundy na przygotowanie sceny przed pierwszym zdjęciem")
    p.add_argument("--no-preview", action="store_true", help="bez strumienia do VLC")
    p.add_argument("--host", default=LAPTOP_IP, help="IP laptopa dla podglądu")
    return p.parse_args()


def build_pipeline(preview, host, port):
    """Opis potoku GStreamera dla cv2.VideoCapture(..., cv2.CAP_GSTREAMER)."""
    src = (
        "v4l2src device={dev} "
        "! video/x-raw,format=YUY2,width={w},height={h},framerate={f}/1 "
        "! tee name=t "
    ).format(dev=DEVICE, w=WIDTH, h=HEIGHT, f=FPS)

    # Gałąź do OpenCV: konwersja YUYV -> BGR, zawsze tylko najnowsza klatka.
    to_opencv = (
        "t. ! queue ! videoconvert ! video/x-raw,format=BGR "
        "! appsink drop=true max-buffers=1 sync=false"
    )
    if not preview:
        return src + to_opencv

    # Gałąź podglądu: ten sam potok co w E1-01 (sprzętowy koder H.264).
    to_vlc = (
        "t. ! queue ! nvvidconv ! video/x-raw(memory:NVMM),format=I420 "
        "! nvv4l2h264enc insert-sps-pps=1 iframeinterval=30 bitrate=4000000 "
        "! h264parse ! rtph264pay config-interval=1 pt=96 "
        "! udpsink host={host} port={port} sync=false "
    ).format(host=host, port=port)
    return src + to_vlc + to_opencv


def set_white_balance(kelvin):
    """Ustawienia v4l2 znikają po restarcie, więc ustawiamy je przy każdym starcie."""
    subprocess.run(
        ["v4l2-ctl", "-d", DEVICE,
         "-c", "white_balance_temperature_auto=0",
         "-c", "white_balance_temperature={}".format(kelvin)],
        check=True,
    )


def write_session_info(out_dir, args, pipeline):
    """Metadane sesji: po miesiącu wiadomo, w jakich warunkach powstały zdjęcia."""
    lines = [
        "start: {}".format(datetime.datetime.now().isoformat(timespec="seconds")),
        "tag: {}".format(args.tag),
        "count: {}".format(args.count),
        "interval_s: {}".format(args.interval),
        "resolution: {}x{} @ {} fps".format(WIDTH, HEIGHT, FPS),
        "white_balance_K: {}".format(WB_KELVIN),
        "pipeline: {}".format(pipeline),
    ]
    (out_dir / "session.txt").write_text("\n".join(lines) + "\n")


def main():
    args = parse_args()

    session = "{}_{}".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), args.tag)
    out_dir = OUT_ROOT / session
    out_dir.mkdir(parents=True, exist_ok=True)

    pipeline = build_pipeline(not args.no_preview, args.host, PREVIEW_PORT)
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        print("BŁĄD: nie udało się otworzyć kamery. Czy inny proces jej nie trzyma?")
        print("      sprawdź: sudo fuser -v {}".format(DEVICE))
        sys.exit(1)

    try:
        set_white_balance(WB_KELVIN)
        write_session_info(out_dir, args, pipeline)

        # Rozgrzewka: czytamy klatki, aż ekspozycja się ustabilizuje.
        t_end = time.time() + WARMUP_S
        while time.time() < t_end:
            cap.read()

        print("Sesja: {}".format(out_dir))
        print("Pierwsze zdjęcie za {:.0f} s. Ctrl+C kończy.".format(args.start_delay))
        next_shot = time.time() + args.start_delay
        saved = 0

        while saved < args.count:
            ok, frame = cap.read()      # czytamy ciągle, żeby mieć zawsze świeżą klatkę
            if not ok:
                print("BŁĄD: brak klatki z kamery")
                break
            if time.time() < next_shot:
                continue

            name = "{}_{:04d}.jpg".format(session, saved)
            cv2.imwrite(str(out_dir / name), frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            saved += 1
            print("[{:3d}/{}] {}  -> przestaw butelki".format(saved, args.count, name))
            next_shot = time.time() + args.interval

    except KeyboardInterrupt:
        print("\nPrzerwano.")
    finally:
        cap.release()               # zwalnia kamerę (bez tego: "Device is busy")

    n = len(list(out_dir.glob("*.jpg")))
    print("Zapisano {} zdjęć w {}".format(n, out_dir))


if __name__ == "__main__":
    main()
