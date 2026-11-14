-- E3-06: schemat bazy LineSight (TimescaleDB). Uruchamiany raz, przy pierwszym starcie kontenera
-- z pustym wolumenem (katalog /docker-entrypoint-initdb.d). Zmiana tego pliku NIE zmienia istniejącej bazy.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Sygnały PLC w formacie „wąskim”: jeden wiersz = jedna zmiana jednej zmiennej.
-- Most wysyła tylko zmiany (subskrypcja OPC UA), więc format szeroki (kolumna na zmienną)
-- byłby pełen pustych pól; nowy sygnał nie wymaga też zmiany schematu.
CREATE TABLE IF NOT EXISTS plc_signal (
    time   TIMESTAMPTZ      NOT NULL,   -- czas odbioru przez most (zegar laptopa, UTC)
    name   TEXT             NOT NULL,   -- nazwa zmiennej, np. iStateCurrent; plc_link = połączenie z PLC
    value  DOUBLE PRECISION,            -- BOOL zapisany jako 0/1
    t_src  TIMESTAMPTZ,                 -- czas ze sterownika (tylko do wglądu, zegar PLC nie jest synchronizowany)
    UNIQUE (time, name)                 -- QoS 1 może dostarczyć duplikat: ON CONFLICT DO NOTHING
);
SELECT create_hypertable('plc_signal', by_range('time', INTERVAL '1 day'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS plc_signal_name_time ON plc_signal (name, time DESC);

-- Zdarzenia z kamery (Jetson): jedno przecięcie linii = jeden wiersz.
CREATE TABLE IF NOT EXISTS vision_event (
    time       TIMESTAMPTZ NOT NULL,    -- t_cross: chwila przecięcia linii (zegar Jetsona, UTC)
    t_decided  TIMESTAMPTZ NOT NULL,    -- chwila ustalenia klasy (ok. 5 s później)
    track_id   BIGINT      NOT NULL,
    class      TEXT        NOT NULL,    -- bottle / missing_cap / fallen
    direction  TEXT,
    clip       TEXT,                    -- nazwa klipu w ~/linesight_clips na Jetsonie (NULL dla bottle)
    votes      JSONB,
    raw        JSONB       NOT NULL,    -- całe zdarzenie, gdyby doszły nowe pola
    UNIQUE (time, track_id)
);
SELECT create_hypertable('vision_event', by_range('time', INTERVAL '7 days'), if_not_exists => TRUE);

-- Stan łącza kamery i mostu (status online/offline z MQTT): pozwala odróżnić brak danych od postoju.
CREATE TABLE IF NOT EXISTS link_status (
    time    TIMESTAMPTZ NOT NULL,       -- czas odbioru przez ingest (zegar laptopa)
    source  TEXT        NOT NULL,       -- plc / vision
    online  BOOLEAN     NOT NULL,
    UNIQUE (time, source)
);
SELECT create_hypertable('link_status', by_range('time', INTERVAL '7 days'), if_not_exists => TRUE);

-- Sygnały z okna `win` przed chwilą `t_event` (domyślnie 30 s) – podstawa diagnostyki postoju (etap 4).
-- Pierwszy wiersz każdej zmiennej to jej wartość na początku okna (ostatnia zmiana przed oknem,
-- z czasem przyciętym do początku okna): bez niego zmienna, która nie zmieniła się w oknie, by zniknęła.
CREATE OR REPLACE FUNCTION signals_before(t_event TIMESTAMPTZ, win INTERVAL DEFAULT INTERVAL '30 seconds')
RETURNS TABLE ("time" TIMESTAMPTZ, name TEXT, value DOUBLE PRECISION)
LANGUAGE sql STABLE AS $$
    SELECT * FROM (
        (SELECT DISTINCT ON (s.name) t_event - win, s.name, s.value
           FROM plc_signal s
          WHERE s.time <= t_event - win
            AND s.time >  t_event - win - INTERVAL '1 day'   -- ogranicza przeszukiwane partycje (chunki)
          ORDER BY s.name, s.time DESC)
        UNION ALL
        (SELECT s.time, s.name, s.value
           FROM plc_signal s
          WHERE s.time > t_event - win AND s.time <= t_event)
    ) w
    ORDER BY 1, 2;
$$;
