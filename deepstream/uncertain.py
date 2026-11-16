"""E6-06: wybór „niepewnych” klatek do retreningu i liczniki do monitorowania dryfu (Jetson, Python 3.6).

Klatka jest niepewna, gdy w niej:
  - low_conf:   detekcja ma pewność w paśmie [próg wdrożenia, conf_hi) – model „ledwo” ją przepuścił
                (próg wdrożenia 0,45 obcina nvinfer, więc wszystko poniżej i tak tu nie dociera),
  - class_flip: ślad (ID z trackera) z co najmniej min_votes klatkami dostaje klasę inną niż jego dotychczasowa
                większość – np. butelka pod światło skacze między bottle a missing_cap (przesunięcie domeny z E2-04).
Obie sytuacje to dokładnie te klatki, których etykieta najwięcej zmieni w retreningu (aktywne uczenie).

Zapis z limitem: najwyżej jedna klatka na min_interval s i max_per_hour na godzinę – żeby długi problem
(np. zmiana światła na cały dzień) nie zapchał karty SD ani zasobnika tysiącami prawie identycznych klatek.
Na dysku: <dir>/<RRRRMMDD>/<RRRRMMDD-HHMMSS>_f<klatka>.jpg + .json (JSON zapisywany jako drugi = para kompletna;
upload_frames.py wysyła tylko pary z JSON-em).
"""
import json
import os
import time
from collections import Counter, deque

NAMES = ["bottle", "missing_cap", "fallen"]


class UncertainFrames(object):
    def __init__(self, out_dir, conf_hi=0.6, min_interval=5.0, max_per_hour=60, min_votes=10, model=None,
                 untracked=0xFFFFFFFFFFFFFFFF, stale_frames=90):
        self.out_dir = out_dir
        self.conf_hi = conf_hi
        self.min_interval = min_interval
        self.max_per_hour = max_per_hour
        self.min_votes = min_votes
        self.model = model or {}
        self.untracked = untracked
        self.stale_frames = stale_frames
        self.tracks = {}            # id -> {"votes": Counter, "last": klatka}
        self.saved_at = deque()     # czasy zapisów z ostatniej godziny
        self.stats = Counter()      # frames, dets, low_conf, class_flip, uncertain_frames, saved, rate_limited
        self.conf_sum = 0.0

    def check(self, frame_num, dets):
        """dets: lista (track_id, class_id, confidence, (left, top, width, height)). Zwraca listę powodów."""
        self.stats["frames"] += 1
        reasons = []
        for tid, cls, conf, box in dets:
            if conf <= 0:           # obiekt dopowiedziany przez tracker, bez detekcji w tej klatce
                continue
            self.stats["dets"] += 1
            self.conf_sum += conf
            if conf < self.conf_hi:
                self.stats["low_conf"] += 1
                reasons.append({"why": "low_conf", "track_id": tid, "class": NAMES[cls], "conf": round(conf, 3)})
            if tid == self.untracked:
                continue
            t = self.tracks.setdefault(tid, {"votes": Counter(), "last": frame_num})
            n = sum(t["votes"].values())
            if n >= self.min_votes:
                top = t["votes"].most_common(1)[0][0]
                if cls != top:
                    self.stats["class_flip"] += 1
                    reasons.append({"why": "class_flip", "track_id": tid, "class": NAMES[cls],
                                    "track_majority": NAMES[top], "votes": n, "conf": round(conf, 3)})
            t["votes"][cls] += 1
            t["last"] = frame_num
        for tid in [k for k, t in self.tracks.items() if frame_num - t["last"] > self.stale_frames]:
            del self.tracks[tid]
        if reasons:
            self.stats["uncertain_frames"] += 1
        return reasons

    def want_save(self, now=None):
        now = time.time() if now is None else now
        while self.saved_at and now - self.saved_at[0] > 3600:
            self.saved_at.popleft()
        if self.saved_at and now - self.saved_at[-1] < self.min_interval:
            return False
        if len(self.saved_at) >= self.max_per_hour:
            self.stats["rate_limited"] += 1
            return False
        return True

    def save(self, bgr, frame_num, dets, reasons, write_jpeg, now=None):
        """write_jpeg(ścieżka, obraz) – z zewnątrz (cv2.imwrite), żeby moduł dało się testować bez OpenCV."""
        now = time.time() if now is None else now
        day = time.strftime("%Y%m%d", time.localtime(now))
        d = os.path.join(self.out_dir, day)
        os.makedirs(d, exist_ok=True)
        base = os.path.join(d, "{}_f{}".format(time.strftime("%Y%m%d-%H%M%S", time.localtime(now)), frame_num))
        write_jpeg(base + ".jpg", bgr)
        meta = {"t": round(now, 3), "frame": frame_num, "model": self.model.get("model"),
                "version": self.model.get("version"), "sha256": (self.model.get("sha256") or "")[:12],
                "reasons": reasons,
                "dets": [{"track_id": tid if tid != self.untracked else None, "class": NAMES[c],
                          "conf": round(p, 3), "box_ltwh": [round(x, 1) for x in b]} for tid, c, p, b in dets]}
        tmp = base + ".json.tmp"
        with open(tmp, "w") as f:
            json.dump(meta, f)
        os.replace(tmp, base + ".json")
        self.saved_at.append(now)
        self.stats["saved"] += 1
        return base

    def summary(self):
        s = dict(self.stats)
        s["mean_conf"] = round(self.conf_sum / self.stats["dets"], 3) if self.stats["dets"] else None
        return s


def load_model_info(path=os.path.expanduser("~/linesight/models/current.json")):
    try:
        with open(path) as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}
