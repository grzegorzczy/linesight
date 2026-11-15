-- E4-02: postoje linii wyliczane przez usługę `diag` z sygnału iStateCurrent.
-- Idempotentny: uruchamiany na istniejącej bazie (docker exec) i przy tworzeniu nowej (initdb).
-- Zwykła tabela, nie hypertabela: postojów jest kilkadziesiąt dziennie, a klucz to sam początek postoju.
CREATE TABLE IF NOT EXISTS stop_event (
    t_start     TIMESTAMPTZ PRIMARY KEY,   -- wyjście z Execute (czas mostu, UTC)
    t_end       TIMESTAMPTZ,               -- powrót do Execute; NULL = postój trwa
    state       INT         NOT NULL,      -- pierwszy stan po Execute: 11 Held, 5 Suspended, 8 Aborting, 7 Stopping
    stop_reason INT,                       -- iStopReason na początku postoju (101 / 201 / 301, 302 / 1)
    cause       TEXT,                      -- E4-03: przyczyna z reguł
    evidence    JSONB,                     -- E4-03: dowody (sygnały, zdarzenia z kamery)
    clip        TEXT,                      -- E4-04: link do klipu
    updated     TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON stop_event TO grafana_ro;
