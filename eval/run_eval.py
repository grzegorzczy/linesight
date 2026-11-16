"""E5-07: automatyczna ewaluacja asystenta na zestawie eval/questions.jsonl.

    python eval\\run_eval.py --name rag_ollama                          # RAG + qwen3:4b-instruct (Ollama)
    python eval\\run_eval.py --name norag_ollama --mode norag           # ten sam model BEZ źródeł (punkt odniesienia)
    python eval\\run_eval.py --name rag_ollama --judge gemini           # + sędzia LLM (zmyślenia, poprawność)
    python eval\\run_eval.py --name rag_gemini --backend gemini --judge gemini
    python eval\\run_eval.py --summary                                  # tabela wszystkich przebiegów z eval/results

Miary deterministyczne (bez LLM, powtarzalne, tanie):
  stop_ok    – asystent wziął właściwy postój (albo poprawnie stwierdził, że postoju nie było)
  recall@k   – wśród k fragmentów instrukcji jest co najmniej jedna sekcja wzorcowa (pytania z polem sources)
  facts      – odsetek wymaganych faktów obecnych w odpowiedzi (grupy wariantów, bez ogonków i wielkości liter)
  cited      – odpowiedź na pytanie z odpowiedzią ma co najmniej jeden cytat [ID]
  bad_cite   – cytat źródła, którego nie było w kontekście (twardy sygnał zmyślenia)
  refusal_ok – pytanie bez odpowiedzi: asystent odmówił; false_refusal – odmówił, choć odpowiedź była w źródłach
Sędzia LLM (opcjonalnie, inny model niż odpowiadający – mniejsze ryzyko, że model „ocenia sam siebie” łagodnie):
  unsupported – twierdzenia bez pokrycia w źródłach; contradiction – sprzeczne ze źródłami; correct 0/1/2 vs wzorzec
  halluc      – odpowiedź ma co najmniej jedno twierdzenie bez pokrycia albo sprzeczne, albo zły cytat
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "assistant"))

from llm import generate  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"
REFUSAL = re.compile(r"nie wiem|nie ma tej informacji|brak (tej )?informacji|nie zawieraj|nie podaj|"
                     r"don't know|do not know|not contain|no information|not available in the", re.I)

NORAG_SYSTEM = {
    "pl": "Jesteś asystentem technika mini linii pakującej. Odpowiadaj po polsku, zwięźle (do 150 słów). "
          "Jeśli nie znasz odpowiedzi, napisz: \"Nie wiem\".",
    "en": "You are an assistant for technicians of a mini packaging line. Answer in English, concisely (up to 150 "
          "words). If you do not know the answer, write: \"I don't know\".",
}

JUDGE_SYSTEM = """You evaluate answers of a RAG assistant for a packaging line. You get SOURCES (the only knowledge the
assistant had; may be in Polish), the QUESTION, a REFERENCE answer written by an engineer, and the ANSWER.
Return JSON only:
{"unsupported": [claims in ANSWER not supported by SOURCES], "contradictions": [claims in ANSWER that contradict SOURCES],
 "correct": 0 | 1 | 2, "comment": "one sentence"}
Rules: a claim is supported if SOURCES state it or it is a trivial paraphrase/translation. Generic polite phrases and
"I don't know" are not claims. correct: 2 = covers the key points of REFERENCE without errors, 1 = partly, 0 = wrong or
misses the main point. If REFERENCE says the correct reply is a refusal, an honest refusal scores 2."""


def norm(text):
    t = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    return "".join(c for c in t if not unicodedata.combining(c))


def facts_score(answer, must):
    a = norm(answer)
    hits = [any(norm(v) in a for v in group) for group in must]
    return (sum(hits) / len(hits) if hits else None), [g[0] for g, h in zip(must, hits) if not h]


def judge(q, answer, sources, backend):
    src = "\n\n".join("[{}] {}\n{}".format(s["id"], s["title"], s["text"]) for s in sources) or "(no sources)"
    user = "SOURCES:\n{}\n\nQUESTION: {}\n\nREFERENCE: {}\n\nANSWER: {}".format(src, q["question"], q["reference"],
                                                                               answer)
    text, _ = generate(JUDGE_SYSTEM, user, backend, json_mode=True)
    try:
        j = json.loads(text)
    except ValueError:
        return {"judge_error": text[:200]}
    return {"unsupported": j.get("unsupported", []), "contradictions": j.get("contradictions", []),
            "correct": j.get("correct"), "judge_comment": j.get("comment", "")}


def evaluate(q, r):
    """q: pytanie z zestawu, r: wynik rag.answer (albo odpowiedź bez RAG). -> miary deterministyczne."""
    ans, srcs = r["answer"], r.get("sources", [])
    m = {}
    if q["type"] in ("stop", "no_stop") and srcs:
        p1 = next((s for s in srcs if s["id"] == "P1"), None)
        if q["type"] == "stop":
            m["stop_ok"] = bool(p1 and q["stop"] in p1["title"])
        else:
            m["stop_ok"] = bool(p1 and p1["title"] == "Brak postoju")
    if q["sources"] and srcs:
        titles = [s["title"] for s in srcs if s["id"].startswith("S")]
        m["recall"] = any(g in t for g in q["sources"] for t in titles)
    refused = bool(REFUSAL.search(ans))
    if q["answerable"]:
        m["facts"], m["missing"] = facts_score(ans, q["must"])
        m["false_refusal"] = refused
        if srcs:
            m["cited"] = bool(r.get("cited"))
    else:
        m["refusal_ok"] = refused
    if srcs:
        m["bad_cite"] = len(r["meta"].get("unknown_citations", []))
    return m


def run(a):
    from kb import Embedder, connect
    from rag import answer, language
    qs = [json.loads(line) for line in open(QUESTIONS, encoding="utf-8")]
    if a.only:
        qs = [q for q in qs if q["id"] in a.only]
    emb = conn = None
    if a.mode == "rag":
        emb, conn = Embedder(), connect()
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "{}.jsonl".format(a.name)
    rows = []
    with open(out, "w", encoding="utf-8") as f:
        for q in qs:
            if a.mode == "rag":
                r = answer(conn, emb, q["question"], backend=a.backend, k=a.k)
            else:
                text, meta = generate(NORAG_SYSTEM[language(q["question"])], q["question"], a.backend)
                r = {"answer": text, "sources": [], "cited": [], "meta": meta}
            m = evaluate(q, r)
            if a.judge:
                time.sleep(a.delay)                       # darmowy poziom Gemini: limit zapytań na minutę
                m.update(judge(q, r["answer"], r["sources"], a.judge))
                m["halluc"] = bool(m.get("unsupported") or m.get("contradictions") or m.get("bad_cite"))
            row = {"id": q["id"], "type": q["type"], "lang": q["lang"], "question": q["question"],
                   "answer": r["answer"], "metrics": m, "seconds": r["meta"].get("seconds"),
                   "model": r["meta"].get("model"), "mode": a.mode, "k": a.k,
                   "sources": [{k: s.get(k) for k in ("id", "title", "dist")} for s in r["sources"]]}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            rows.append(row)
            flag = " ".join("{}={}".format(k, v) for k, v in m.items()
                            if k in ("stop_ok", "recall", "facts", "refusal_ok", "false_refusal", "bad_cite",
                                     "correct", "halluc") and v not in (None,))
            print("{:<4} {:>5}s  {}".format(q["id"], r["meta"].get("seconds"), flag), flush=True)
            if a.backend == "gemini":
                time.sleep(a.delay)
    print("\nWyniki: {}".format(out))
    print_summary([(a.name, rows)])


def agg(rows):
    def mean(key, pred=lambda r: True):
        v = [r["metrics"][key] for r in rows if key in r["metrics"] and r["metrics"][key] is not None and pred(r)]
        return (sum(float(x) for x in v) / len(v), len(v)) if v else (None, 0)
    out = {"n": len(rows)}
    for key in ("stop_ok", "recall", "facts", "cited", "refusal_ok", "false_refusal", "halluc"):
        out[key] = mean(key)
    out["correct"] = mean("correct")
    out["bad_cite"] = (sum(r["metrics"].get("bad_cite", 0) for r in rows), len(rows))
    secs = [r["seconds"] for r in rows if r.get("seconds")]
    out["sec_mean"] = (sum(secs) / len(secs), len(secs)) if secs else (None, 0)
    for lang in ("pl", "en"):
        out["facts_" + lang] = mean("facts", lambda r, lang=lang: r["lang"] == lang)
    return out


def fmt(v, pct=True):
    val, n = v
    if val is None:
        return "–"
    return "{:.0f} %".format(100 * val) if pct else "{:.2f}".format(val)


def print_summary(runs):
    cols = [("stop_ok", "postój", 1), ("recall", "recall@k", 1), ("facts", "fakty", 1), ("facts_pl", "fakty PL", 1),
            ("facts_en", "fakty EN", 1), ("cited", "cytaty", 1), ("refusal_ok", "odmowy OK", 1),
            ("false_refusal", "zbędne odmowy", 1), ("halluc", "zmyślenia", 1), ("correct", "poprawność 0-2", 0),
            ("sec_mean", "s/odp.", 0)]
    lines = ["| przebieg | n | " + " | ".join(c[1] for c in cols) + " | złe cytaty |",
             "|---" * (len(cols) + 3) + "|"]
    for name, rows in runs:
        s = agg(rows)
        lines.append("| {} | {} | ".format(name, s["n"]) + " | ".join(fmt(s[c[0]], c[2]) for c in cols) +
                     " | {} |".format(s["bad_cite"][0]))
    print("\n".join(lines))
    return "\n".join(lines)


def summary():
    runs = []
    for p in sorted(RESULTS.glob("*.jsonl")):
        runs.append((p.stem, [json.loads(line) for line in open(p, encoding="utf-8")]))
    table = print_summary(runs)
    (RESULTS / "summary.md").write_text("# Wyniki ewaluacji asystenta\n\n" + table + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", help="nazwa przebiegu = plik eval/results/<name>.jsonl")
    ap.add_argument("--mode", choices=["rag", "norag"], default="rag")
    ap.add_argument("--backend", choices=["ollama", "gemini"], default="ollama")
    ap.add_argument("--judge", choices=["ollama", "gemini"], help="sędzia LLM (domyślnie brak)")
    ap.add_argument("-k", type=int, default=4, help="liczba fragmentów instrukcji")
    ap.add_argument("--delay", type=float, default=4.0, help="przerwa przed zapytaniem do Gemini [s]")
    ap.add_argument("--only", nargs="+", help="tylko wskazane pytania, np. --only P05 P10")
    ap.add_argument("--summary", action="store_true", help="tabela wszystkich przebiegów")
    a = ap.parse_args()
    if a.summary:
        summary()
    elif a.name:
        run(a)
    else:
        ap.error("podaj --name albo --summary")


if __name__ == "__main__":
    main()
