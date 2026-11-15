"""E4-06/07: ocena alarmów kondycji napędu – wspólna dla baseline i modelu.

Wynik detektora: wartość na sztukę (score) i próg; alarm = score > próg przez co najmniej HOLD kolejnych sztuk
(ok. 30 s) – jak opóźnienie alarmu w SCADA: pojedyncze przekroczenia przy progu nie migają alarmem.
Ta sama reguła dla wszystkich metod, więc porównanie jest uczciwe.
- Epizod zużycia wykryty, jeśli w nim jest alarm; opóźnienie = czas od początku epizodu do pierwszego alarmu
  (i zużycie w tej chwili). Wcześniej = lepiej: o to chodzi w predictive maintenance.
- Fałszywe alarmy: włączenia alarmu (zbocze narastające) w pracy normalnej, na godzinę pracy normalnej.
  Normalna = brak zużycia i co najmniej GRACE_S po naprawie (po naprawie zużycie znika skokowo,
  a okno modelu jeszcze przez chwilę je „pamięta” – to nie jest fałszywy alarm).
- Próg: kwantyl wyniku w normalnej części walidacji (domyślnie 99,9 %) – bez zaglądania w epizody zużycia.
"""
import numpy as np
import pandas as pd

GRACE_S = 120.0
HOLD = 20


def alarms(score, thr, hold=HOLD):
    """Alarm, gdy wynik jest nad progiem od co najmniej `hold` kolejnych sztuk."""
    above = score > thr
    run = np.zeros(len(above), dtype=int)
    for i, a in enumerate(above):
        run[i] = run[i - 1] + 1 if a and i else int(a)
    return run >= hold


def normal_mask(df):
    t = df["t"].to_numpy()
    wearing = df["wearing"].to_numpy()
    ok = ~wearing
    ends = t[np.flatnonzero(wearing & ~np.r_[wearing[1:], False])]
    for e in ends:
        ok &= ~((t > e) & (t <= e + GRACE_S))
    return ok


def threshold(df, score, q=0.999):
    m = (df["split"] == "val").to_numpy() & normal_mask(df)
    return float(np.nanquantile(score[m], q))


def evaluate(df, score, thr, split, eps):
    """Słownik metryk dla jednej części (val / test)."""
    sel = (df["split"] == split).to_numpy()
    d = df[sel]
    alarm = alarms(score, thr)[sel]
    t = d["t"].to_numpy()
    res = {"split": split, "threshold": thr}
    det = []
    for a, b in eps:
        m = (t >= a) & (t <= b)
        if not m.any():
            continue
        hit = np.flatnonzero(alarm & m)
        if hit.size:
            i = hit[0]
            det.append({"delay_min": (t[i] - a) / 60.0, "wear_at_alarm": float(d["wear"].iat[i])})
        else:
            det.append({"delay_min": None, "wear_at_alarm": None})
    res["episodes"] = det
    res["detected"] = "{}/{}".format(sum(x["delay_min"] is not None for x in det), len(det))
    nm = normal_mask(d)
    onsets = alarm & ~np.r_[False, alarm[:-1]] & nm
    hours = nm.sum() * np.median(np.diff(t)) / 3600.0
    res["false_alarms"] = int(onsets.sum())
    res["false_alarms_per_h"] = float(onsets.sum() / hours) if hours > 0 else float("nan")
    res["normal_in_alarm_pct"] = float(100.0 * (alarm & nm).sum() / max(1, nm.sum()))
    return res


def table(results):
    """Wiersze do druku: metoda, część, wykryte, opóźnienia, zużycie przy alarmie, fałszywe alarmy/h."""
    rows = []
    for name, r in results:
        delays = ", ".join("-" if e["delay_min"] is None else "{:.1f}".format(e["delay_min"]) for e in r["episodes"])
        wears = ", ".join("-" if e["wear_at_alarm"] is None else "{:.0f}%".format(100 * e["wear_at_alarm"])
                          for e in r["episodes"])
        rows.append({"metoda": name, "część": r["split"], "wykryte": r["detected"], "opóźnienie [min]": delays,
                     "zużycie przy alarmie": wears, "fałszywe alarmy/h": round(r["false_alarms_per_h"], 2),
                     "normalna w alarmie [%]": round(r["normal_in_alarm_pct"], 1)})
    return pd.DataFrame(rows)
