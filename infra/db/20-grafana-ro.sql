-- E3-07: użytkownik tylko do odczytu dla Grafany. Grafana wykonuje SQL wpisany w panelach,
-- więc nie powinna mieć prawa do INSERT/DELETE/DROP. Plik jest idempotentny: można go uruchomić
-- na istniejącej bazie (docker exec) i jest też wykonywany przy tworzeniu nowej (initdb).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        CREATE ROLE grafana_ro LOGIN PASSWORD 'grafana_ro';   -- tylko sieć lokalna; w zakładzie: sekret
    END IF;
END
$$;
GRANT CONNECT ON DATABASE linesight TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;          -- TimescaleDB przenosi prawa na partycje
ALTER DEFAULT PRIVILEGES FOR ROLE linesight IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
