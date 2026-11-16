"""E4-02: wykrywanie postojów z historii stanu PackML. Czysta logika, bez bazy – testy w test_stops.py.

Postój = od wyjścia ze stanu Execute (6) do powrotu do Execute. Jeden postój obejmuje cały łańcuch stanów,
np. Stopping -> Stopped -> Resetting -> Idle -> Starting -> Execute; zapamiętujemy pierwszy stan po Execute,
bo on mówi, co zatrzymało linię (Held = zator, Suspended = brak produktu, Aborting = awaria, Stopping = operator).
"""
EXECUTE = 6
# Stany, które same mówią o przyczynie. Przejście między nimi w trakcie postoju (bez Execute pomiędzy) to druga
# przyczyna: 16.11, E5 – Held -> Suspended; PLC był w Execute tylko jeden cykl zadania (200 ms), most go nie
# zobaczył, więc zamiast dwóch postojów do połączenia był jeden z samym Held, a brak produktu zginął.
CAUSE_STATES = {5, 7, 8, 11}
STATE_NAMES = {1: "Clearing", 2: "Stopped", 3: "Starting", 4: "Idle", 5: "Suspended", 6: "Execute",
               7: "Stopping", 8: "Aborting", 9: "Aborted", 11: "Held", 15: "Resetting"}


def find_stops(changes, initial=None):
    """changes: [(czas, stan)] rosnąco wg czasu; initial: stan przed pierwszą zmianą (None = nieznany).

    Zwraca [{"t_start", "t_end", "state"}]; t_end = None, gdy postój trwa. Gdy w trakcie postoju linia przeszła
    do innego stanu z CAUSE_STATES, postój ma też pole "inner": [kolejne takie stany].
    Powtórzona wartość (most po ponownym połączeniu wysyła bieżący stan jeszcze raz) nie jest zmianą.
    Gdy linia na początku danych nie jest w Execute, ten okres nie jest postojem – nie wiemy, kiedy się zaczął.
    """
    stops, prev, current = [], initial, None
    for t, state in changes:
        if state is None or state == prev:
            continue
        if prev == EXECUTE:                       # wyjście z Execute: początek postoju
            current = {"t_start": t, "t_end": None, "state": state}
            stops.append(current)
        elif state == EXECUTE and current is not None:   # powrót do Execute: koniec postoju
            current["t_end"] = t
            current = None
        elif current is not None and state in CAUSE_STATES:   # druga przyczyna bez powrotu do Execute
            seen = [current["state"]] + current.get("inner", [])
            if state != seen[-1]:
                current.setdefault("inner", []).append(state)
        prev = state
    return stops


def merge_stops(stops, min_run_s=2.0):
    """Łączy postoje, między którymi linia pracowała krócej niż min_run_s sekund.

    Przykład z 14.11: Held do 17:02:33.131, Suspended od 17:02:33.328 – jeden cykl zadania (200 ms) w Execute.
    Dla operatora to jeden postój z dwiema przyczynami. Wynik ma pole "states": wszystkie pierwsze stany po kolei.
    Czasy muszą obsługiwać odejmowanie (datetime albo liczby); różnica datetime -> timedelta.
    """
    merged = []
    for s in stops:
        s = dict(s, states=[s["state"]] + s.get("inner", []))
        prev = merged[-1] if merged else None
        if prev is not None and prev["t_end"] is not None:
            gap = s["t_start"] - prev["t_end"]
            gap = gap.total_seconds() if hasattr(gap, "total_seconds") else gap
            if gap < min_run_s:
                prev["t_end"] = s["t_end"]
                prev["states"].extend(s["states"])
                continue
        merged.append(s)
    return merged
