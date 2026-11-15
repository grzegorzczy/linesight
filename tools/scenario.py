#!/usr/bin/env python3
"""E4-06: scenariusz sesji danych napędu – steruje linią przez OPC UA bez operatora.

Laptop, .venv (asyncua jest już zainstalowane – tools/opcua_browse.py):
    python tools\\scenario.py --dry              # plan i czas trwania, bez połączenia
    python tools\\scenario.py --scale 0.05       # próba mechaniki: każdy krok 20x krótszy
    python tools\\scenario.py                    # pełna sesja (ok. 2 h 50 min)
    python tools\\scenario.py --extra            # dokładka po sesji: zimny start bez zużycia (35 min)

Po co: model kondycji napędu potrzebuje danych normalnych z zimnymi startami po postojach różnej długości
(pułapka dla prostego progu) i kilku epizodów zużycia, w tym jednego zaraz po zimnym starcie (najtrudniejszy
przypadek: oba zjawiska podnoszą moment). Ręcznie to 3 h klikania; skrypt robi to powtarzalnie.

Komendy PackML to zbocza: zapis TRUE, 0,5 s, FALSE. Każdy krok trafia do logu data/scenario_<czas>.csv
(czas UTC, krok, stan linii) – to dziennik sesji; prawdą o zużyciu dla modelu i tak jest sygnał rSimWear w bazie.
Ctrl+C przerywa: skrypt zdejmuje xInjWear i zostawia linię w bieżącym stanie.
"""
import argparse
import asyncio
import csv
import datetime
import os

from asyncua import Client, ua

URL = "opc.tcp://192.168.0.244:4840"
NS_URI = "CODESYSSPV3/3S/IecVarAccess"
PREFIX = "|var|JUMO ARM Cortex A7 Linux iMX6ULL ARM32.Application.GVL_Line."
WEAR_RAMP_MIN = 10        # zużycie 0 -> 100 % w 10 min (w PLC domyślnie 20; krótsza sesja)

# (krok, minuty, opis). run = praca; stop = postój (silnik stygnie), potem Reset + Start;
# wear = praca ze zużyciem przez podany czas, potem naprawa (xInjWear FALSE).
PLAN = [
    ("run", 30, "rozgrzanie od zimnego silnika, praca normalna"),
    ("stop", 15, "postój długi: zimny start"),
    ("run", 20, "praca normalna"),
    ("wear", 15, "zużycie 1: rozgrzany silnik"),
    ("stop", 5, "postój krótki (naprawa)"),
    ("run", 15, "praca normalna"),
    ("stop", 15, "postój długi"),
    ("wear", 15, "zużycie 2: zaraz po zimnym starcie (najtrudniejsze)"),
    ("run", 15, "praca normalna po naprawie"),
    ("stop", 3, "postój bardzo krótki"),
    ("wear", 15, "zużycie 3"),
    ("run", 10, "praca normalna na koniec"),
]
# --extra: dopisane po pierwszej sesji 15.11. Część testowa (od 2. epizodu zużycia) nie miała zimnego startu bez
# zużycia, więc nie sprawdzała fałszywych alarmów po postoju – a to główna pułapka dla prostego progu.
PLAN_EXTRA = [
    ("stop", 15, "postój długi: zimny start bez zużycia (test fałszywych alarmów)"),
    ("run", 20, "rozgrzewanie i praca normalna"),
]


class Line(object):
    def __init__(self, client, ns):
        self.client, self.ns = client, ns

    def node(self, name):
        return self.client.get_node(ua.NodeId(PREFIX + name, self.ns))

    async def write(self, name, value):
        node = self.node(name)
        vt = await node.read_data_type_as_variant_type()   # BOOL -> Boolean, TIME -> typ z serwera
        await node.write_value(ua.DataValue(ua.Variant(value, vt)))   # bez znaczników czasu (CODESYS je odrzuca)

    async def pulse(self, name):
        await self.write(name, True)
        await asyncio.sleep(0.5)
        await self.write(name, False)

    async def state(self):
        return await self.node("iStateCurrent").read_value()

    async def ensure_execute(self, log):
        """Doprowadza linię do Execute (6) z Stopped / Idle; czeka na stany przejściowe."""
        for _ in range(30):
            s = await self.state()
            if s == 6:
                return
            if s == 2:
                await self.pulse("xCmdReset")
            elif s == 4:
                await self.pulse("xCmdStart")
            elif s == 9:
                raise RuntimeError("linia w Aborted – skasuj awarię (xCmdClear) i uruchom skrypt ponownie")
            await asyncio.sleep(1.5)
        raise RuntimeError("linia nie doszła do Execute, stan {}".format(await self.state()))


def plan_minutes(plan, scale):
    return sum(m for _, m, _ in plan) * scale


async def run(plan, scale, logfile):
    async with Client(url=URL, timeout=5) as client:
        line = Line(client, await client.get_namespace_index(NS_URI))
        await line.write("tWearRamp", int(WEAR_RAMP_MIN * 60000))   # TIME w OPC UA CODESYS = milisekundy
        await line.write("xInjWear", False)

        with open(logfile, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_utc", "krok", "minuty", "stan", "opis"])

            async def log(step, minutes, desc):
                s = await line.state()
                t = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                w.writerow([t, step, minutes, s, desc])
                f.flush()
                print("{} UTC  {:<5} {:>5.1f} min  stan {}  {}".format(t, step, minutes, s, desc), flush=True)

            try:
                await line.ensure_execute(log)
                for i, (step, minutes, desc) in enumerate(plan, 1):
                    dur = minutes * scale * 60
                    await log(step, minutes * scale, "[{}/{}] {}".format(i, len(plan), desc))
                    if step == "run":
                        await asyncio.sleep(dur)
                    elif step == "wear":
                        await line.write("xInjWear", True)
                        await asyncio.sleep(dur)
                        await line.write("xInjWear", False)
                        await log("fix", 0, "naprawa: xInjWear FALSE")
                    elif step == "stop":
                        await line.pulse("xCmdStop")
                        await asyncio.sleep(dur)
                        await line.ensure_execute(log)
                await log("end", 0, "koniec scenariusza")
            finally:
                await line.write("xInjWear", False)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scale", type=float, default=1.0, help="mnożnik czasu kroków (próba: 0.05)")
    ap.add_argument("--dry", action="store_true", help="tylko plan, bez połączenia z PLC")
    ap.add_argument("--extra", action="store_true", help="dokładka: zimny start bez zużycia (PLAN_EXTRA)")
    args = ap.parse_args()
    plan = PLAN_EXTRA if args.extra else PLAN
    print("Plan: {} kroków, {:.0f} min (scale {})".format(len(plan), plan_minutes(plan, args.scale), args.scale))
    for step, m, desc in plan:
        print("  {:<5} {:>5.1f} min  {}".format(step, m * args.scale, desc))
    if args.dry:
        return
    os.makedirs("data", exist_ok=True)
    logfile = os.path.join("data", "scenario_{}.csv".format(datetime.datetime.now().strftime("%Y%m%d-%H%M")))
    print("Log:", logfile)
    try:
        asyncio.run(run(plan, args.scale, logfile))
    except KeyboardInterrupt:
        print("Przerwano.")


if __name__ == "__main__":
    main()
