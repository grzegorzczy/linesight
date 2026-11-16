"""E5-05: odpowiedź asystenta = kontekst postoju (SQL) + fragmenty instrukcji (pgvector) + LLM ze źródłami.

    python assistant/rag.py "dlaczego linia stanęła o 10:23?"
    python assistant/rag.py "what should I do when the line is in Held?"
    python assistant/rag.py --backend gemini "co oznacza kod 302?"

Przebieg:
1. Pytanie o konkretny postój (godzina w pytaniu, „ostatni postój”, parametr stop z Grafany) -> context.py:
   [P1] postój, [P2] sygnały 30 s, [P3] napęd. Godzina bez postoju -> [P1] mówi wprost, że postoju nie było.
2. Zawsze: k fragmentów instrukcji z pgvector -> [S1..Sk]. Pytanie o historię bez konkretnego postoju
   ("czy zatory się powtarzają") -> także 2 podobne postoje -> [H1, H2].
3. Prompt: odpowiadaj tylko ze źródeł, po każdym stwierdzeniu [ID], „nie wiem”, gdy źródła nie wystarczają.
4. Wynik: odpowiedź + lista źródeł z identyfikatorami, odległościami i linkiem do klipu (do UI i do ewaluacji).
"""
import argparse
import json
import re
import time

from context import MATCH_S, find_stop, parse_when, stop_sources
from kb import TZ, Embedder, connect, search
from llm import LLMUnavailable, generate

K_MANUAL = 4
K_CASES = 2
RE_LAST = re.compile(r"ostatni\w*\s+post[oó]j|last\s+stop", re.I)
# polskie znaki albo częste polskie słowa (także w pytaniach bez ogonków: "jaki jest numer telefonu")
RE_PL = re.compile(r"[ąćęłńóśźż]|\b(co|czy|jak\w*|jaki\w*|gdzie|kto|kt[oó]r\w*|dlaczego|kiedy|ile|czym|jest|sie|nie|"
                   r"post[oó]j\w*|lini\w*|zator\w*|naped\w*)\b", re.I)
# podobne postoje z historii [H] tylko, gdy pytanie jest o historię – inaczej to szum (test 15.11: "restart_plc"
# doklejony do pytania o alarm napędu)
RE_HISTORY = re.compile(r"histori|powtarza|wcze[sś]niej|ile razy|jak cz[eę]sto|ostatnio|poprzedni|"
                        r"history|before|again|how often|previous|recent", re.I)

SYSTEM = {
    "pl": """Jesteś asystentem technika mini linii pakującej LineSight. Odpowiadasz WYŁĄCZNIE na podstawie źródeł
podanych w wiadomości (bloki [P1], [S1], [H1] itd.). Zasady:
- Po każdym zdaniu z faktem podaj identyfikator źródła w nawiasie kwadratowym, np. [P1] albo [S2].
- Nie dodawaj faktów, liczb, kodów ani procedur, których nie ma w źródłach.
- Jeśli źródła nie wystarczają do odpowiedzi, napisz: "Nie wiem – w dostępnych źródłach nie ma tej informacji." i nic nie zmyślaj.
- Przy pytaniu o postój: najpierw przyczyna i pewność, potem dowody (sygnały, kamera), potem co zrobić według instrukcji.
- Jeśli źródło podaje link do klipu, podaj go.
- Źródła [H] to tylko przykłady podobnych postojów, nie cała historia: nie licz na ich podstawie, ile razy coś się
  zdarzyło – napisz, że nie masz pełnej historii, i podaj przykłady.
- Odpowiadaj po polsku, zwięźle (do 150 słów).""",
    "en": """You are an assistant for technicians of the LineSight mini packaging line. Answer ONLY from the sources
given in the message (blocks [P1], [S1], [H1] etc.); sources may be in Polish. Rules:
- After every sentence that states a fact, cite the source id in square brackets, e.g. [P1] or [S2].
- Do not add facts, numbers, codes or procedures that are not in the sources.
- If the sources are not sufficient, write: "I don't know – the available sources do not contain this information." and invent nothing.
- For a question about a stop: first the cause and confidence, then the evidence (signals, camera), then what to do according to the manual.
- If a source gives a clip link, include it.
- Sources [H] are only examples of similar stops, not the full history: do not count how often something happened from
  them – say that you do not have the full history and give the examples.
- Answer in English, concisely (up to 150 words).""",
}


def language(question):
    """Prosta heurystyka zamiast modelu: polskie znaki albo polskie słowa pytające -> pl, inaczej en."""
    return "pl" if RE_PL.search(question) else "en"


def gather(conn, emb, question, stop_t=None, k=K_MANUAL):
    """Zbiera źródła: [{"id", "title", "text", "url", "source", "dist"}]."""
    sources, extra = [], ""
    when = None if stop_t else parse_when(question)
    if stop_t or when or RE_LAST.search(question):
        stop = find_stop(conn, stop_t or when, exact=bool(stop_t))
        if stop:
            sources += stop_sources(conn, stop)
            # Pytanie „dlaczego stanęła o 9:07” nie mówi nic o przyczynie, więc wyszukiwanie zwracało losowe sekcje
            # o stanach (ewaluacja 16.11: recall 81 %, brak sekcji 302 -> model nazwał abort „usterką”).
            # Dopisujemy przyczynę i kod z [P1] do zapytania wektorowego – instrukcja trafia w procedurę.
            secondary = ((stop[6] or {}).get("secondary") or [])
            extra = " Przyczyna: {}. Kod {}. Procedura postępowania.".format(
                ", ".join([stop[4] or "nieznana"] + secondary).replace("_", " "), stop[3])
        else:
            t = when.astimezone(TZ).strftime("%d.%m.%Y %H:%M") if when else "-"
            sources.append({"id": "P1", "title": "Brak postoju", "url": None, "source": "stop_event",
                            "text": "W bazie postojów nie ma postoju w ± {} s od {} (czas lokalny). "
                                    "Linia w tym czasie nie stała.".format(MATCH_S, t)})
    q = emb.query(question + extra)
    for i, (_, kind, src, sec, text, dist) in enumerate(search(conn, q, k, "manual"), 1):
        sources.append({"id": "S{}".format(i), "title": sec, "text": text, "url": None, "source": src,
                        "dist": round(float(dist), 3)})
    if not any(s["id"] == "P1" for s in sources) and RE_HISTORY.search(question):
        for i, (_, kind, src, sec, text, dist) in enumerate(search(conn, q, K_CASES, "case"), 1):
            sources.append({"id": "H{}".format(i), "title": "Przykład podobnego postoju (NIE pełna historia): " + sec,
                            "text": text, "url": None, "source": src,
                            "dist": round(float(dist), 3)})
    return sources


def prompt(question, sources):
    blocks = "\n\n".join("[{}] {}\n{}".format(s["id"], s["title"], s["text"]) for s in sources)
    return "ŹRÓDŁA / SOURCES:\n\n{}\n\nPYTANIE / QUESTION: {}".format(blocks, question)


def answer(conn, emb, question, stop_t=None, backend=None, k=K_MANUAL):
    t0 = time.time()
    sources = gather(conn, emb, question, stop_t, k)
    t_ret = time.time() - t0
    lang = language(question)
    text, meta = generate(SYSTEM[lang], prompt(question, sources), backend)
    cited = sorted(set(re.findall(r"[PSH]\d+", " ".join(re.findall(r"\[([PSH\d,;\s]+)\]", text)))))   # [P1] i [P1, S2]
    meta.update(language=lang, retrieval_s=round(t_ret, 2),
                unknown_citations=[c for c in cited if c not in {s["id"] for s in sources}])
    return {"question": question, "answer": text, "cited": cited, "sources": sources, "meta": meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--backend", choices=["ollama", "gemini"])
    ap.add_argument("--json", action="store_true", help="pełny wynik (źródła z treścią) jako JSON")
    a = ap.parse_args()
    emb, conn = Embedder(), connect()
    try:
        r = answer(conn, emb, " ".join(a.question), backend=a.backend)
    except LLMUnavailable as e:
        raise SystemExit("Błąd: {}".format(e))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        return
    print("\n" + r["answer"] + "\n")
    for s in r["sources"]:
        mark = "*" if s["id"] in r["cited"] else " "
        print("{} [{}] {}{}{}".format(mark, s["id"], s["title"],
                                      "  dist {}".format(s["dist"]) if "dist" in s else "",
                                      "  " + s["url"] if s.get("url") else ""))
    print("\n" + json.dumps(r["meta"], ensure_ascii=False))


if __name__ == "__main__":
    main()
