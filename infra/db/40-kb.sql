-- E5-01: baza wiedzy asystenta (RAG) – fragmenty instrukcji i opisy zamkniętych postojów z embeddingami.
-- Idempotentny: na istniejącej bazie (docker exec) i przy tworzeniu nowej (initdb).
-- pgvector 0.8.1 jest w obrazie timescale/timescaledb:2.25.2-pg17, trzeba go tylko włączyć w bazie.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunk (
    id         BIGSERIAL   PRIMARY KEY,
    kind       TEXT        NOT NULL,      -- 'manual' = fragment instrukcji z docs/kb, 'case' = opis zamkniętego postoju
    source     TEXT        NOT NULL,      -- plik (np. 'kb/kody-bledow.md') albo 'stop:<t_start ISO>'
    chunk_no   INT         NOT NULL,      -- kolejny fragment w źródle
    section    TEXT,                      -- ścieżka nagłówków, np. 'Kody błędów > 101 Zator'
    content    TEXT        NOT NULL,      -- tekst fragmentu (to, co trafia do promptu i do cytatu)
    embedding  vector(384) NOT NULL,      -- intfloat/multilingual-e5-small, wektor znormalizowany
    updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, chunk_no)             -- ponowne indeksowanie źródła = DELETE po source + INSERT
);
-- Bez indeksu HNSW/IVFFlat: przy ~100-300 fragmentach pełne przeszukanie (exact) trwa < 1 ms
-- i ma recall 100 %. Indeks przybliżony dodamy tylko z pomiarem (E5-03).
