"""E5-05: jedna funkcja generate() dla dwóch dostawców LLM: Ollama (lokalnie, domyślny) i Gemini (API, darmowy poziom).

Bez SDK, czyste HTTP: oba wywołania mają ten sam kształt (instrukcja systemowa + treść użytkownika -> tekst),
więc reszta kodu (rag.py, ewaluacja) nie wie, który model odpowiada. temperature 0 = odpowiedzi powtarzalne,
co jest warunkiem sensownej ewaluacji (ten sam zestaw pytań -> te same odpowiedzi).

Zmienne środowiskowe:
  LLM_BACKEND   ollama | gemini                       (domyślnie ollama)
  OLLAMA_URL    http://localhost:11434                (z kontenera: http://host.docker.internal:11434)
  OLLAMA_MODEL  qwen3:4b-instruct                     (wariant bez trybu myślenia; :4b to dziś wersja thinking)
  OLLAMA_CTX    4096                                  okno kontekstu; za długi prompt Ollama PRZYCINA bez błędu
  GEMINI_MODEL  gemini-flash-latest                   alias na bieżący model Flash
  GEMINI_API_KEY                                      klucz z Google AI Studio (nie trafia do repo)
"""
import os
import time

import requests

BACKEND = os.environ.get("LLM_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")
OLLAMA_CTX = int(os.environ.get("OLLAMA_CTX", "4096"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def _ollama(system, user):
    r = requests.post(OLLAMA_URL + "/api/chat", timeout=300, json={
        "model": OLLAMA_MODEL, "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_ctx": OLLAMA_CTX}})
    r.raise_for_status()
    j = r.json()
    return j["message"]["content"], {"model": OLLAMA_MODEL, "prompt_tokens": j.get("prompt_eval_count"),
                                     "output_tokens": j.get("eval_count")}


def _gemini(system, user):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Brak GEMINI_API_KEY")
    r = requests.post(GEMINI_URL.format(GEMINI_MODEL), timeout=120, headers={"x-goog-api-key": key}, json={
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0}})
    r.raise_for_status()
    j = r.json()
    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    u = j.get("usageMetadata", {})
    return text, {"model": GEMINI_MODEL, "prompt_tokens": u.get("promptTokenCount"),
                  "output_tokens": u.get("candidatesTokenCount")}


def generate(system, user, backend=None):
    """-> (tekst, meta: model, tokeny, czas [s]). Wyjątek przy błędzie HTTP – wołający decyduje, co dalej."""
    backend = backend or BACKEND
    t0 = time.time()
    text, meta = {"ollama": _ollama, "gemini": _gemini}[backend](system, user)
    meta.update(backend=backend, seconds=round(time.time() - t0, 2))
    if backend == "ollama" and meta["prompt_tokens"] and meta["prompt_tokens"] >= OLLAMA_CTX - 50:
        meta["warning"] = "prompt na granicy okna kontekstu – mógł zostać przycięty"
    return text.strip(), meta
