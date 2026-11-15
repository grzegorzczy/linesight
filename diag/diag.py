#!/usr/bin/env python3
"""E4-02: usługa diagnostyki – wyznacza postoje linii z bazy i zapisuje je w tabeli stop_event.

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

from stops import STATE_NAMES, find_stops

DB_DSN = os.environ.get("DB_DSN", "postgresql://linesight:linesight@localhost:5432/linesight")
POLL_S = float(os.environ.get("POLL_S", "5"))
HORIZON_H = float(os.environ.get("HORIZON_H", "24"))

SQL_SINCE = """
    SELECT LEAST(now() - make_interval(secs => %s),
                 (SELECT min(t_start) FROM stop_event WHERE t_end IS NULL) - interval '1 second')
"""
# Stan tuż przed początkiem zakresu (ostatnia zmiana przed `since`) – żeby wiedzieć, czy linia była w Execute.
SQL_INITIAL = """
    SELECT value FROM plc_signal
     WHERE name = 'iStateCurrent' AND time <= %(since)s AND time > %(since)s - interval '7 days'
     ORDER BY time DESC LIMIT 1
"""
SQL_CHANGES = """
    SELECT time, value FROM plc_signal
     WHERE name = 'iStateCurrent' AND time > %(since)s
     ORDER BY time
"""
# Kod przyczyny z PLC: ostatnia wartość iStopReason najpóźniej 1 s po początku postoju. PLC ustawia kod
# i stan w tym samym cyklu, ale most nadaje czas każdej zmiennej osobno (różnice rzędu milisekund).
SQL_UPSERT = """
    INSERT INTO stop_event (t_start, t_end, state, stop_reason)
    VALUES (%(t_start)s, %(t_end)s, %(state)s,
            (SELECT value::int FROM plc_signal
              WHERE name = 'iStopReason' AND time <= %(t_start)s + interval '1 second'
                AND time > %(t_start)s - interval '1 day'
              ORDER BY time DESC LIMIT 1))
    ON CONFLICT (t_start) DO UPDATE
       SET t_end = EXCLUDED.t_end, state = EXCLUDED.state, stop_reason = EXCLUDED.stop_reason, updated = now()
     WHERE (stop_event.t_end, stop_event.state, stop_event.stop_reason)
           IS DISTINCT FROM (EXCLUDED.t_end, EXCLUDED.state, EXCLUDED.stop_reason)
    RETURNING (xmax = 0) AS inserted, stop_reason
"""


def fmt(t):
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t else "trwa"


def run_once(conn):
    """Jeden przebieg: historia stanu -> postoje -> UPSERT. Zwraca (liczba postojów, nowe, zmienione)."""
    since = conn.execute(SQL_SINCE, (HORIZON_H * 3600,)).fetchone()[0]
    row = conn.execute(SQL_INITIAL, {"since": since}).fetchone()
    initial = int(row[0]) if row and row[0] is not None else None
    changes = [(t, int(v) if v is not None else None)
               for t, v in conn.execute(SQL_CHANGES, {"since": since})]
    stops = find_stops(changes, initial)
    new = changed = 0
    with conn.transaction():
        for s in stops:
            res = conn.execute(SQL_UPSERT, s).fetchone()
            if res is None:            # bez zmian
                continue
            inserted, reason = res
            new += inserted
            changed += not inserted
            print("{} postój {} – {}, stan {} ({}), kod PLC {}".format(
                "NOWY  " if inserted else "ZMIANA", fmt(s["t_start"]), fmt(s["t_end"]), s["state"],
                STATE_NAMES.get(s["state"], "?"), reason), flush=True)
    return len(stops), new, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="jeden przebieg i koniec (test, odtworzenie historii)")
    args = ap.parse_args()
    conn = None
    while True:
        try:
            if conn is None or conn.closed:
                conn = psycopg.connect(DB_DSN, autocommit=True, connect_timeout=5)
                print("DB: połączono, horyzont {} h, co {} s".format(HORIZON_H, POLL_S), flush=True)
            n, new, changed = run_once(conn)
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
