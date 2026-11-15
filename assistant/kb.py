"""E5-03: baza wiedzy asystenta – podział instrukcji na fragmenty, embeddingi, wyszukiwanie w pgvector.

Model embeddingów: intfloat/multilingual-e5-small (118 mln parametrów, wektor 384, ok. 100 języków).
Model e5 był trenowany z przedrostkami: tekst w bazie dostaje "passage: ", pytanie "query: ".
Bez nich wyniki są wyraźnie gorsze – to częsty błąd przy tej rodzinie modeli.
Wektory są normalizowane (długość 1), więc odległość kosinusowa pgvectora (<=>) = 1 − iloczyn skalarny.
"""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

DB_DSN = os.environ.get("DB_DSN", "postgresql://linesight:linesight@localhost:5432/linesight")
MODEL = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-small")
KB_DIR = Path(__file__).resolve().parent.parent / "docs" / "kb"


def chunk_markdown(path):
    """Plik Markdown -> [(sekcja, treść)]. Jeden nagłówek ## = jeden fragment.

    Do treści dokładamy tytuł pliku (#) i nazwę sekcji: fragment wyjęty z kontekstu nadal mówi, czego dotyczy,
    a nazwa sekcji często zawiera słowa z pytania („Kod 101 – zator”). Tekst przed pierwszym ## pomijamy.
    """
    title, section, lines, out = "", None, [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            if section:
                out.append((section, lines))
            section, lines = line[3:].strip(), []
        elif section is not None:
            lines.append(line)
    if section:
        out.append((section, lines))
    return [(title + " > " + s, "{}\n{}\n{}".format(title, s, "\n".join(l).strip())) for s, l in out]


def manual_chunks():
    """Wszystkie fragmenty instrukcji: [(źródło, nr, sekcja, treść)]. README.md nie jest instrukcją."""
    rows = []
    for p in sorted(KB_DIR.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        for i, (sec, text) in enumerate(chunk_markdown(p)):
            rows.append(("kb/" + p.name, i, sec, text))
    return rows


class Embedder(object):
    def __init__(self, model=MODEL):
        from sentence_transformers import SentenceTransformer   # import tu: chunk_markdown działa bez torcha
        try:                    # model już w cache: bez zapytań do Hugging Face (ostrzeżenia, zerwane połączenia)
            self.m = SentenceTransformer(model, local_files_only=True)
        except Exception:       # pierwsze uruchomienie: pobranie (ok. 470 MB)
            self.m = SentenceTransformer(model)
        print("Embeddingi: {} ({} wymiarów, urządzenie {})".format(
            model, self.m.get_embedding_dimension(), self.m.device), flush=True)

    def passages(self, texts):
        return self.m.encode(["passage: " + t for t in texts], normalize_embeddings=True, batch_size=16)

    def query(self, text):
        return self.m.encode("query: " + text, normalize_embeddings=True)


SQL_SEARCH = """
    SELECT id, kind, source, section, content, embedding <=> %(q)s AS dist
      FROM kb_chunk
     WHERE %(kind)s::text IS NULL OR kind = %(kind)s
     ORDER BY embedding <=> %(q)s
     LIMIT %(k)s
"""


def search(conn, qvec, k=4, kind=None):
    """k najbliższych fragmentów (dokładne przeszukanie, bez indeksu). kind: None / 'manual' / 'case'."""
    return conn.execute(SQL_SEARCH, {"q": qvec, "k": k, "kind": kind}).fetchall()


def connect():
    import psycopg
    from pgvector.psycopg import register_vector
    conn = psycopg.connect(DB_DSN, autocommit=True)
    register_vector(conn)       # numpy.ndarray <-> typ vector
    return conn


TZ = ZoneInfo("Europe/Warsaw")
STATE = {1: "Clearing", 2: "Stopped", 3: "Starting", 4: "Idle", 5: "Suspended", 6: "Execute", 7: "Stopping",
         8: "Aborting", 9: "Aborted", 11: "Held", 15: "Resetting"}


def case_text(r):
    """Wiersz stop_event -> opis postoju po polsku (jedno źródło 'stop:<t_start UTC ISO>')."""
    t_start, t_end, state, reason, cause, conf, ev, clip = r
    ev = ev or {}
    plc, vis = ev.get("plc", {}), ev.get("vision", {})
    states = ", ".join("{} ({})".format(STATE.get(s, "nieznany"), s) for s in plc.get("states", [state]))
    lines = [
        "Postój {} czasu lokalnego, trwał {:.0f} s.".format(
            t_start.astimezone(TZ).strftime("%d.%m.%Y %H:%M:%S"), (t_end - t_start).total_seconds()),
        "Stany po Execute: {}. Kod iStopReason: {}.".format(states, reason),
        "Przyczyna: {}, pewność: {}.".format(cause, conf),
    ]
    if ev.get("secondary"):
        lines.append("Kolejne przyczyny w tym postoju: {}.".format(", ".join(ev["secondary"])))
    lines.append("Sztuk w 30 s przed postojem: {}, ostatni czas cyklu: {} ms.".format(
        plc.get("pieces_in_window"), plc.get("cycle_ms")))
    if vis.get("offline_in_window"):
        lines.append("Kamera była offline w oknie postoju.")
    else:
        lines.append("Kamera: obiekty {}, przewrócone butelki w chwilach {} s względem postoju, "
                     "ostatnia sztuka {} s przed postojem.".format(
                         ", ".join("{} {}".format(c, n) for c, n in (vis.get("counts") or {}).items()) or "brak",
                         ", ".join(str(x) for x in vis.get("fallen_at_s") or []) or "brak", vis.get("last_item_s_before")))
    if ev.get("note"):
        lines.append("Uwaga: {}.".format(ev["note"]))
    lines.append("Klip: {}.".format(clip or "brak"))
    return "\n".join(lines)
