#!/usr/bin/env python3
"""E4-02/E4-03: usługa diagnostyki – postoje linii z przyczyną i dowodami, zapis w tabeli stop_event.

Laptop, kontener `diag` z infra/docker-compose.yml (albo ręcznie: python diag/diag.py --once).

Dlaczego odpytywanie bazy co POLL_S sekund, a nie reakcja na wiadomość MQTT:
- Dane z przerwy (kolejka brokera, E4-01) docierają do bazy z opóźnieniem i nie po kolei. Każdy przebieg liczy
  postoje od nowa z historii i zapisuje je idempotentnie (UPSERT po t_start), więc spóźnione dane same
  poprawiają wynik w następnym przebiegu, a restart usługi niczego nie gubi i niczego nie dubluje.
- Pierwszy przebieg po starcie odtwarza postoje z ostatniej doby (dane z etapu 3) – bez osobnego skryptu.
Koszt: opóźnienie do POLL_S sekund – dla diagnostyki postoju bez znaczenia.

Zakres przebiegu: od MIN(teraz − HORIZON_H, początek najstarszego trwającego postoju) – tak trwający postój,
starszy niż horyzont, też zostanie zamknięty, gdy linia wróci do Execute.
"""
import argparse
import datetime
import os
import time

import psycopg
from psycopg.types.json import Jsonb

from rules import WINDOW_S, classify, pick_clip

try:                                      # E4-08: kondycja napędu – opcjonalna, gdy brak modelu albo onnxruntime
    from drive_health import DriveHealth
except ImportError as e:
    DriveHealth = None
    print("Napęd: wyłączony ({})".format(e), flush=True)
from stops import STATE_NAMES, find_stops, merge_stops

DB_DSN = os.environ.get("DB_DSN", "postgresql://linesight:linesight@localhost:5432/linesight")
POLL_S = float(os.environ.get("POLL_S", "5"))
HORIZON_H = float(os.environ.get("HORIZON_H", "24"))
# E4-04: klipy udostępnia Jetson (python3 -m http.server 8080 w ~/linesight_clips)
CLIP_URL = os.environ.get("CLIP_URL", "http://192.168.0.124:8080/")
# E4-08: model kondycji napędu (anomaly/model.py) – katalog models/ podmontowany do kontenera
DRIVE_MODEL = os.environ.get("DRIVE_MODEL", "models/drive_ae.onnx")

SQL_SINCE = """
    SELECT LEAST(now() - make_interval(secs => %s),
                 (SELECT min(t_start) FROM stop_event WHERE t_end IS NULL) - interval '1 second')
"""
# Stan tuż przed początkiem zakresu (ostatnia zmiana przed `since`) – żeby wiedzieć, czy linia była w Execute.
SQL_INITIAL = """
    SELECT value FROM plc_signal
     WHERE name = 'iStateCurrent' AND time <= %(since)s AND time > %(since)s - interval '7 days'
       AND value IS NOT NULL      -- 16.11: NULL (zła jakość OPC UA przy restarcie PLC) tuż przed granicą horyzontu dawał
                                  -- initial = None -> postój po granicy nie był wykryty, a DELETE_STALE go usuwał
     ORDER BY time DESC LIMIT 1
"""
SQL_CHANGES = """
    SELECT time, value FROM plc_signal
     WHERE name = 'iStateCurrent' AND time > %(since)s
     ORDER BY time
"""
# Kod przyczyny z PLC: ostatnia wartość iStopReason najpóźniej 1 s po początku postoju. PLC ustawia kod
# i stan w tym samym cyklu, ale most nadaje czas każdej zmiennej osobno (różnice rzędu milisekund).
SQL_REASON = """
    SELECT value::int FROM plc_signal
     WHERE name = 'iStopReason' AND time <= %(t)s + interval '1 second' AND time > %(t)s - interval '1 day'
     ORDER BY time DESC LIMIT 1
"""
SQL_SIGNALS = "SELECT time, name, value FROM signals_before(%(t)s, make_interval(secs => %(w)s))"
# Kamera: od 30 s przed postojem (najwcześniej od końca poprzedniego postoju) do 10 s po
# (klasa ustalana ok. 5 s po przecięciu linii, czas = t_cross).
SQL_VISION = """
    SELECT time, class, clip FROM vision_event
     WHERE time > GREATEST(%(t)s - make_interval(secs => %(w)s), %(prev_end)s) AND time <= %(t)s + interval '10 seconds'
     ORDER BY time
"""
# Źródło (plc / vision) bez połączenia w oknie (albo przed oknem i nie wróciło) – jego dane są niepełne.
SQL_OFFLINE = """
    SELECT coalesce(bool_or(NOT online), false) FROM (
        (SELECT online FROM link_status WHERE source = %(src)s AND time <= %(t)s - make_interval(secs => %(w)s)
          ORDER BY time DESC LIMIT 1)
        UNION ALL
        (SELECT online FROM link_status WHERE source = %(src)s
          AND time > %(t)s - make_interval(secs => %(w)s) AND time <= %(t)s)) x
"""
SQL_UPSERT = """
    INSERT INTO stop_event (t_start, t_end, state, stop_reason, cause, confidence, evidence, clip)
    VALUES (%(t_start)s, %(t_end)s, %(state)s, %(stop_reason)s, %(cause)s, %(confidence)s, %(evidence)s, %(clip)s)
    ON CONFLICT (t_start) DO UPDATE
       SET t_end = EXCLUDED.t_end, state = EXCLUDED.state, stop_reason = EXCLUDED.stop_reason,
           cause = EXCLUDED.cause, confidence = EXCLUDED.confidence, evidence = EXCLUDED.evidence,
           clip = EXCLUDED.clip, updated = now()
     WHERE (stop_event.t_end, stop_event.state, stop_event.stop_reason, stop_event.cause,
            stop_event.confidence, stop_event.evidence, stop_event.clip)
           IS DISTINCT FROM (EXCLUDED.t_end, EXCLUDED.state, EXCLUDED.stop_reason, EXCLUDED.cause,
                             EXCLUDED.confidence, EXCLUDED.evidence, EXCLUDED.clip)
    RETURNING (xmax = 0) AS inserted
"""
# Postoje z zakresu, których już nie ma w wyniku (np. połączone z poprzednim) – usuwamy.
SQL_DELETE_STALE = "DELETE FROM stop_event WHERE t_start > %(since)s AND NOT (t_start = ANY(%(keep)s)) RETURNING t_start"


def fmt(t):
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t else "trwa"


def diagnose(conn, s, prev_end=None):
    """Uzupełnia postój o kod PLC, przyczynę, pewność i dowody (E4-03). prev_end: koniec poprzedniego postoju."""
    p = {"t": s["t_start"], "w": WINDOW_S, "prev_end": prev_end or s["t_start"] - datetime.timedelta(days=1)}
    row = conn.execute(SQL_REASON, p).fetchone()
    s["stop_reason"] = row[0] if row else None
    signals = conn.execute(SQL_SIGNALS, p).fetchall()
    vision = conn.execute(SQL_VISION, p).fetchall()
    plc_off = conn.execute(SQL_OFFLINE, dict(p, src="plc")).fetchone()[0]
    cam_off = conn.execute(SQL_OFFLINE, dict(p, src="vision")).fetchone()[0]
    s["cause"], s["confidence"], evidence = classify(s, s["t_start"], signals, vision, plc_off, cam_off)
    picked = pick_clip(vision, s["t_start"], s["cause"])
    s["clip"] = CLIP_URL + picked[0] if picked else None
    evidence["clip_at_s"] = picked[1] if picked else None      # klip względem początku postoju
    s["evidence"] = Jsonb(evidence)
    return s


def run_once(conn):
    """Jeden przebieg: historia stanu -> postoje -> przyczyny -> UPSERT. Zwraca (postoje, nowe, zmienione)."""
    since = conn.execute(SQL_SINCE, (HORIZON_H * 3600,)).fetchone()[0]
    row = conn.execute(SQL_INITIAL, {"since": since}).fetchone()
    initial = int(row[0]) if row and row[0] is not None else None
    changes = [(t, int(v) if v is not None else None)
               for t, v in conn.execute(SQL_CHANGES, {"since": since})]
    stops, prev_end = [], None
    for s in merge_stops(find_stops(changes, initial)):
        stops.append(diagnose(conn, s, prev_end))
        prev_end = s["t_end"]
    new = changed = 0
    with conn.transaction():
        for (t_del,) in conn.execute(SQL_DELETE_STALE, {"since": since, "keep": [s["t_start"] for s in stops]}):
            print("USUNIĘTY postój {} (połączony z poprzednim)".format(fmt(t_del)), flush=True)
        for s in stops:
            res = conn.execute(SQL_UPSERT, s).fetchone()
            if res is None:            # bez zmian
                continue
            inserted = res[0]
            new += inserted
            changed += not inserted
            print("{} postój {} – {}, stany {}, kod PLC {} -> {} ({})".format(
                "NOWY  " if inserted else "ZMIANA", fmt(s["t_start"]), fmt(s["t_end"]),
                "+".join("{} {}".format(x, STATE_NAMES.get(x, "?")) for x in s["states"]),
                s["stop_reason"], s["cause"], s["confidence"]) + (", klip " + s["clip"] if s["clip"] else ""),
                  flush=True)
    return len(stops), new, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="jeden przebieg i koniec (test, odtworzenie historii)")
    args = ap.parse_args()
    conn = None
    drive = None
    if DriveHealth is not None and os.path.exists(DRIVE_MODEL):
        drive = DriveHealth(DRIVE_MODEL, os.path.splitext(DRIVE_MODEL)[0] + ".json")
    elif DriveHealth is not None:
        print("Napęd: brak modelu {} – kondycja napędu wyłączona".format(DRIVE_MODEL), flush=True)
    while True:
        try:
            if conn is None or conn.closed:
                conn = psycopg.connect(DB_DSN, autocommit=True, connect_timeout=5)
                print("DB: połączono, horyzont {} h, co {} s".format(HORIZON_H, POLL_S), flush=True)
            n, new, changed = run_once(conn)
            if drive is not None:
                try:
                    drive.run_once(conn)
                except psycopg.OperationalError:
                    raise
                except Exception as e:            # błąd modelu nie może zatrzymać diagnostyki postojów
                    print("Napęd: błąd ({}: {})".format(type(e).__name__, e), flush=True)
            if args.once:
                print("Postoje w zakresie: {}, nowe: {}, zmienione: {}".format(n, new, changed))
                return
        except psycopg.OperationalError as e:      # baza niedostępna – ponawiamy
            print("DB: błąd ({}), ponawiam".format(str(e).strip().splitlines()[0]), flush=True)
            conn = None
            if args.once:
                raise
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
