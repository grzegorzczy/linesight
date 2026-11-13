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


def run(frames, decide=30, line=320):
    """frames: lista klatek, każda to lista (track_id, class_id, cx)."""
    c = app.LineCounter(line, None, decide)
    for n, objs in enumerate(frames):
        c.update(n, objs)
    c.flush(len(frames))
    return c.summary()["counts"]


def test_klasa_ustalana_po_przecieciu():
    # ręka zasłania szyjkę przy linii (missing_cap), potem widać nakrętkę (bottle)
    frames = [[(1, MISSING, x)] for x in range(200, 330, 10)] + [[(1, BOTTLE, 330 + i)] for i in range(40)]
    assert run(frames) == {"bottle": 1, "missing_cap": 0, "fallen": 0}


def test_srodek_dokladnie_na_linii():
    frames = [[(1, BOTTLE, x)] for x in (300, 310, 320, 330, 340)]
    assert run(frames)["bottle"] == 1


def test_cofniecie_nie_liczy_drugi_raz():
    frames = [[(1, FALLEN, x)] for x in (300, 330, 300, 330, 300)]
    assert run(frames)["fallen"] == 1


def test_bez_przeciecia_brak_zliczenia():
    frames = [[(1, BOTTLE, x)] for x in range(100, 300, 5)]
    assert sum(run(frames).values()) == 0


def test_dwa_slady_obok_siebie():
    frames = [[(1, BOTTLE, x), (2, MISSING, x - 60)] for x in range(250, 450, 10)]
    assert run(frames) == {"bottle": 1, "missing_cap": 1, "fallen": 0}


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK ", t.__name__)
    print("{} testów zaliczonych".format(len(tests)))
