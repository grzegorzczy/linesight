"""E5-04: kontekst konkretnego postoju – deterministycznie z SQL, bez wyszukiwania wektorowego.

Pytanie o konkretny postój ("dlaczego linia stanęła o 13:03?") ma jedną poprawną odpowiedź w bazie: wiersz
stop_event. Szukanie go embeddingami byłoby gorsze (odległości wektorów prawie nie zależą od godziny), więc:
czas z pytania -> postój z SQL -> trzy źródła z identyfikatorami, które LLM cytuje:
  [P1] postój: przyczyna, pewność, dowody, klip (ten sam opis co w bazie przypadków),
  [P2] sygnały PLC z 30 s przed postojem (funkcja signals_before z etapu 4),
  [P3] kondycja napędu przed postojem (drive_health).

    python assistant/context.py "dlaczego linia stanęła o 10:23?"
    python assistant/context.py "why did the line stop at 10:23 on 15.11?"
    python assistant/context.py "ostatni postój"
"""
import re
import sys
from datetime import datetime, timedelta, timezone

from kb import STATE, TZ, case_text, connect

MATCH_S = 120   # postój pasuje do godziny z pytania, gdy trwał w chwili ± 2 min (ludzie podają czas „mniej więcej”)

RE_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)(?:[:.]([0-5]\d))?\b")
RE_DATE = re.compile(r"\b([0-2]?\d|3[01])\.(0?[1-9]|1[0-2])(?:\.(\d{4}))?\b")


def parse_when(question, now=None):
    """Godzina (i opcjonalnie data dd.mm[.rrrr]) z pytania -> datetime w strefie Europe/Warsaw albo None.

    Bez daty: dziś, a gdy ta godzina jeszcze nie nadeszła – wczoraj. Najpierw szukamy daty i wycinamy ją z tekstu,
    bo "15.11" pasuje też do wzorca godziny (15:11).
    """
    now = now or datetime.now(TZ)
    q, day = question, now.date()
    m = RE_DATE.search(q)
    if m and (":" in q or m.group(3)):          # "15.11" bez dwukropka w pytaniu traktujemy jako datę tylko z rokiem
        day = day.replace(year=int(m.group(3) or day.year), month=int(m.group(2)), day=int(m.group(1)))
        q = q[:m.start()] + q[m.end():]
    m = RE_TIME.search(q)
    if not m:
        return None
    t = datetime(day.year, day.month, day.day, int(m.group(1)), int(m.group(2)), int(m.group(3) or 0), tzinfo=TZ)
    if t > now and not RE_DATE.search(question):
        t -= timedelta(days=1)
    return t


SQL_AT = """
    SELECT t_start, t_end, state, stop_reason, cause, confidence, evidence, clip FROM stop_event
     WHERE t_start <= %(t)s + make_interval(secs => %(m)s)
       AND coalesce(t_end, now()) >= %(t)s - make_interval(secs => %(m)s)
     ORDER BY abs(extract(epoch FROM t_start - %(t)s)) LIMIT 1
"""
SQL_LAST = """SELECT t_start, t_end, state, stop_reason, cause, confidence, evidence, clip
                FROM stop_event ORDER BY t_start DESC LIMIT 1"""


def find_stop(conn, when=None):
    """Postój trwający w chwili `when` (± MATCH_S), najbliższy początkiem; bez czasu – ostatni postój."""
    if when is None:
        return conn.execute(SQL_LAST).fetchone()
    return conn.execute(SQL_AT, {"t": when, "m": MATCH_S}).fetchone()


# sygnały pokazywane LLM-owi, w tej kolejności, z jednostką; xInj* (prawda symulacji) celowo pominięte
SIGNALS = [("iStateCurrent", ""), ("iStopReason", ""), ("udiProdProcessed", " szt."), ("udiCycleTime_ms", " ms"),
           ("rMachSpeed", " szt./min"), ("rTorqueMean_Nm", " Nm"), ("rTorquePeak_Nm", " Nm"),
           ("rCurrent_A", " A"), ("rMotorTemp_C", " °C")]


def _fmt(name, v):
    if name == "iStateCurrent":
        return "{} ({})".format(STATE.get(int(v), "nieznany"), int(v))
    return "{:g}".format(round(v, 3))


def signals_text(conn, t_start, window_s=30):
    """Przebieg sygnałów PLC w oknie: wartość na początku okna, na końcu, min–max, liczba zmian."""
    rows = conn.execute("SELECT time, name, value FROM signals_before(%s, make_interval(secs => %s))",
                        (t_start, window_s)).fetchall()
    by = {}
    for _, name, v in rows:
        by.setdefault(name, []).append(v)
    out = ["Sygnały PLC w {} s przed postojem (wartość na początku okna -> w chwili postoju):".format(window_s)]
    for name, unit in SIGNALS:
        vs = by.get(name)
        if not vs:
            out.append("- {}: brak danych".format(name))
            continue
        line = "- {}: {} -> {}{}".format(name, _fmt(name, vs[0]), _fmt(name, vs[-1]), unit)
        if name not in ("iStateCurrent", "iStopReason", "udiProdProcessed") and len(vs) > 2:
            line += " (min {:g}, max {:g}, zmian {})".format(round(min(vs), 3), round(max(vs), 3), len(vs) - 1)
        if name == "iStateCurrent" and len(vs) > 1:
            line += " (przebieg: {})".format(" -> ".join(_fmt(name, v) for v in vs))
        out.append(line)
    return "\n".join(out)


SQL_DRIVE = """
    SELECT l.health, l.ratio, l.alarm, w.hmin, w.any_alarm, w.n
      FROM (SELECT min(health) AS hmin, bool_or(alarm) AS any_alarm, count(*) AS n FROM drive_health
             WHERE time > %(t)s - interval '30 minutes' AND time <= %(t)s) w
      LEFT JOIN LATERAL (SELECT health, ratio, alarm FROM drive_health
                          WHERE time <= %(t)s ORDER BY time DESC LIMIT 1) l ON true
"""


def drive_text(conn, t_start):
    h, r, a, hmin, alarm, n = conn.execute(SQL_DRIVE, {"t": t_start}).fetchone()
    if not n:
        return "Kondycja napędu: brak wyników modelu w 30 min przed postojem."
    return ("Kondycja napędu tuż przed postojem: {:.0f} % (wynik/próg {:.2f}, alarm: {}). "
            "W 30 min przed postojem: najniższa kondycja {:.0f} %, alarm wystąpił: {}, ocenionych sztuk {}.").format(
        h, r, "tak" if a else "nie", hmin, "tak" if alarm else "nie", n)


def stop_sources(conn, stop):
    """Wiersz stop_event -> [{"id", "title", "text", "url"}] do promptu i do listy źródeł w odpowiedzi."""
    t = stop[0]
    local = t.astimezone(TZ).strftime("%d.%m.%Y %H:%M:%S")
    return [
        {"id": "P1", "title": "Postój {} ({})".format(local, stop[4]), "text": case_text(stop),
         "url": stop[7], "source": "stop:" + t.astimezone(timezone.utc).isoformat()},
        {"id": "P2", "title": "Sygnały PLC przed postojem {}".format(local), "text": signals_text(conn, t),
         "url": None, "source": "plc_signal"},
        {"id": "P3", "title": "Kondycja napędu przed postojem {}".format(local), "text": drive_text(conn, t),
         "url": None, "source": "drive_health"},
    ]


def main():
    q = " ".join(sys.argv[1:]) or "ostatni postój"
    when = parse_when(q)
    conn = connect()
    stop = find_stop(conn, when)
    print("Pytanie: {}\nCzas z pytania: {}\n".format(q, when.strftime("%d.%m.%Y %H:%M:%S") if when else "brak -> ostatni postój"))
    if stop is None:
        print("Brak postoju w ± {} s od tej chwili.".format(MATCH_S))
        return
    for s in stop_sources(conn, stop):
        print("[{}] {}\n{}\n".format(s["id"], s["title"], s["text"]))


if __name__ == "__main__":
    main()
