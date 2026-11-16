-- E6-07: statystyki detektora z Jetsona co minutę – sygnał dryfu danych / degradacji modelu.
-- Idempotentny: na istniejącej bazie (docker exec) i przy tworzeniu nowej (initdb).
CREATE TABLE IF NOT EXISTS vision_stats (
    time              TIMESTAMPTZ NOT NULL,   -- koniec okna (zegar Jetsona, UTC)
    window_s          REAL        NOT NULL,   -- długość okna [s], ok. 60
    frames            INTEGER     NOT NULL,
    dets              INTEGER     NOT NULL,   -- detekcje (z pewnością z detektora, bez obiektów dopowiedzianych przez tracker)
    low_conf          INTEGER     NOT NULL,   -- detekcje z pewnością w [próg wdrożenia, --unc-conf)
    class_flip        INTEGER     NOT NULL,
    uncertain_frames  INTEGER     NOT NULL,
    saved             INTEGER     NOT NULL,   -- klatki zapisane do retreningu
    mean_conf         REAL,                   -- NULL, gdy w oknie nie było detekcji
    model             TEXT,
    version           TEXT,                   -- wersja modelu z rejestru (models/current.json)
    UNIQUE (time)
);
SELECT create_hypertable('vision_stats', by_range('time', INTERVAL '7 days'), if_not_exists => TRUE);
GRANT SELECT ON vision_stats TO grafana_ro;
