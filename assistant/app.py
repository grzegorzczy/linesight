"""E5-05: usługa HTTP asystenta (FastAPI).

    uvicorn app:app --app-dir assistant --port 8000      (albo usługa assistant w infra/docker-compose.yml)
    http://localhost:8000/                           (strona dla technika; ?stop=<t_start ISO> – link z Grafany)
    http://localhost:8000/ask?q=dlaczego%20linia%20stanęła%20o%2010:23
    http://localhost:8000/docs                       (Swagger – formularz do testów)

Model embeddingów i połączenie z bazą ładujemy raz przy starcie, nie przy każdym pytaniu (ok. 3 s i 470 MB).
"""
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from kb import Embedder, connect
from llm import LLMUnavailable
from rag import answer

state = {}


@asynccontextmanager
async def lifespan(app):
    state["emb"], state["conn"] = Embedder(), connect()
    yield
    state["conn"].close()


app = FastAPI(title="LineSight – asystent postojów", lifespan=lifespan)


@app.get("/ask")
def ask(q: str, stop: Optional[datetime] = None, backend: Optional[str] = None):
    """q – pytanie; stop – t_start postoju (ISO, z linku w Grafanie); backend – ollama | gemini."""
    if backend not in (None, "ollama", "gemini"):
        raise HTTPException(400, "backend: ollama | gemini")
    try:
        return answer(state["conn"], state["emb"], q, stop_t=stop, backend=backend)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))


@app.get("/health")
def health():
    return {"ok": state["conn"].execute("SELECT 1").fetchone()[0] == 1}


PAGE = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LineSight – asystent</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;background:#111217;color:#d8d9da}
 h1{font-size:20px} input,select,button{font-size:15px;padding:8px;border-radius:4px;border:1px solid #444;
 background:#1f2026;color:#d8d9da} input{width:100%;box-sizing:border-box;margin:8px 0}
 button{background:#3d71d9;border:0;color:#fff;cursor:pointer} #ans{white-space:pre-wrap;line-height:1.5;margin-top:16px}
 .src{font-size:13px;color:#9fa1a6;margin-top:16px} .src li{margin:3px 0} a{color:#6e9fff} .meta{font-size:12px;color:#777}
 .stop{background:#1f2026;padding:8px 12px;border-left:3px solid #f2cc0c;margin:8px 0;font-size:14px}
</style></head><body>
<h1>LineSight – dlaczego linia stanęła?</h1>
<div id="stop" class="stop" hidden></div>
<form id="f"><input id="q" placeholder="np. Dlaczego linia stanęła o 9:40? / What should I do when the line is in Held?">
<select id="b"><option value="">model: domyślny</option><option value="ollama">Ollama (lokalnie)</option>
<option value="gemini">Gemini (chmura)</option></select> <button>Zapytaj</button></form>
<div id="ans"></div><ul id="src" class="src"></ul><div id="meta" class="meta"></div>
<script>
const P = new URLSearchParams(location.search), stop = P.get("stop");
if (P.get("embed")) { document.body.style.margin = "4px auto"; document.querySelector("h1").hidden = true; }
const q = document.getElementById("q");
if (stop) { const d = document.getElementById("stop"); d.hidden = false;
  d.textContent = "Postój z Grafany: " + new Date(stop).toLocaleString("pl-PL");
  q.value = P.get("q") || "Dlaczego linia stanęła i co zrobić?"; }
async function ask(e) { if (e) e.preventDefault();
  const ans = document.getElementById("ans"), src = document.getElementById("src"), meta = document.getElementById("meta");
  ans.textContent = "…"; src.innerHTML = ""; meta.textContent = "";
  const u = new URLSearchParams({q: q.value}); if (stop) u.set("stop", stop);
  const b = document.getElementById("b").value; if (b) u.set("backend", b);
  const r = await fetch("ask?" + u); const j = await r.json();
  if (!r.ok) { ans.textContent = "Błąd: " + (j.detail || r.status); return; }
  ans.textContent = j.answer;
  for (const s of j.sources) { const li = document.createElement("li");
    li.textContent = (j.cited.includes(s.id) ? "• " : "  ") + "[" + s.id + "] " + s.title + " ";
    if (s.url) { const a = document.createElement("a"); a.href = s.url; a.target = "_blank"; a.textContent = "▶ klip";
      li.appendChild(a); }
    src.appendChild(li); }
  meta.textContent = j.meta.model + " · " + j.meta.seconds + " s · źródła oznaczone • są cytowane w odpowiedzi"; }
document.getElementById("f").onsubmit = ask;
if (stop) ask();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def page():
    """Strona dla technika: pytanie, odpowiedź, źródła z linkiem do klipu. Bez frameworka JS – jeden plik."""
    return PAGE
