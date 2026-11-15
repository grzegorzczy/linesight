-- E4-08: kondycja napędu – wynik modelu (autoenkoder, ONNX) dla każdej sztuki, liczony przez usługę diag.
-- Idempotentny: na istniejącej bazie (docker exec) i przy tworzeniu nowej (initdb).
CREATE TABLE IF NOT EXISTS drive_health (
    time    TIMESTAMPTZ PRIMARY KEY,   -- czas sztuki (zmiana licznika, czas mostu, UTC)
    piece   BIGINT      NOT NULL,      -- udiProdProcessed
    score   REAL        NOT NULL,      -- błąd odtworzenia cech okna 32 sztuk
    ratio   REAL        NOT NULL,      -- wynik / próg (próg z walidacji, models/drive_ae.json)
    alarm   BOOLEAN     NOT NULL,      -- ratio > 1 przez co najmniej 20 kolejnych sztuk
    health  REAL        NOT NULL       -- kondycja [%] dla operatora: 100 % przy ≤ 0,3 progu, ok. 66 % na progu, 0 % przy ≥ 10 progach
);
SELECT create_hypertable('drive_health', 'time', if_not_exists => TRUE, migrate_data => TRUE);
GRANT SELECT ON drive_health TO grafana_ro;
