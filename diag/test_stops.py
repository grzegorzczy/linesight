"""Testy find_stops. Uruchomienie: python diag/test_stops.py (albo pytest)."""
from stops import find_stops


def t(s):          # czas jako liczba sekund – funkcja nie zależy od typu czasu, tylko od kolejności
    return float(s)


def test_zator():
    stops = find_stops([(t(0), 6), (t(10), 11), (t(25), 6)], initial=None)
    assert stops == [{"t_start": 10.0, "t_end": 25.0, "state": 11}]


def test_operator_caly_lancuch_to_jeden_postoj():
    ch = [(t(0), 6), (t(5), 7), (t(6), 2), (t(20), 15), (t(21), 4), (t(30), 3), (t(31), 6)]
    assert find_stops(ch) == [{"t_start": 5.0, "t_end": 31.0, "state": 7}]


def test_awaria_i_drugi_postoj():
    ch = [(t(0), 6), (t(5), 8), (t(6), 9), (t(40), 1), (t(41), 2), (t(50), 15), (t(51), 4), (t(52), 3),
          (t(53), 6), (t(60), 5), (t(70), 6)]
    assert find_stops(ch) == [{"t_start": 5.0, "t_end": 53.0, "state": 8},
                              {"t_start": 60.0, "t_end": 70.0, "state": 5}]


def test_powtorzona_wartosc_nie_jest_zmiana():
    ch = [(t(0), 6), (t(3), 6), (t(10), 11), (t(12), 11), (t(25), 6), (t(26), 6)]
    assert find_stops(ch) == [{"t_start": 10.0, "t_end": 25.0, "state": 11}]


def test_postoj_trwa():
    assert find_stops([(t(0), 6), (t(10), 5)]) == [{"t_start": 10.0, "t_end": None, "state": 5}]


def test_stan_poczatkowy_execute():
    assert find_stops([(t(10), 11), (t(20), 6)], initial=6) == [{"t_start": 10.0, "t_end": 20.0, "state": 11}]


def test_start_poza_execute_to_nie_postoj():
    assert find_stops([(t(0), 2), (t(5), 15), (t(6), 4), (t(7), 3), (t(8), 6)]) == []


def test_brak_wartosci_pomijany():
    assert find_stops([(t(0), 6), (t(5), None), (t(10), 11), (t(20), 6)]) == \
        [{"t_start": 10.0, "t_end": 20.0, "state": 11}]


if __name__ == "__main__":
    tests = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for f in tests:
        f()
        print("OK ", f.__name__)
    print("{} testów zaliczonych".format(len(tests)))
