"""Kopia FB_DriveSim i scenariusza (tools/scenario.py) w Pythonie – TYLKO do testów kodu analizy bez sterownika.

Generuje surowe dane w tym samym formacie co eksport z bazy (t, name, value). Prawdziwy zbiór pochodzi z PLC;
ten plik nie służy do trenowania modelu. Uruchomienie: python anomaly/sim.py  -> data/drive_raw_sim.csv
"""
import csv
import random
import sys
from pathlib import Path

PLAN = [("run", 30), ("stop", 15), ("run", 20), ("wear", 15), ("stop", 5), ("run", 15), ("stop", 15),
        ("wear", 15), ("run", 15), ("stop", 3), ("wear", 15), ("run", 10),
        ("stop", 15), ("run", 20)]   # + --extra: zimny start bez zużycia w części testowej


def gauss(rng):
    return (sum(rng.random() for _ in range(4)) - 2.0) * 1.7320508


def simulate(seed=0, t0=1_800_000_000.0, ramp_s=600.0, temp0=35.0, dt=0.1):
    rng = random.Random(seed)
    rows, t, temp, cur, wear, piece, state = [], t0, temp0, 0.0, 0.0, 0, None
    last = {}

    def emit(name, value):
        if last.get(name) != value:
            rows.append((round(t, 3), name, value))
            last[name] = value

    for step, minutes in PLAN:
        steps = int(minutes * 60 / dt)
        running = step in ("run", "wear")
        emit("iStateCurrent", 6 if running else 2)
        emit("xInjWear", 1.0 if step == "wear" else 0.0)
        tcyc, cyc_len = 0.0, 1.55
        for _ in range(steps):
            wear = min(1.0, wear + dt / ramp_s) if step == "wear" else 0.0
            i_eff = cur if running else 0.0
            temp += dt / 600.0 * (22.0 + 2.25 * i_eff * i_eff - temp)
            emit("rMotorTemp_C", int(temp * 10) / 10.0)
            emit("rSimWear", int(wear * 100) / 100.0)
            if running:
                tcyc += dt
                if tcyc >= cyc_len:
                    tcyc, cyc_len = 0.0, 1.45 + rng.random() * 0.2
                    piece += 1
                    cold = min(0.12, max(0.0, 0.12 * (40.0 - temp) / 18.0))
                    tm = 2.0 * (1 + 0.15 * wear + cold) + 0.06 * (1 + 1.5 * wear) * gauss(rng)
                    emit("udiProdProcessed", float(piece))
                    emit("rTorqueMean_Nm", int(tm * 1000) / 1000.0)
                    emit("rTorquePeak_Nm", int((tm * (1.6 + 0.25 * wear) + 0.08 * (1 + 2 * wear) * gauss(rng)) * 1000) / 1000.0)
                    cur = int((0.8 + 1.2 * tm + 0.02 * gauss(rng)) * 1000) / 1000.0
                    emit("rCurrent_A", cur)
            t += dt
        if step == "wear":
            emit("xInjWear", 0.0)
    return rows


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/drive_raw_sim.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "name", "value"])
        w.writerows(simulate())
    print("Zapisano", out)
