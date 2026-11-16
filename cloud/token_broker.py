"""E6-03: broker krótkotrwałych tokenów GCP dla Jetsona (laptop, Docker).

Dlaczego: organizacja GCP tego konta wymusza politykę iam.disableServiceAccountKeyCreation (secure by default),
więc Jetson nie dostanie klucza JSON. Zamiast tego laptop – zalogowany kontem użytkownika (ADC) z rolą
roles/iam.serviceAccountTokenCreator na koncie usługi jetson-edge – podszywa się pod to konto (impersonation)
i wydaje token OAuth ważny 1 h. Jetson rozmawia z Cloud Storage sam, ale tylko z uprawnieniami jetson-edge
(odczyt modeli, dodawanie klatek), a na urządzeniu nie leży żaden długoterminowy sekret Google.

GET /token   nagłówek "Authorization: Bearer <BROKER_SECRET>"  ->  {"access_token": ..., "expires_in": s}
GET /health  bez autoryzacji -> {"ok": true, "sa": ...}
"""
import datetime as dt
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import Request

SA = os.environ.get("TARGET_SA", "jetson-edge@linesight-514914.iam.gserviceaccount.com")
SECRET = os.environ.get("BROKER_SECRET", "")   # wspólny sekret z Jetsonem (zmienna Windows, nie w repo)
if len(SECRET) < 16:
    raise SystemExit("BROKER_SECRET pusty lub krótszy niż 16 znaków – ustaw zmienną Windows (setx) i zrestartuj kontener")
SCOPES = ["https://www.googleapis.com/auth/devstorage.read_write"]   # i tak ogranicza IAM jetson-edge
LIFETIME_S = 3600
REFRESH_MARGIN_S = 300   # nowy token, gdy do wygaśnięcia zostało < 5 min

_lock = threading.Lock()
_source, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
_creds = impersonated_credentials.Credentials(
    source_credentials=_source, target_principal=SA, target_scopes=SCOPES, lifetime=LIFETIME_S)


def get_token():
    """Token z pamięci; odświeżany tylko blisko wygaśnięcia (mniej wywołań IAM Credentials API)."""
    with _lock:
        now = dt.datetime.utcnow()   # google-auth trzyma expiry jako naiwny czas UTC
        if not _creds.token or (_creds.expiry - now).total_seconds() < REFRESH_MARGIN_S:
            _creds.refresh(Request())
            print("nowy token dla {}, ważny do {}Z".format(SA, _creds.expiry.isoformat(timespec="seconds")),
                  flush=True)
        return _creds.token, int((_creds.expiry - now).total_seconds())


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "sa": SA})
        if self.path != "/token":
            return self._send(404, {"error": "not found"})
        auth = self.headers.get("Authorization", "")
        if not hmac.compare_digest(auth, "Bearer " + SECRET):   # porównanie w stałym czasie
            return self._send(401, {"error": "unauthorized"})
        try:
            token, expires_in = get_token()
        except Exception as e:   # np. brak roli TokenCreator, wygasłe ADC
            return self._send(502, {"error": type(e).__name__, "detail": str(e)[:300]})
        self._send(200, {"access_token": token, "expires_in": expires_in, "sa": SA})

    def log_message(self, fmt, *args):   # bez tokenów w logach; tylko kto i jaki kod
        print("{} {}".format(self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8010"))
    print("token broker: {} na :{}".format(SA, port), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
