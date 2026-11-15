"""E5-03: indeksowanie bazy wiedzy w pgvector (tabela kb_chunk) i zapytanie testowe.

    python assistant/index_kb.py                 # instrukcja (docs/kb) + zamknięte postoje
    python assistant/index_kb.py --query "co zrobić przy zatorze"
    python assistant/index_kb.py --query "what does code 201 mean" --kind manual

Idempotentne: dla każdego źródła DELETE + INSERT w jednej transakcji, więc ponowne uruchomienie po zmianie
instrukcji daje ten sam stan co pierwsze. Postoje ('case') to tekst wygenerowany z stop_event – BEZ pola
evidence.sim (prawda symulacji, xInj*): asystent ma wiedzieć tylko to, co wiedziałby system w zakładzie.
"""
import argparse
import time
from datetime import timezone
from zoneinfo import ZoneInfo

from kb import Embedder, connect, manual_chunks, search

TZ = ZoneInfo("Europe/Warsaw")
STATE = {1: "Clearing", 2: "Stopped", 3: "Starting", 4: "Idle", 5: "Suspended", 6: "Execute", 7: "Stopping",
         8: "Aborting", 9: "Aborted", 11: "Held", 15: "Resetting"}


def case_text(r):
    """Wiersz stop_event -> opis postoju po polsku (jedno źródło 'stop:<t_start UTC ISO>')."""
    t_start, t_end, state, reason, cause, conf, ev, clip = r
    ev = ev or {}
    plc, vis = ev.get("plc", {}), ev.get("vision", {})
    states = ", ".join("{} ({})".format(STATE.get(s, "nieznany"), s) for s in plc.get("states", [state]))
    lines = [
        "Postój {} czasu lokalnego, trwał {:.0f} s.".format(
            t_start.astimezone(TZ).strftime("%d.%m.%Y %H:%M:%S"), (t_end - t_start).total_seconds()),
        "Stany po Execute: {}. Kod iStopReason: {}.".format(states, reason),
        "Przyczyna: {}, pewność: {}.".format(cause, conf),
    ]
    if ev.get("secondary"):
        lines.append("Kolejne przyczyny w tym postoju: {}.".format(", ".join(ev["secondary"])))
    lines.append("Sztuk w 30 s przed postojem: {}, ostatni czas cyklu: {} ms.".format(
        plc.get("pieces_in_window"), plc.get("cycle_ms")))
    if vis.get("offline_in_window"):
        lines.append("Kamera była offline w oknie postoju.")
    else:
        lines.append("Kamera: obiekty {}, przewrócone butelki w chwilach {} s względem postoju, "
                     "ostatnia sztuka {} s przed postojem.".format(
                         ", ".join("{} {}".format(c, n) for c, n in (vis.get("counts") or {}).items()) or "brak",
                         ", ".join(str(x) for x in vis.get("fallen_at_s") or []) or "brak", vis.get("last_item_s_before")))
    if ev.get("note"):
        lines.append("Uwaga: {}.".format(ev["note"]))
    lines.append("Klip: {}.".format(clip or "brak"))
    return "\n".join(lines)


SQL_CASES = """SELECT t_start, t_end, state, stop_reason, cause, confidence, evidence, clip
                 FROM stop_event WHERE t_end IS NOT NULL ORDER BY t_start"""
SQL_DEL = "DELETE FROM kb_chunk WHERE kind = %s AND source = %s"
SQL_INS = """INSERT INTO kb_chunk (kind, source, chunk_no, section, content, embedding)
             VALUES (%s, %s, %s, %s, %s, %s)"""


def write(conn, kind, rows, emb):
    """rows: [(źródło, nr, sekcja, treść)] -> embeddingi -> DELETE + INSERT po źródłach, jedna transakcja."""
    t0 = time.time()
    vecs = emb.passages([r[3] for r in rows])
    t_emb = time.time() - t0
    with conn.transaction():
        if kind == "case":
            conn.execute("DELETE FROM kb_chunk WHERE kind = 'case'")   # postoje mogły zostać przeliczone
        else:
            for src in {r[0] for r in rows}:
                conn.execute(SQL_DEL, (kind, src))
        for (src, no, sec, text), v in zip(rows, vecs):
            conn.execute(SQL_INS, (kind, src, no, sec, text, v))
    print("{}: {} fragmentów, embeddingi {:.1f} s".format(kind, len(rows), t_emb), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", help="tylko wyszukaj (bez indeksowania)")
    ap.add_argument("--kind", choices=["manual", "case"])
    ap.add_argument("-k", type=int, default=4)
    a = ap.parse_args()
    emb, conn = Embedder(), connect()

    if a.query:
        for i, (id_, kind, src, sec, text, dist) in enumerate(search(conn, emb.query(a.query), a.k, a.kind), 1):
            print("[S{}] dist {:.3f}  {}  {}  ({})".format(i, dist, kind, sec or "", src))
        return

    write(conn, "manual", manual_chunks(), emb)
    cases = conn.execute(SQL_CASES).fetchall()
    rows = [("stop:" + r[0].astimezone(timezone.utc).isoformat(), 0, "Postój " + (r[4] or "nieznana"), case_text(r))
            for r in cases]
    if rows:
        write(conn, "case", rows, emb)
    print(conn.execute("SELECT kind, count(*) FROM kb_chunk GROUP BY kind ORDER BY kind").fetchall())


if __name__ == "__main__":
    main()
