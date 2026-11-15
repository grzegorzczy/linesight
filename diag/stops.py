"""E4-02: wykrywanie postojów z historii stanu PackML. Czysta logika, bez bazy – testy w test_stops.py.

Postój = od wyjścia ze stanu Execute (6) do powrotu do Execute. Jeden postój obejmuje cały łańcuch stanów,
np. Stopping -> Stopped -> Resetting -> Idle -> Starting -> Execute; zapamiętujemy pierwszy stan po Execute,
bo on mówi, co zatrzymało linię (Held = zator, Suspended = brak produktu, Aborting = awaria, Stopping = operator).
"""
EXECUTE = 6
STATE_NAMES = {1: "Clearing", 2: "Stopped", 3: "Starting", 4: "Idle", 5: "Suspended", 6: "Execute",
               7: "Stopping", 8: "Aborting", 9: "Aborted", 11: "Held", 15: "Resetting"}


def find_stops(changes, initial=None):
    """changes: [(czas, stan)] rosnąco wg czasu; initial: stan przed pierwszą zmianą (None = nieznany).

    Zwraca [{"t_start", "t_end", "state"}]; t_end = None, gdy postój trwa.
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
        prev = state
    return stops
