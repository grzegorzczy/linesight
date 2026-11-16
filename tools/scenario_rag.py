#!/usr/bin/env python3
"""E5-06: sesja postojów do ewaluacji asystenta – każdy rodzaj postoju i pewności co najmniej raz (ok. 25 min).

Laptop, .venv; PLC, most, baza, diag (drive_health) i Jetson (kamera + serwer klipów) muszą działać:
    python tools\\scenario_rag.py --dry      # plan bez połączenia
    python tools\\scenario_rag.py            # sesja z operatorem (Enter = gotowe)
    python tools\\scenario_rag.py --only E1  # powtórka jednego zdarzenia (16.11: w E1 kamera nie zliczyła leżącej butelki)

Czemu z operatorem: pewność „potwierdzona” wymaga, żeby kamera NAPRAWDĘ zobaczyła przewróconą butelkę albo brak
butelek – tego nie wstrzykniemy przez OPC UA. Skrypt mówi, co zrobić przed kamerą, czeka na Enter i dopiero wtedy
wstrzykuje usterkę w PLC, więc zdarzenie z kamery wypada w oknie 30 s przed postojem.

Log data/scenario_rag_<czas>.csv: czas UTC, id zdarzenia, oczekiwana przyczyna i pewność. To jest „prawda”
do zestawu pytań (E5-06) – asystent jej nie widzi (tak jak xInj* w bazie).
"""
import argparse
import asyncio
import csv
import datetime
import os

from asyncua import Client

from scenario import NS_URI, URL, Line

WEAR_RAMP_MIN = 10     # zużycie 0 -> 100 % w 10 min (jak w scenario.py)
FLOW = "przesuwaj stojące butelki przez kadr co ok. 2 s"

# (id, oczekiwana przyczyna, oczekiwana pewność, polecenie dla operatora przed Enter, akcje)
# akcje: ("wait", s) | ("set", zmienna, wartość) | ("pulse", komenda) | ("recover",) = Clear/Reset/Start
PLAN = [
    ("E0", "-", "-", "Rozgrzewka: " + FLOW + " przez ok. 1 min, potem Enter", [("wait", 60)]),
    ("E1", "zator", "potwierdzona",
     FLOW + "; potem PRZEWRÓĆ jedną butelkę i przesuń ją leżącą przez kadr – Enter dopiero, gdy na Jetsonie "
     "(SSH1) pojawi się ZLICZONO z \"class\": \"fallen\"",
     [("wait", 2), ("set", "xInjJam", True), ("wait", 20), ("set", "xInjJam", False)]),
    ("E2", "zator", "tylko_plc", FLOW + " (tylko stojące, bez przewróconej) przez ok. 20 s – Enter",
     [("set", "xInjJam", True), ("wait", 25), ("set", "xInjJam", False)]),
    ("E3", "brak_produktu", "potwierdzona", "ODSUŃ wszystkie butelki z kadru i nic nie przesuwaj – Enter",
     [("wait", 15), ("set", "xInjNoProduct", True), ("wait", 30), ("set", "xInjNoProduct", False)]),
    ("E4", "brak_produktu", "sprzeczna", FLOW + " przez ok. 20 s, nie przerywaj – Enter w trakcie",
     [("wait", 2), ("set", "xInjNoProduct", True), ("wait", 20), ("set", "xInjNoProduct", False)]),
    ("E5", "zator, potem brak_produktu", "potwierdzona",
     FLOW + "; PRZEWRÓĆ butelkę i przesuń przez kadr, potem odsuń wszystkie butelki – Enter",
     [("wait", 2), ("set", "xInjJam", True), ("wait", 10), ("set", "xInjNoProduct", True),
      ("set", "xInjJam", False), ("wait", 25), ("set", "xInjNoProduct", False)]),
    ("E6", "awaria (napęd zużyty, alarm przed awarią)", "tylko_plc",
     "Zużycie napędu przez 8 min (butelek nie trzeba przesuwać) – Enter",
     [("set", "xInjWear", True), ("wait", 480), ("set", "xInjFault", True), ("wait", 15),
      ("set", "xInjFault", False), ("set", "xInjWear", False), ("wait", 20), ("recover",)]),
    ("E7", "awaria (abort operatora, kod 302)", "tylko_plc", "Wyłącznik awaryjny – Enter",
     [("pulse", "xCmdAbort"), ("wait", 20), ("recover",)]),
    ("E8", "operator", "tylko_plc", "Stop planowy na 60 s – Enter",
     [("pulse", "xCmdStop"), ("wait", 60), ("recover",)]),
    ("E9", "-", "-", "Praca normalna 2 min na koniec (okno dla ostatniego postoju) – Enter", [("wait", 120)]),
]


async def recover(line):
    """Aborted -> Clear -> Stopped -> Reset -> Idle -> Start -> Execute (kolejność z instrukcji, docs/kb)."""
    for _ in range(20):
        s = await line.state()
        if s == 9:
            await line.pulse("xCmdClear")
        elif s in (2, 4):
            await line.ensure_execute(None)
            return
        elif s == 6:
            return
        await asyncio.sleep(1.5)
    raise RuntimeError("linia nie wróciła do Execute, stan {}".format(await line.state()))


async def run(plan, logfile):
    loop = asyncio.get_running_loop()
    async with Client(url=URL, timeout=5) as client:
        line = Line(client, await client.get_namespace_index(NS_URI))
        await line.write("tWearRamp", int(WEAR_RAMP_MIN * 60000))
        for v in ("xInjJam", "xInjNoProduct", "xInjFault", "xInjWear", "xInjSlow"):
            await line.write(v, False)
        await line.ensure_execute(None)
        with open(logfile, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t_utc", "id", "przyczyna", "pewnosc", "zdarzenie"])

            def log(eid, cause, conf, what):
                t = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                w.writerow([t, eid, cause, conf, what])
                f.flush()
                print("  {} UTC  {}  {}".format(t, eid, what), flush=True)

            try:
                for i, (eid, cause, conf, instr, actions) in enumerate(plan, 1):
                    print("\n[{}/{}] {} – oczekiwane: {} / {}\n  >> {}".format(i, len(plan), eid, cause, conf, instr))
                    await loop.run_in_executor(None, input, "  [Enter] ")
                    log(eid, cause, conf, "start")
                    for a in actions:
                        if a[0] == "wait":
                            await asyncio.sleep(a[1])
                        elif a[0] == "set":
                            await line.write(a[1], a[2])
                            log(eid, cause, conf, "{} := {}".format(a[1], a[2]))
                        elif a[0] == "pulse":
                            await line.pulse(a[1])
                            log(eid, cause, conf, a[1])
                        elif a[0] == "recover":
                            await recover(line)
                            log(eid, cause, conf, "Execute po Clear/Reset/Start")
                    if await line.state() != 6:
                        await recover(line)
                log("END", "-", "-", "koniec sesji")
            finally:
                for v in ("xInjJam", "xInjNoProduct", "xInjFault", "xInjWear"):
                    await line.write(v, False)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry", action="store_true", help="tylko plan")
    ap.add_argument("--only", nargs="+", metavar="ID", help="tylko wskazane zdarzenia, np. --only E1")
    a = ap.parse_args()
    plan = [p for p in PLAN if not a.only or p[0] in a.only]
    for eid, cause, conf, instr, actions in plan:
        sec = sum(x[1] for x in actions if x[0] == "wait")
        print("{:<3} {:>4} s  {:<40} {:<13} {}".format(eid, sec, cause, conf, instr))
    if a.dry:
        return
    os.makedirs("data", exist_ok=True)
    logfile = os.path.join("data", "scenario_rag_{}.csv".format(datetime.datetime.now().strftime("%Y%m%d-%H%M")))
    print("Log:", logfile)
    try:
        asyncio.run(run(plan, logfile))
    except KeyboardInterrupt:
        print("Przerwano – usterki zdjęte.")


if __name__ == "__main__":
    main()
