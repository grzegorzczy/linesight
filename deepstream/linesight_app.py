#!/usr/bin/env python3
"""E2-04..E2-06: potok LineSight na Jetsonie – detekcja (nvinfer), tracking (nvtracker IOU), zliczanie sztuk,
strumień RTSP H.264 z ramkami detekcji i klipy ze zdarzeń (bufor kołowy).

Jetson, Python 3.6, DeepStream 6.0.1, pyds 1.1.1. Uruchamiać z ~/linesight/deepstream:
    python3 linesight_app.py --source /dev/video0                 # kamera na żywo, wynik do fakesink
    python3 linesight_app.py --source /tmp/raw.mp4 --out /tmp/e2-04.mp4   # nagranie testowe -> MP4 z OSD
    python3 linesight_app.py --rtsp                                 # kamera -> rtsp://<jetson>:8554/linesight
    python3 linesight_app.py --rtsp --clips                         # + klip 10 s przed / 5 s po zdarzeniu
    (--rtsp, --out i --clips można łączyć: jeden koder, tee na RTSP, MP4 i bufor kołowy)

Potok:
    źródło -> nvvideoconvert (NVMM) -> nvstreammux -> nvinfer -> nvtracker
           -> [sonda: zliczanie + rysowanie linii i liczników] -> nvdsosd -> koder H.264 -> tee -> MP4 / RTP
    RTP (rtph264pay -> udpsink 127.0.0.1:5400) odbiera wbudowany serwer RTSP (GstRtspServer, port 8554).
    Bufor kołowy (--clips): splitmuxsink tnie H.264 na kawałki po 2 s w /dev/shm (RAM) i trzyma ostatnie 15.
    Zdarzenie klasy z --clip-classes skleja (ffmpeg -c copy, bez ponownego kodowania) kawałki z okna
    [przecięcie - pre, przecięcie + post] w jeden MP4 w --clips-dir; nazwa klipu trafia do zdarzenia ("clip").

Zliczanie: przejście śladu (stałe ID z trackera) liczymy, gdy środek jego ramki przetnie pionową linię
x = --line * szerokość w kierunku taśmy (--direction). Klasa = najczęstsza klasa w śladzie
(głosowanie większościowe) ustalona --decide klatek po przecięciu, a nie klasa z pojedynczej klatki.
Zdarzenia trafiają na stdout i do pliku
JSON Lines (--events) – z nich korzystają bufor klipów (E2-06) i wysyłka MQTT (E2-07).
"""
import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import Counter

import gi
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402
import pyds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = ["bottle", "missing_cap", "fallen"]
W, H = 640, 360
TRACKER_LIB = "/opt/nvidia/deepstream/deepstream-6.0/lib/libnvds_nvmultiobjecttracker.so"
STALE_FRAMES = 90  # ślad niewidziany przez 3 s usuwamy z pamięci licznika
UNTRACKED = getattr(pyds, "UNTRACKED_OBJECT_ID", 0xFFFFFFFFFFFFFFFF)  # obiekt bez ID z trackera


def source_desc(src):
    """Kamera (/dev/videoN) albo plik MP4 z H.264 (np. z record_raw.sh) -> bufory NVMM NV12."""
    if src.startswith("/dev/video"):
        return ("v4l2src device={} extra-controls=c,white_balance_temperature_auto=0,"
                "white_balance_temperature=5500 "
                "! video/x-raw,format=YUY2,width={},height={},framerate=30/1 "
                "! nvvideoconvert ! video/x-raw(memory:NVMM),format=NV12".format(src, W, H)), True
    # plik: sprzętowy dekoder H.264 (nvv4l2decoder) od razu daje bufory NVMM
    return ("filesrc location={} ! qtdemux ! h264parse ! nvv4l2decoder "
            "! nvvideoconvert ! video/x-raw(memory:NVMM),format=NV12".format(os.path.abspath(src))), False


FPS = 30.0  # nominalne FPS kamery: przeliczenie klatek na sekundy przy wyznaczaniu chwili przecięcia
SEG_DIR = "/dev/shm/linesight"  # bufor kołowy w RAM (tmpfs): bez zużywania karty SD
SEG_S = 2  # długość kawałka; klatka I co 1 s (E2-05), więc każdy kawałek zaczyna się od klatki I
SEG_FILES = 15  # 15 x 2 s = 30 s historii (wystarcza na pre + post + zapas na zamknięcie kawałka)
UDP_PORT = 5400  # wewnętrzny port RTP: udpsink potoku -> udpsrc serwera RTSP


def encoder_desc(args, live):
    """Koniec potoku: jeden sprzętowy koder H.264 (NVENC), tee na MP4 i/lub RTP; bez wyjść -> fakesink."""
    if not args.out and not args.rtsp and not args.clips:
        return "fakesink sync=false"
    # insert-sps-pps + klatka I co 30 klatek (1 s): klient RTSP może dołączyć w dowolnej chwili
    # i po zgubionym pakiecie obraz wraca najpóźniej po 1 s.
    desc = ("nvvideoconvert ! video/x-raw(memory:NVMM),format=I420 "
            "! nvv4l2h264enc bitrate={} insert-sps-pps=1 iframeinterval=30 ! h264parse ! tee name=enc"
            ).format(args.bitrate)
    if args.out:
        desc += " enc. ! queue ! qtmux ! filesink location={}".format(args.out)
    if args.rtsp:
        # Kamera: sync=false – wysyłamy klatkę od razu (mniejsze opóźnienie). Plik: sync=true – tempo 30 FPS.
        desc += (" enc. ! queue ! rtph264pay config-interval=1 pt=96 "
                 "! udpsink host=127.0.0.1 port={} sync={} async=false").format(UDP_PORT, "false" if live else "true")
    if args.clips:
        # max-files: nazwy plików krążą (seg00000..seg00014), najstarszy kawałek jest nadpisywany
        # max-size-time 2,5 s, nie 2 s: przy klatce I co dokładnie 1 s i limicie 2 s splitmuxsink czasem
        # zamykał kawałek po 1 s (E2-06: pliki na zmianę ~0,5 i ~1 MB) i 15 plików dawało ~22 s zamiast 30 s
        desc += (" enc. ! queue ! splitmuxsink location={}/seg%05d.mp4 max-size-time={} max-files={}"
                 ).format(SEG_DIR, int((SEG_S + 0.5) * 1000000000), SEG_FILES)
    return desc


def select_segments(segments, t_start, t_end, now, seg_s=SEG_S):
    """Wybiera zamknięte kawałki bufora pokrywające okno [t_start, t_end] (czas z time.time()).

    segments: lista (ścieżka, mtime). mtime = chwila zamknięcia kawałka (mp4mux dopisuje nagłówek
    na końcu), więc kawałek obejmuje mniej więcej [mtime - seg_s, mtime]. Najnowszy plik jest jeszcze
    zapisywany (bez nagłówka moov) – pomijamy go. Zwraca ścieżki w kolejności czasu.
    """
    done = sorted(segments, key=lambda x: x[1])[:-1]
    return [p for p, m in done if m > t_start and m - seg_s < t_end and m < now]


class ClipMaker(object):
    """Klipy ze zdarzeń: czeka, aż minie `post` s (+ zamknięcie kawałka), skleja kawałki ffmpegiem."""

    def __init__(self, out_dir, classes, pre=10, post=5):
        self.out_dir, self.classes, self.pre, self.post = out_dir, classes, pre, post
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        if not os.path.isdir(SEG_DIR):
            os.makedirs(SEG_DIR)
        for f in glob.glob(os.path.join(SEG_DIR, "seg*.mp4")):  # stare kawałki zafałszowałyby czasy
            os.remove(f)
        self.pending = 0

    def on_event(self, ev):
        """Wołane przez LineCounter przed zapisem zdarzenia: dopisuje nazwę klipu i planuje jego zapis."""
        if ev["class"] not in self.classes:
            return
        # zdarzenie powstaje `decide` klatek po przecięciu linii – klip centrujemy na przecięciu
        t_cross = ev["t"] - (ev["decided_at"] - ev["frame"]) / FPS
        name = "{}_{}_id{}.mp4".format(time.strftime("%Y%m%d-%H%M%S", time.localtime(t_cross)),
                                       ev["class"], ev["track_id"])
        ev["clip"] = name
        wait = max(0.0, t_cross + self.post - time.time()) + SEG_S + 1  # + domknięcie bieżącego kawałka
        self.pending += 1
        timer = threading.Timer(wait, self._make, (name, t_cross))
        timer.daemon = True
        timer.start()

    def _make(self, name, t_cross):
        self.pending -= 1
        segs = [(f, os.path.getmtime(f)) for f in glob.glob(os.path.join(SEG_DIR, "seg*.mp4"))]
        paths = select_segments(segs, t_cross - self.pre, t_cross + self.post, time.time())
        if not paths:
            print("KLIP: brak kawałków dla", name)
            return
        lst = os.path.join(SEG_DIR, name + ".txt")
        with open(lst, "w") as f:
            f.writelines("file '{}'\n".format(p) for p in paths)
        out = os.path.join(self.out_dir, name)
        # concat demuxer + -c copy: sklejenie bez dekodowania i kodowania (ułamek sekundy, prawie 0 CPU)
        rc = subprocess.call(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                              "-i", lst, "-c", "copy", out])
        os.remove(lst)
        print("KLIP:", out if rc == 0 else "błąd ffmpeg ({})".format(rc), "({} kawałków)".format(len(paths)))


def start_rtsp_server(port, mount):
    """Serwer RTSP (GstRtspServer) w tym samym procesie: dla każdego klienta podaje pakiety RTP z UDP_PORT.

    set_shared(True): wszyscy klienci dostają ten sam strumień (bez osobnego kodowania na klienta).
    """
    gi.require_version("GstRtspServer", "1.0")
    from gi.repository import GstRtspServer
    server = GstRtspServer.RTSPServer.new()
    server.props.service = str(port)
    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_launch('( udpsrc name=pay0 port={} buffer-size=524288 caps="application/x-rtp, media=video, '
                       'clock-rate=90000, encoding-name=(string)H264, payload=96" )'.format(UDP_PORT))
    factory.set_shared(True)
    server.get_mount_points().add_factory(mount, factory)
    server.attach(None)
    return server


def build_pipeline(args):
    src, live = source_desc(args.source)
    sink = encoder_desc(args, live)
    desc = (
        "{src} ! m.sink_0 nvstreammux name=m batch-size=1 width={w} height={h} live-source={live} "
        "! nvinfer name=infer config-file-path={cfg} "
        "! nvtracker name=tracker ll-lib-file={lib} ll-config-file={trk} "
        "tracker-width=640 tracker-height=384 enable-batch-process=1 "
        "! nvvideoconvert name=post ! video/x-raw(memory:NVMM),format=RGBA "
        "! nvdsosd ! {sink}"
    ).format(src=src, w=W, h=H, live=int(live), cfg=os.path.join(HERE, "configs", "nvinfer_yolo26.txt"),
             lib=TRACKER_LIB, trk=os.path.abspath(args.tracker), sink=sink)
    return Gst.parse_launch(desc)


class LineCounter(object):
    """Liczy przejścia śladów przez pionową linię; klasa = większość głosów w śladzie.

    - `direction`: kierunek taśmy ("L->R", "R->L") albo "both". Liczymy tylko przejścia w tym
      kierunku. Ślad, który wróci na stronę wejściową, może zostać policzony ponownie
      (E2-04: ta sama butelka przesuwana tam i z powrotem to kilka przejść).
    - Przejście liczymy w chwili przecięcia linii, a klasę ustalamy `decide` klatek później
      (albo gdy ślad zniknie wcześniej): przy linii ręka często zasłania szyjkę.
    """

    def __init__(self, line_x, events_path, decide=150, direction="L->R", margin=20):
        self.line_x = line_x
        self.margin = margin  # strefa martwa ±margin px wokół linii (histereza)
        self.decide = decide
        self.direction = direction
        self.tracks = {}  # id -> votes, cx, last, pending (lista przejść czekających na klasę)
        self.counts = Counter()
        self.events = open(events_path, "a") if events_path else None
        self.n_tracks = 0
        self.on_event = None  # opcjonalnie: funkcja(ev) wołana przed zapisem zdarzenia (E2-06: klipy)

    def update(self, frame_num, objects):
        """objects: lista (track_id, class_id, cx). Zwraca listę zdarzeń zamkniętych w tej klatce."""
        new_events = []
        for tid, cls, cx in objects:
            t = self.tracks.get(tid)
            if t is None:
                t = self.tracks[tid] = {"votes": Counter(), "side": None, "last": frame_num, "pending": []}
                self.n_tracks += 1
            t["votes"][cls] += 1
            # Histereza: strona zmienia się dopiero, gdy środek ramki wyjdzie poza strefę ±margin.
            # E2-04: środek ramki leżącej butelki drgał przy linii i dawał 2-3 przejścia w 1-12 klatek.
            side = "L" if cx < self.line_x - self.margin else "R" if cx > self.line_x + self.margin else None
            if side is not None:
                if t["side"] is not None and side != t["side"]:
                    d = "L->R" if side == "R" else "R->L"
                    if self.direction in ("both", d):
                        t["pending"].append((frame_num, d))
                t["side"] = side
            t["last"] = frame_num
        for tid, t in list(self.tracks.items()):
            stale = frame_num - t["last"] > STALE_FRAMES
            while t["pending"] and (frame_num - t["pending"][0][0] >= self.decide or stale):
                new_events.append(self._close(tid, t, t["pending"].pop(0), frame_num))
            if stale:
                del self.tracks[tid]
        return new_events

    def flush(self, frame_num):
        """Koniec strumienia: zamyka przejścia policzone, a jeszcze bez ustalonej klasy."""
        for tid, t in self.tracks.items():
            while t["pending"]:
                self._close(tid, t, t["pending"].pop(0), frame_num)

    def _close(self, tid, t, crossing, frame_num):
        label = NAMES[t["votes"].most_common(1)[0][0]]
        self.counts[label] += 1
        ev = {"t": round(time.time(), 3), "frame": crossing[0], "decided_at": frame_num, "track_id": tid,
              "class": label, "direction": crossing[1],
              "votes": {NAMES[c]: n for c, n in t["votes"].items()}}
        if self.on_event:
            self.on_event(ev)
        print("ZLICZONO", json.dumps(ev))
        if self.events:
            self.events.write(json.dumps(ev) + "\n")
            self.events.flush()
        return ev

    def summary(self):
        return {"counts": {n: self.counts[n] for n in NAMES}, "total": sum(self.counts.values()),
                "tracks_seen": self.n_tracks}


def add_overlay(batch_meta, frame_meta, counter):
    """Linia zliczania i liczniki rysowane przez nvdsosd (metadane wyświetlania DeepStreama)."""
    dm = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
    dm.num_lines = 1
    ln = dm.line_params[0]
    ln.x1 = ln.x2 = int(counter.line_x)
    ln.y1, ln.y2 = 0, H - 1
    ln.line_width = 2
    ln.line_color.set(1.0, 1.0, 0.0, 1.0)
    dm.num_labels = 1
    tp = dm.text_params[0]
    c = counter.counts
    tp.display_text = "bottle {}  missing_cap {}  fallen {}".format(c["bottle"], c["missing_cap"], c["fallen"])
    tp.x_offset, tp.y_offset = 8, H - 28
    tp.font_params.font_name = "Serif"
    tp.font_params.font_size = 12
    tp.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
    tp.set_bg_clr = 1
    tp.text_bg_clr.set(0.0, 0.0, 0.0, 0.6)
    pyds.nvds_add_display_meta_to_frame(frame_meta, dm)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="/dev/video0", help="/dev/videoN albo plik .mp4 (H.264)")
    ap.add_argument("--out", help="zapis wyniku z OSD do MP4 (domyślnie brak, fakesink)")
    ap.add_argument("--rtsp", action="store_true",
                    help="strumień RTSP H.264 z OSD: rtsp://<ip_jetsona>:<--rtsp-port>/<--rtsp-mount>")
    ap.add_argument("--rtsp-port", type=int, default=8554)
    ap.add_argument("--rtsp-mount", default="/linesight")
    ap.add_argument("--bitrate", type=int, default=4000000, help="bitrate kodera H.264 w bit/s (domyślnie 4 Mbit/s)")
    ap.add_argument("--clips", action="store_true",
                    help="bufor kołowy i klipy ze zdarzeń (kamera na żywo; z pliku czasy są przybliżone)")
    ap.add_argument("--clips-dir", default=os.path.expanduser("~/linesight_clips"))
    ap.add_argument("--clip-classes", default="missing_cap,fallen",
                    help="klasy, dla których zapisujemy klip (domyślnie missing_cap,fallen)")
    ap.add_argument("--pre", type=float, default=10, help="sekundy przed przecięciem linii (domyślnie 10)")
    ap.add_argument("--post", type=float, default=5, help="sekundy po przecięciu linii (domyślnie 5)")
    ap.add_argument("--line", type=float, default=0.5, help="położenie linii zliczania, ułamek szerokości")
    ap.add_argument("--events", default="/tmp/linesight_events.jsonl", help="plik zdarzeń (JSON Lines)")
    ap.add_argument("--decide", type=int, default=150,
                    help="po ilu klatkach od przecięcia ustalić klasę (domyślnie 150 = 5 s albo zniknięcie śladu)")
    ap.add_argument("--margin", type=int, default=20,
                    help="strefa martwa wokół linii w px (histereza przeciw drganiom ramki, domyślnie 20)")
    ap.add_argument("--tracker", default=os.path.join(HERE, "configs", "tracker_iou.yml"),
                    help="plik YAML trackera (domyślnie configs/tracker_iou.yml)")
    ap.add_argument("--direction", default="L->R", choices=["L->R", "R->L", "both"],
                    help="kierunek taśmy: liczymy tylko przejścia w tym kierunku (domyślnie L->R)")
    args = ap.parse_args()

    Gst.init(None)
    pipeline = build_pipeline(args)
    server = None  # referencja musi żyć do końca programu
    if args.rtsp:
        server = start_rtsp_server(args.rtsp_port, args.rtsp_mount)
        print("RTSP: rtsp://<ip_jetsona>:{}{}".format(args.rtsp_port, args.rtsp_mount))
    counter = LineCounter(args.line * W, args.events, args.decide, args.direction, args.margin)
    clips = None
    if args.clips:
        if args.pre + args.post + 2 * SEG_S + 1 > SEG_S * (SEG_FILES - 1):
            sys.exit("--pre + --post za duże dla bufora {} s".format(SEG_S * SEG_FILES))
        clips = ClipMaker(args.clips_dir, args.clip_classes.split(","), args.pre, args.post)
        counter.on_event = clips.on_event
        print("KLIPY: bufor {} s w {}, klipy w {}".format(SEG_S * SEG_FILES, SEG_DIR, args.clips_dir))
    last_frame = [0]
    stats = {"frames": 0, "t0": None}

    def probe(pad, info, _):
        batch = pyds.gst_buffer_get_nvds_batch_meta(hash(info.get_buffer()))
        l_frame = batch.frame_meta_list
        while l_frame is not None:
            fm = pyds.NvDsFrameMeta.cast(l_frame.data)
            objects = []
            l_obj = fm.obj_meta_list
            while l_obj is not None:
                o = pyds.NvDsObjectMeta.cast(l_obj.data)
                if o.object_id != UNTRACKED:  # tylko potwierdzone ślady
                    r = o.rect_params
                    objects.append((o.object_id, o.class_id, r.left + r.width / 2.0))
                l_obj = l_obj.next
            counter.update(fm.frame_num, objects)
            last_frame[0] = fm.frame_num
            add_overlay(batch, fm, counter)
            stats["frames"] += 1
            if stats["t0"] is None:
                stats["t0"] = time.time()
            l_frame = l_frame.next
        return Gst.PadProbeReturn.OK

    # sonda za trackerem (na wejściu nvvideoconvert przed OSD): ID śladów są już nadane
    pipeline.get_by_name("post").get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, probe, None)

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(_bus, msg):
        if msg.type == Gst.MessageType.EOS:
            loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            print("BŁĄD:", err, dbg)
            loop.quit()

    bus.connect("message", on_message)
    # Ctrl+C -> EOS, żeby qtmux domknął plik MP4 (jak gst-launch -e)
    signal.signal(signal.SIGINT, lambda *_: pipeline.send_event(Gst.Event.new_eos()))

    pipeline.set_state(Gst.State.PLAYING)
    loop.run()
    pipeline.set_state(Gst.State.NULL)

    counter.flush(last_frame[0])
    s = counter.summary()
    if stats["t0"] and stats["frames"] > 1:
        s["fps"] = round((stats["frames"] - 1) / (time.time() - stats["t0"]), 1)
    s["frames"] = stats["frames"]
    print("PODSUMOWANIE", json.dumps(s))
    if clips and clips.pending:
        print("KLIPY: {} niezapisanych (program zakończony przed upływem --post)".format(clips.pending))


if __name__ == "__main__":
    main()
