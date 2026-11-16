"""E5-06: zrzut kontekstu postojów ([P1] postój, [P2] sygnały, [P3] napęd) do JSON – materiał do wzorcowych odpowiedzi.

    python assistant/dump_contexts.py --since 2026-11-14 > data/eval_contexts.json

Wzorcowe odpowiedzi w zestawie ewaluacyjnym piszemy z TEGO, co asystent dostaje w kontekście (plus log sesji
z prawdą symulacji). Zrzut jest też dowodem w repo: widać, na jakich danych liczono wyniki ewaluacji.
"""
import argparse
import json
import sys

from context import stop_sources
from kb import TZ, connect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-14", help="data (czas lokalny) najstarszego postoju")
    a = ap.parse_args()
    conn = connect()
    rows = conn.execute("""SELECT t_start, t_end, state, stop_reason, cause, confidence, evidence, clip FROM stop_event
                            WHERE t_start >= %s::date AT TIME ZONE 'Europe/Warsaw' ORDER BY t_start""",
                        (a.since,)).fetchall()
    out = []
    for r in rows:
        out.append({"t_start_local": r[0].astimezone(TZ).strftime("%d.%m.%Y %H:%M:%S"), "t_start": r[0].isoformat(),
                    "cause": r[4], "confidence": r[5], "evidence": r[6], "clip": r[7],
                    "sources": stop_sources(conn, r)})
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1, default=str)
    print("postojów: {}".format(len(out)), file=sys.stderr)


if __name__ == "__main__":
    main()
