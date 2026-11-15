"""E4-08: kondycja napędu na żywo – wynik autoenkodera (ONNX Runtime) po każdej sztuce, zapis w drive_health.

Wołane z diag.py w tej samej pętli co postoje (co POLL_S s). Bez PyTorcha: model to 329 wag w pliku ONNX,
do wnioskowania wystarcza onnxruntime (kontener mniejszy o ok. 2 GB).

Przebieg: surowe sygnały z ostatnich FETCH_MIN minut (+ ostatnia wartość każdego sygnału sprzed okna – most wysyła
tylko zmiany, a temperatura w ustalonej pracy potrafi się nie zmieniać przez minuty) -> te same funkcje co w treningu
(anomaly/data.pieces, anomaly/features.window_features) -> normalizacja z models/drive_ae.json -> błąd odtworzenia
-> wynik / próg, alarm (HOLD sztuk nad progiem), kondycja [%] -> INSERT nowych sztuk (ON CONFLICT DO NOTHING).
Każdy przebieg liczy okno od nowa, więc restart usługi i spóźnione dane nie psują wyniku (jak przy postojach).
"""
import json
import os

import numpy as np
import onnxruntime as ort
import pandas as pd

from data import FEATURES, SIGNALS, pieces
from features import health_pct, window_features

FETCH_MIN = float(os.environ.get("DRIVE_FETCH_MIN", "10"))
NAMES = ["udiProdProcessed"] + list(SIGNALS)

SQL_RAW = """
    SELECT extract(epoch FROM time) AS t, name, value FROM plc_signal
     WHERE name = ANY(%(names)s) AND time > now() - make_interval(secs => %(s)s)
    UNION ALL
    (SELECT DISTINCT ON (name) extract(epoch FROM time), name, value FROM plc_signal
      WHERE name = ANY(%(names)s) AND time <= now() - make_interval(secs => %(s)s)
        AND time > now() - make_interval(secs => %(s)s) - interval '1 day'
      ORDER BY name, time DESC)
"""
SQL_LAST = "SELECT extract(epoch FROM max(time)) FROM drive_health"
SQL_INSERT = """
    INSERT INTO drive_health (time, piece, score, ratio, alarm, health)
    VALUES (to_timestamp(%s), %s, %s, %s, %s, %s) ON CONFLICT (time) DO NOTHING
"""


class DriveHealth(object):
    def __init__(self, onnx_path, json_path):
        self.sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.cfg = json.load(open(json_path))
        self.mu = np.asarray(self.cfg["mean"], dtype=np.float32)
        self.sd = np.asarray(self.cfg["std"], dtype=np.float32)
        self.thr = float(self.cfg["threshold"])
        self.hold = int(self.cfg["hold"])
        self.w = int(self.cfg["window"])
        print("Napęd: model {} (okno {} sztuk, próg {:.3f}, alarm po {} sztukach)".format(
            onnx_path, self.w, self.thr, self.hold), flush=True)

    def score(self, feats):
        z = ((feats - self.mu) / self.sd).astype(np.float32)
        rec = self.sess.run(None, {self.sess.get_inputs()[0].name: z})[0]
        return ((rec - z) ** 2).mean(axis=1)

    def run_once(self, conn):
        """Zwraca liczbę nowych sztuk zapisanych w drive_health."""
        rows = conn.execute(SQL_RAW, {"names": NAMES, "s": FETCH_MIN * 60}).fetchall()
        if not rows:
            return 0
        raw = pd.DataFrame(rows, columns=["t", "name", "value"]).astype({"t": float, "value": float})
        df = pieces(raw.sort_values("t", kind="stable"))
        if df.empty:
            return 0
        feats = window_features(df[FEATURES].to_numpy(dtype=np.float32), df["segment"].to_numpy(), self.w)
        ok = ~np.isnan(feats[:, 0])
        if not ok.any():
            return 0
        score = np.full(len(df), np.nan)
        score[ok] = self.score(feats[ok])
        ratio = score / self.thr
        above = ratio > 1.0                      # NaN (okno niepełne) -> False
        run = np.zeros(len(df), dtype=int)
        for i, a in enumerate(above):
            run[i] = run[i - 1] + 1 if a and i else int(a)
        alarm = run >= self.hold
        last = conn.execute(SQL_LAST).fetchone()[0]
        last = float(last) if last is not None else 0.0
        new = [(float(t), int(p), float(s), float(r), bool(a), float(health_pct(r)))
               for t, p, s, r, a, k in zip(df["t"], df["piece"], score, ratio, alarm, ok) if k and t > last + 1e-3]
        if new:
            with conn.transaction():
                for row in new:
                    conn.execute(SQL_INSERT, row)
            a = new[-1]
            print("Napęd: +{} sztuk, ostatnia: wynik/próg {:.2f}, kondycja {:.0f} %{}".format(
                len(new), a[3], a[5], ", ALARM" if a[4] else ""), flush=True)
        return len(new)
