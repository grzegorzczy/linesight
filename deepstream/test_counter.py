"""Testy logiki zliczania (LineCounter) bez Jetsona: gi i pyds zastąpione atrapami.

    python deepstream/test_counter.py        (laptop albo Jetson; bez pytest)
"""
import importlib.util
import os
import sys
import types

gi = types.ModuleType("gi")
gi.require_version = lambda *a: None
repo = types.ModuleType("gi.repository")
repo.GLib = repo.Gst = None
sys.modules.update({"gi": gi, "gi.repository": repo, "pyds": types.ModuleType("pyds")})
spec = importlib.util.spec_from_file_location(
    "app", os.path.join(os.path.dirname(os.path.abspath(__file__)), "linesight_app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

BOTTLE, MISSING, FALLEN = 0, 1, 2


def run(frames, decide=30, line=320, direction="L->R", margin=20):
    """frames: lista klatek, każda to lista (track_id, class_id, cx)."""
    c = app.LineCounter(line, None, decide, direction, margin)
    for n, objs in enumerate(frames):
        c.update(n, objs)
    c.flush(len(frames))
    return c.summary()["counts"]


def test_klasa_ustalana_po_przecieciu():
    # ręka zasłania szyjkę przy linii (missing_cap), potem widać nakrętkę (bottle)
    frames = [[(1, MISSING, x)] for x in range(200, 330, 10)] + [[(1, BOTTLE, 330 + i)] for i in range(40)]
    assert run(frames) == {"bottle": 1, "missing_cap": 0, "fallen": 0}


def test_przejscie_przez_strefe_martwa():
    frames = [[(1, BOTTLE, x)] for x in (280, 300, 310, 320, 330, 345)]
    assert run(frames)["bottle"] == 1


def test_drgania_przy_linii_nie_licza_sie():
    # środek ramki skacze wokół linii w strefie ±20 px: brak przejścia
    frames = [[(1, FALLEN, x)] for x in (290, 305, 330, 315, 335, 310, 325, 300)]
    assert sum(run(frames, direction="both").values()) == 0


def test_tylko_kierunek_tasmy():
    frames = [[(1, BOTTLE, x)] for x in (400, 350, 300, 250)]  # R->L
    assert sum(run(frames).values()) == 0
    assert run(frames, direction="R->L")["bottle"] == 1


def test_tam_i_z_powrotem():
    # ta sama butelka 3x w prawo i 2x w lewo -> 3 przejścia L->R, 5 w trybie both
    frames = [[(1, FALLEN, x)] for x in (280, 360, 280, 360, 280, 360)]
    assert run(frames)["fallen"] == 3
    assert run(frames, direction="both")["fallen"] == 5


def test_bez_przeciecia_brak_zliczenia():
    frames = [[(1, BOTTLE, x)] for x in range(100, 300, 5)]
    assert sum(run(frames).values()) == 0


def test_dwa_slady_obok_siebie():
    frames = [[(1, BOTTLE, x), (2, MISSING, x - 60)] for x in range(250, 450, 10)]
    assert run(frames) == {"bottle": 1, "missing_cap": 1, "fallen": 0}


def test_wybor_kawalkow_bufora():
    # kawałki 2 s zamknięte w chwilach 100, 102, ..., 130; 130 to plik wciąż zapisywany
    segs = [("seg{}".format(i), 100.0 + 2 * i) for i in range(16)]
    # przecięcie w 115, okno [105, 120]: kawałki kończące się w 106..120 (pokrywają 104..120)
    got = app.select_segments(segs, 105, 120, now=131)
    assert got == ["seg{}".format(i) for i in range(3, 11)], got
    # najnowszy (otwarty) kawałek nigdy nie jest brany
    assert "seg15" not in app.select_segments(segs, 120, 140, now=131)


def test_zdarzenie_dostaje_nazwe_klipu():
    c = app.LineCounter(320, None, decide=3)
    c.on_event = lambda ev: ev.update(clip="x.mp4")
    for n, x in enumerate((280, 360, 360, 360, 360)):
        c.update(n, [(1, FALLEN, x)])
    assert c.counts["fallen"] == 1
    evs = []
    c.on_event = lambda ev: evs.append(ev)
    for n, x in enumerate((280, 280, 360, 360, 360, 360), start=10):
        c.update(n, [(2, BOTTLE, x)])
    assert evs and evs[0]["class"] == "bottle"


def test_czas_przeciecia():
    # klasa ustalana `decide` klatek po przecięciu: t_cross = t - decide / FPS
    evs = []
    c = app.LineCounter(320, None, decide=30)
    c.on_event = evs.append
    for n, x in enumerate([280] + [360] * 40):
        c.update(n, [(1, BOTTLE, x)])
    ev = evs[0]
    assert ev["decided_at"] - ev["frame"] == 30
    assert abs((ev["t"] - ev["t_cross"]) - 30 / app.FPS) < 0.002, ev


class FakeMqtt(object):
    """Atrapa klienta paho: zapisuje wywołania, publikacje od razu „potwierdzone”."""

    def __init__(self):
        self.calls, self.sent = [], []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a, k))

    def publish(self, topic, payload, qos=0, retain=False):
        self.sent.append((topic, payload, qos, retain))
        return types.SimpleNamespace(rc=0, is_published=lambda: True)


def test_mqtt_zdarzenie_i_status():
    import json
    fake = FakeMqtt()
    pub = app.MqttPublisher("broker", client=fake)
    names = [c[0] for c in fake.calls]
    assert "will_set" in names and "connect_async" in names and "loop_start" in names
    assert [c for c in fake.calls if c[0] == "will_set"][0][1] == ("linesight/vision/status", "offline")
    pub._on_connect(fake, None, None, 0)
    pub.publish({"class": "fallen", "track_id": 7, "clip": "x.mp4"})
    pub.close()
    assert fake.sent[0] == ("linesight/vision/status", "online", 1, True)
    topic, payload, qos, retain = fake.sent[1]
    assert (topic, qos, retain) == ("linesight/vision/events", 1, False)
    assert json.loads(payload) == {"class": "fallen", "track_id": 7, "clip": "x.mp4"}
    assert fake.sent[2] == ("linesight/vision/status", "offline", 1, True)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK ", t.__name__)
    print("{} testów zaliczonych".format(len(tests)))
