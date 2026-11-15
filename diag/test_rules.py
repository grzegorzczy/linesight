"""Testy reguł przyczyny i łączenia postojów. Uruchomienie: python diag/test_rules.py (albo pytest)."""
from rules import classify
from stops import merge_stops

T = 1000.0   # początek postoju; czasy jako liczby sekund


def sig(*items):
    return [(T + dt, n, v) for dt, n, v in items]


def stop(state, reason, states=None):
    return {"state": state, "stop_reason": reason, "states": states or [state]}


def test_zator_potwierdzony_kamera():
    c, p, e = classify(stop(11, 101), T, sig((-30, "udiProdProcessed", 100), (-1, "udiProdProcessed", 120)),
                       [(T - 4, "fallen"), (T - 8, "bottle")])
    assert (c, p) == ("zator", "potwierdzona")
    assert e["plc"]["pieces_in_window"] == 20 and e["vision"]["fallen_at_s"] == [-4.0]


def test_zator_bez_kamery():
    assert classify(stop(11, 101), T, [], [(T - 3, "bottle")])[:2] == ("zator", "tylko_plc")


def test_brak_produktu_potwierdzony():
    assert classify(stop(5, 201), T, [], [(T - 25, "bottle")])[:2] == ("brak_produktu", "potwierdzona")


def test_brak_produktu_sprzeczny():
    assert classify(stop(5, 201), T, [], [(T - 2, "bottle")])[:2] == ("brak_produktu", "sprzeczna")


def test_awaria_i_operator():
    assert classify(stop(8, 301), T, [], [])[:2] == ("awaria", "tylko_plc")
    assert classify(stop(7, 1), T, [], [])[:2] == ("operator", "tylko_plc")


def test_restart_plc():
    assert classify(stop(0, 0), T, [], [])[:2] == ("restart_plc", "tylko_plc")


def test_offline_nie_potwierdza():
    assert classify(stop(11, 101), T, [], [(T - 4, "fallen")], plc_offline=True)[:2] == ("zator", "tylko_plc")


def test_kamera_offline_nie_potwierdza_braku_produktu():
    c, p, e = classify(stop(5, 201), T, [], [], camera_offline=True)
    assert (c, p) == ("brak_produktu", "tylko_plc") and e["note"] == "kamera offline w oknie"


def test_xinj_tylko_w_sim():
    _, _, e = classify(stop(11, 101), T, sig((-30, "xInjJam", 0.0), (0, "xInjJam", 1.0)), [])
    assert e["sim"] == {"xInjJam": 1.0}


def test_postoj_laczony_ma_druga_przyczyne():
    _, _, e = classify(stop(11, 101, [11, 5]), T, [], [])
    assert e["secondary"] == ["brak_produktu"]


def test_merge_stops():
    s = [{"t_start": 10.0, "t_end": 20.0, "state": 11}, {"t_start": 20.2, "t_end": 25.0, "state": 5},
         {"t_start": 40.0, "t_end": None, "state": 8}]
    assert merge_stops(s) == [{"t_start": 10.0, "t_end": 25.0, "state": 11, "states": [11, 5]},
                              {"t_start": 40.0, "t_end": None, "state": 8, "states": [8]}]


if __name__ == "__main__":
    tests = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for f in tests:
        f()
        print("OK ", f.__name__)
    print("{} testów zaliczonych".format(len(tests)))
