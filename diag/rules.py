"""E4-03: przyczyna postoju z reguł. Czysta logika, bez bazy – testy w test_rules.py.

Wejście (zebrane przez diag.py z bazy):
- stop: {"state", "states", "stop_reason"} – pierwszy stan po Execute i kod iStopReason z PLC,
- signals: [(czas, nazwa, wartość)] z signals_before(t_start, 30 s) – wartość każdej zmiennej na początku okna
  i wszystkie zmiany w oknie,
- vision: [(czas t_cross, klasa[, klip])] zdarzenia z kamery od t_start − 30 s do t_start + 10 s,
- plc_offline: czy most zgłaszał brak połączenia z PLC w oknie,
- camera_offline: czy Jetson zgłaszał brak połączenia w oknie – wtedy „kamera nic nie widziała” nic nie znaczy.
Okno kamery zaczyna się najwcześniej na końcu poprzedniego postoju (diag.py): przewrócona butelka, która
wyjaśniła poprzedni zator, nie może potwierdzić kolejnego (test 15.11, scenariusz B 19 s po A).

Wyjście: (przyczyna, pewność, dowody). Pewność mówi, czy kamera potwierdza kod PLC:
- "potwierdzona"  – kamera widziała to, co PLC zgłasza (np. przewróconą butelkę przed zatorem),
- "tylko_plc"     – kamera nic nie wnosi (awaria, operator) albo nic nie widziała,
- "sprzeczna"     – kamera przeczy kodowi PLC (np. „brak produktu”, a butelki dalej płyną).

Zmienne xInj* (wstrzyknięte awarie) NIE są wejściem reguł: to „prawda” symulacji, służy tylko do oceny
trafności (w prawdziwym zakładzie jej nie ma). Trafiają do dowodów w osobnym polu "sim".
"""
WINDOW_S = 30
NO_PRODUCT_S = 10       # brak produktu potwierdzony, gdy kamera nie widziała żadnej butelki przez tyle sekund
CAUSE_BY_REASON = {101: "zator", 201: "brak_produktu", 301: "awaria", 302: "awaria", 1: "operator"}
CAUSE_BY_STATE = {11: "zator", 5: "brak_produktu", 8: "awaria", 7: "operator"}
KNOWN_STATES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 15}


def _secs(d):
    return d.total_seconds() if hasattr(d, "total_seconds") else float(d)


def classify(stop, t_start, signals, vision, plc_offline=False, camera_offline=False):
    """Zwraca (przyczyna, pewność, dowody: dict gotowy do JSON)."""
    # --- dowody z PLC: przebieg sygnałów w oknie
    first, last = {}, {}
    for t, name, value in signals:
        first.setdefault(name, value)
        last[name] = value
    pieces = None
    if "udiProdProcessed" in first:
        pieces = int(last["udiProdProcessed"] - first["udiProdProcessed"])
    # --- dowody z kamery: ile czego i kiedy względem początku postoju (ujemne = przed postojem)
    rel = [(round(_secs(v[0] - t_start), 1), v[1]) for v in vision]
    counts = {}
    for _, cls in rel:
        counts[cls] = counts.get(cls, 0) + 1
    before = [r for r, _ in rel if r <= 0]
    fallen = [r for r, c in rel if c == "fallen"]
    last_item_s = -max(before) if before else None          # ile sekund przed postojem przeszła ostatnia sztuka
    evidence = {
        "plc": {"states": stop.get("states", [stop["state"]]), "stop_reason": stop["stop_reason"],
                "pieces_in_window": pieces, "cycle_ms": last.get("udiCycleTime_ms"),
                "offline_in_window": plc_offline},
        "vision": {"counts": counts, "fallen_at_s": fallen, "last_item_s_before": last_item_s,
                   "offline_in_window": camera_offline},
        "window_s": WINDOW_S,
        "sim": {k: v for k, v in last.items() if k.startswith("xInj") and v},   # tylko do oceny
    }

    # --- reguły, od najmocniejszych
    if stop["state"] not in KNOWN_STATES:      # np. 0 po wgraniu programu: zmienne PLC wyzerowane
        return "restart_plc", "tylko_plc", evidence
    cause = CAUSE_BY_REASON.get(stop["stop_reason"]) or CAUSE_BY_STATE.get(stop["state"], "nieznana")
    if len(evidence["plc"]["states"]) > 1:
        evidence["secondary"] = [CAUSE_BY_STATE.get(s, "nieznana") for s in evidence["plc"]["states"][1:]]

    if plc_offline:                            # luka w danych z PLC: nie ufamy kolejności zdarzeń
        return cause, "tylko_plc", evidence
    if camera_offline:                         # brak zdarzeń z kamery nie jest dowodem (test 15.11, 08:47)
        evidence["note"] = "kamera offline w oknie"
        return cause, "tylko_plc", evidence
    if cause == "zator":
        return cause, ("potwierdzona" if fallen else "tylko_plc"), evidence
    if cause == "brak_produktu":
        if last_item_s is None or last_item_s >= NO_PRODUCT_S:
            return cause, "potwierdzona", evidence
        return cause, "sprzeczna", evidence    # kamera widziała sztukę tuż przed postojem
    if fallen and cause != "zator":            # kamera widzi przewróconą butelkę, PLC mówi co innego
        evidence["note"] = "kamera: przewrócona butelka w oknie"
    return cause, "tylko_plc", evidence


CLASS_FOR_CAUSE = {"zator": "fallen"}


def pick_clip(vision, t_start, cause):
    """E4-04: klip do postoju. vision: [(czas, klasa, klip lub None)]. Zwraca (klip, sekundy względem postoju) albo None.

    Klipy powstają tylko dla wad (missing_cap, fallen). Pierwszeństwo: klasa pasująca do przyczyny (przewrócona
    butelka przy zatorze), potem zdarzenie najbliższe początkowi postoju, przy remisie wcześniejsze (przyczyna
    poprzedza skutek). Brak klipu to informacja (kamera nie widziała wady), nie błąd.
    """
    cands = [(_secs(v[0] - t_start), v[1], v[2]) for v in vision if len(v) > 2 and v[2]]
    if not cands:
        return None
    want = CLASS_FOR_CAUSE.get(cause)
    best = min(cands, key=lambda c: (c[1] != want, abs(c[0]), c[0] > 0))
    return best[2], round(best[0], 1)
