"""E5-05: jedna funkcja generate() dla dwóch dostawców LLM: Ollama (lokalnie, domyślny) i Gemini (API, darmowy poziom).

Bez SDK, czyste HTTP: oba wywołania mają ten sam kształt (instrukcja systemowa + treść użytkownika -> tekst),
więc reszta kodu (rag.py, ewaluacja) nie wie, który model odpowiada. temperature 0 = odpowiedzi powtarzalne,
co jest warunkiem sensownej ewaluacji (ten sam zestaw pytań -> te same odpowiedzi).

Zmienne środowiskowe:
  LLM_BACKEND   ollama | gemini                       (domyślnie ollama)
  OLLAMA_URL    http://localhost:11434                (z kontenera: http://host.docker.internal:11434)
  OLLAMA_MODEL  qwen3:4b-instruct                     (wariant bez trybu myślenia; :4b to dziś wersja thinking)
  OLLAMA_CTX    4096                                  okno kontekstu; za długi prompt Ollama PRZYCINA bez błędu
  GEMINI_MODEL  gemini-3.5-flash-lite                 lekki model Flash z darmowego poziomu
  GEMINI_API_KEY                                      klucz z Google AI Studio (nie trafia do repo)
  OLLAMA_KEEP_ALIVE  30m                              jak długo model zostaje w VRAM po ostatnim pytaniu

Ustawienia SERWERA Ollamy (Windows, setx + ponowne uruchomienie Ollamy), test 15.11:
  OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0 -> KV cache 306 MiB zamiast ok. 600 MiB, model 3,3 GB,
  37/37 warstw na GPU (wcześniej 3,6 GB i podział 20/80 CPU/GPU na 4 GB VRAM).
"""
import os
import time

import requests

BACKEND = os.environ.get("LLM_BACKEND", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-instruct")
OLLAMA_CTX = int(os.environ.get("OLLAMA_CTX", "4096"))
# Ładowanie modelu do VRAM trwa ok. 19 s (test 15.11) – domyślne 5 min bezczynności to zimny start co chwilę
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
# 16.11: alias gemini-flash-latest -> 503 i brak odpowiedzi w 120 s; gemini-3.5-flash-lite odpowiada w ok. 1,4 s
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_TIMEOUT_S = float(os.environ.get("GEMINI_TIMEOUT_S", "60"))
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


class LLMUnavailable(RuntimeError):
    """Dostawca LLM nieosiągalny (serwer nie działa, brak klucza) – usługa zwraca 503, nie 500."""


def _ollama(system, user, json_mode=False, model=None):
    model = model or OLLAMA_MODEL
    try:
        r = requests.post(OLLAMA_URL + "/api/chat", timeout=300, json={
            "model": model, "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "seed": 42, "num_ctx": OLLAMA_CTX}, **({"format": "json"} if json_mode else {})})
    except requests.ConnectionError:
        raise LLMUnavailable("Ollama nie odpowiada pod {} – uruchom Ollamę (menu Start albo `ollama serve`)".format(
            OLLAMA_URL)) from None
    r.raise_for_status()
    j = r.json()
    return j["message"]["content"], {"model": model, "prompt_tokens": j.get("prompt_eval_count"),
                                     "output_tokens": j.get("eval_count"),
                                     "load_s": round(j.get("load_duration", 0) / 1e9, 2)}


RETRY_STATUS = {429, 500, 503}          # limit zapytań / przeciążenie po stronie Google – zwykle mija po chwili
RETRY_WAIT_S = (5, 15, 30)


def _gemini(system, user, json_mode=False, model=None):
    model = model or GEMINI_MODEL
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMUnavailable("Brak GEMINI_API_KEY")
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": dict({"temperature": 0}, **({"responseMimeType": "application/json"} if json_mode else {}))}
    for wait in RETRY_WAIT_S + (None,):
        try:
            r = requests.post(GEMINI_URL.format(model), timeout=GEMINI_TIMEOUT_S, headers={"x-goog-api-key": key},
                              json=body)
            status = r.status_code
        except requests.Timeout:            # przeciążony model potrafi nie odpowiedzieć wcale (16.11, 120 s)
            r, status = None, "timeout"
        if status not in RETRY_STATUS and status != "timeout" or wait is None:
            break
        print("Gemini {} – ponowienie za {} s".format(status, wait), flush=True)
        time.sleep(wait)
    if r is None or r.status_code in RETRY_STATUS:
        raise LLMUnavailable("Gemini ({}) {} po {} próbach: {}".format(
            model, status, len(RETRY_WAIT_S) + 1, r.text[:300] if r is not None else "brak odpowiedzi"))
    if r.status_code != 200:
        raise RuntimeError("Gemini {}: {}".format(r.status_code, r.text[:300]))   # np. 404 = zła nazwa modelu
    j = r.json()
    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    u = j.get("usageMetadata", {})
    return text, {"model": model, "prompt_tokens": u.get("promptTokenCount"),
                  "output_tokens": u.get("candidatesTokenCount")}


def generate(system, user, backend=None, json_mode=False, model=None):
    """-> (tekst, meta: model, tokeny, czas [s]). Wyjątek przy błędzie HTTP – wołający decyduje, co dalej.
    json_mode=True: dostawca wymusza poprawny JSON (sędzia w ewaluacji); model: inny niż domyślny (sędzia)."""
    backend = backend or BACKEND
    t0 = time.time()
    text, meta = {"ollama": _ollama, "gemini": _gemini}[backend](system, user, json_mode, model)
    meta.update(backend=backend, seconds=round(time.time() - t0, 2))
    if backend == "ollama" and meta["prompt_tokens"] and meta["prompt_tokens"] >= OLLAMA_CTX - 50:
        meta["warning"] = "prompt na granicy okna kontekstu – mógł zostać przycięty"
    return text.strip(), meta
