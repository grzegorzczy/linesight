"""E5-07: automatyczna ewaluacja asystenta na zestawie eval/questions.jsonl.

    python eval\\run_eval.py --name rag_ollama                          # RAG + qwen3:4b-instruct (Ollama)
    python eval\\run_eval.py --name norag_ollama --mode norag           # ten sam model BEZ źródeł (punkt odniesienia)
    python eval\\run_eval.py --name rag_ollama --judge gemini --judge-model gemini-3.8-flash   # + sędzia LLM
    python eval\\run_eval.py --name rag_gemini --backend gemini --judge gemini
    python eval\\run_eval.py --summary                                  # tabela wszystkich przebiegów z eval/results
    python eval\\run_eval.py --rejudge rag_ollama_v2 --judge gemini --judge-model gemini-3.6-flash --judge-check

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

from llm import LLMUnavailable, generate  # noqa: E402

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

JUDGE_SYSTEM = """You verify answers of a RAG assistant for a packaging line. You get SOURCES (the only knowledge the
assistant had; mostly in Polish), the QUESTION, a REFERENCE answer written by an engineer, and the ANSWER.

Step 1 – split the ANSWER into atomic factual claims (one fact each; ignore citation markers like [P1]; skip polite
phrases and "I don't know"). Step 2 – give each claim a verdict:
  "supported"    – SOURCES state it, or it is a direct paraphrase/translation,
  "unsupported"  – SOURCES do not state it (including the assistant's own interpretations, explanations of causes,
                   or general knowledge),
  "contradicted" – SOURCES state the opposite.
Check these especially carefully: stop cause and code; confidence – "potwierdzona" = confirmed by the camera,
"tylko_plc" = only the PLC, the camera did NOT confirm, "sprzeczna" = the camera contradicts the PLC; whether an event
happened before or after the stop; counts ("how many times") – sources [H] are only examples, never the full history;
numbers and units.
Step 3 – correct: 2 = covers the key points of REFERENCE with no wrong statement, 1 = partly, or key points right but
one wrong statement, 0 = wrong main point or misses it. If REFERENCE says the correct reply is a refusal, an honest
refusal scores 2.
Return JSON only:
{"claims": [{"claim": "...", "verdict": "supported" | "unsupported" | "contradicted"}], "correct": 0 | 1 | 2,
 "comment": "one sentence"}"""


def norm(text):
    t = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    return "".join(c for c in t if not unicodedata.combining(c))


def facts_score(answer, must):
    a = norm(answer)
    hits = [any(norm(v) in a for v in group) for group in must]
    return (sum(hits) / len(hits) if hits else None), [g[0] for g, h in zip(must, hits) if not h]


def judge(q, answer, sources, backend, model=None):
    src = "\n\n".join("[{}] {}\n{}".format(s["id"], s["title"], s.get("text", "")) for s in sources) or "(no sources)"
    user = "SOURCES:\n{}\n\nQUESTION: {}\n\nREFERENCE: {}\n\nANSWER: {}".format(src, q["question"], q["reference"],
                                                                               answer)
    try:
        text, _ = generate(JUDGE_SYSTEM, user, backend, json_mode=True, model=model)
    except LLMUnavailable as e:                  # sędzia niedostępny: pytanie bez oceny, przebieg idzie dalej
        return {"judge_error": str(e)[:200]}
    try:
        j = json.loads(text)
    except ValueError:
        return {"judge_error": text[:200]}
    claims = j.get("claims", [])
    return {"unsupported": [c["claim"] for c in claims if c.get("verdict") == "unsupported"],
            "contradictions": [c["claim"] for c in claims if c.get("verdict") == "contradicted"],
            "n_claims": len(claims), "correct": j.get("correct"), "judge_comment": j.get("comment", "")}


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
                m.update(judge(q, r["answer"], r["sources"], a.judge, a.judge_model))
                if "judge_error" not in m:      # bez oceny sędziego nie wiemy – None, nie False (16.11: 503 -> False)
                    m["halluc"] = bool(m.get("unsupported") or m.get("contradictions") or m.get("bad_cite"))
            row = {"id": q["id"], "type": q["type"], "lang": q["lang"], "question": q["question"],
                   "answer": r["answer"], "metrics": m, "seconds": r["meta"].get("seconds"),
                   "model": r["meta"].get("model"), "mode": a.mode, "k": a.k,
                   "sources": [{k: s.get(k) for k in ("id", "title", "text", "dist")} for s in r["sources"]]}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            rows.append(row)
            flag = " ".join("{}={}".format(k, v) for k, v in m.items()
                            if k in ("stop_ok", "recall", "facts", "refusal_ok", "false_refusal", "bad_cite",
                                     "correct", "halluc", "judge_error") and v not in (None,))
            print("{:<4} {:>5}s  {}".format(q["id"], r["meta"].get("seconds"), flag), flush=True)
            if a.backend == "gemini":
                time.sleep(a.delay)
    print("\nWyniki: {}".format(out))
    print_summary([(a.name, rows)])


def rejudge(a):
    """Ocena sędziego dla zapisanych odpowiedzi (bez ponownego generowania): --rejudge <przebieg> -> <przebieg>__<model>."""
    qs = {q["id"]: q for q in (json.loads(line) for line in open(QUESTIONS, encoding="utf-8"))}
    src = RESULTS / "{}.jsonl".format(a.rejudge)
    rows = [json.loads(line) for line in open(src, encoding="utf-8")]
    if a.only:
        rows = [r for r in rows if r["id"] in a.only]
    if any("text" not in s for r in rows for s in r["sources"]):
        # starsze wyniki (do v2) bez treści źródeł: odtwarzamy je tym samym wyszukiwaniem (SQL + pgvector, bez LLM –
        # deterministyczne), tak jak widział je asystent
        from kb import Embedder, connect
        from rag import gather
        emb, conn = Embedder(), connect()
        for r in rows:
            r["sources"] = [{k: s.get(k) for k in ("id", "title", "text", "dist")}
                            for s in gather(conn, emb, r["question"], k=r.get("k", 4))]
    out = RESULTS / "{}__{}.jsonl".format(a.rejudge, a.judge_model or a.judge)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            m = {k: v for k, v in r["metrics"].items() if k not in ("unsupported", "contradictions", "n_claims",
                                                                   "correct", "judge_comment", "judge_error", "halluc")}
            time.sleep(a.delay)
            m.update(judge(qs[r["id"]], r["answer"], r["sources"], a.judge, a.judge_model))
            if "judge_error" not in m:
                m["halluc"] = bool(m.get("unsupported") or m.get("contradictions") or m.get("bad_cite"))
            r["metrics"] = m
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print("{:<4} halluc={} correct={} {}".format(r["id"], m.get("halluc"), m.get("correct"),
                                                         m.get("judge_error", "")), flush=True)
    print("\nWyniki: {}".format(out))
    return out


def judge_check(path):
    """Zgodność sędziego z ręcznymi ocenami (eval/judge_labels.jsonl) – sędziego też trzeba sprawdzić."""
    labels = [json.loads(line) for line in open(ROOT / "eval" / "judge_labels.jsonl", encoding="utf-8")]
    res = {r["id"]: r for r in (json.loads(line) for line in open(path, encoding="utf-8"))}
    got = {}
    for lab in labels:
        r = res.get(lab["id"])
        if r is not None and r["answer"].startswith(lab["answer_start"]):
            got[lab["id"]] = r["metrics"].get("halluc")
        elif r is not None:
            print("UWAGA {}: inna odpowiedź niż oceniona ręcznie – pomijam".format(lab["id"]))
    tp = fp = fn = tn = miss = 0
    for lab in labels:
        g = got.get(lab["id"])
        if g is None:
            miss += 1
            continue
        tp += g and lab["halluc"]
        fp += g and not lab["halluc"]
        fn += (not g) and lab["halluc"]
        tn += (not g) and not lab["halluc"]
        mark = "OK " if g == lab["halluc"] else "ŹLE"
        print("{} {:<4} człowiek={!s:<5} sędzia={!s:<5} {}".format(mark, lab["id"], lab["halluc"], g, lab["why"]))
    n = tp + fp + fn + tn
    print("\nZgodność {}/{}; wykryte zmyślenia {}/{} (czułość), fałszywe alarmy {}/{}; bez oceny {}".format(
        tp + tn, n, tp, tp + fn, fp, fp + tn, miss))


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
    ap.add_argument("--judge-model", help="model sędziego (np. gemini-3.8-flash); domyślnie jak GEMINI_MODEL")
    ap.add_argument("-k", type=int, default=4, help="liczba fragmentów instrukcji")
    ap.add_argument("--delay", type=float, default=4.0, help="przerwa przed zapytaniem do Gemini [s]")
    ap.add_argument("--only", nargs="+", help="tylko wskazane pytania, np. --only P05 P10")
    ap.add_argument("--summary", action="store_true", help="tabela wszystkich przebiegów")
    ap.add_argument("--rejudge", metavar="PRZEBIEG", help="ocena sędziego zapisanych odpowiedzi (wymaga --judge)")
    ap.add_argument("--judge-check", action="store_true", help="z --rejudge: zgodność z eval/judge_labels.jsonl")
    a = ap.parse_args()
    if a.summary:
        summary()
    elif a.rejudge:
        if not a.judge:
            ap.error("--rejudge wymaga --judge")
        out = rejudge(a)
        if a.judge_check:
            judge_check(out)
    elif a.name:
        try:
            run(a)
        except LLMUnavailable as e:
            raise SystemExit("Błąd: {}".format(e))
    else:
        ap.error("podaj --name albo --summary")


if __name__ == "__main__":
    main()
