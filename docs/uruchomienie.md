# Zimny start – cała linia od zera

Wszystko wyłączone → linia pracuje, Grafana pokazuje dane, asystent odpowiada. Kolejność ma znaczenie:
najpierw usługi na laptopie (broker MQTT i baza), potem sterownik, na końcu Jetson (wysyła zdarzenia do brokera).

Adresy: laptop 192.168.0.203, Jetson 192.168.0.124 (`grzegorz@grzegorz-desktop`), sterownik LineSight
192.168.0.244 (domyślny w repo) albo 192.168.0.90 (tymczasowo, 18.11).

Okna: **LAPTOP** (cmd w `C:\Users\Grzesiek\Desktop\linesight`, `.venv`), **OLLAMA** (cmd), **SSH1** i **SSH2** (Jetson),
**CODESYS**.

## 1. Laptop – usługi

| Krok | Komenda | Sprawdzenie |
|---|---|---|
| Kod | `git pull` | `Already up to date` albo lista zmian |
| Czas (diagnostyka łączy zdarzenia po czasie) | `w32tm /resync` | `Polecenie zostało wykonane pomyślnie` |
| Docker | uruchom Docker Desktop, poczekaj na „Engine running” | `docker info` bez błędu |
| Sterownik dla mostu – tylko gdy aplikacja jest na .90 | `set OPCUA_URL=opc.tcp://192.168.0.90:4840` | – (tylko to okno cmd) |
| Usługi | `docker compose -f infra\docker-compose.yml up -d` | `docker compose -f infra\docker-compose.yml ps` – 8 usług `Up`, `db` `healthy` |
| LLM (okno OLLAMA) | `ollama serve` (jeśli ikona Ollamy nie działa już w zasobniku) | LAPTOP: `ollama list` pokazuje `qwen3:4b-instruct` |

Usługi: mosquitto, bridge, db, ingest, diag, assistant, tokens, grafana. `tokens` wymaga zmiennej `BROKER_SECRET`
(ustawionej `setx` w etapie 6); bez niej nie wstanie – reszta działa.

## 2. Sterownik

| Krok | Komenda / czynność | Sprawdzenie |
|---|---|---|
| Zasilanie | włącz sterownik z aplikacją LineSight | po ok. 1 min odpowiada na ping |
| Aplikacja | jeśli brak: CODESYS → projekt LineSight → Login → download → Start → Create boot application | – |
| Serwer OPC UA | `python tools\opcua_browse.py` (dla .90: `--url opc.tcp://192.168.0.90:4840`) | ≥ 15 zmiennych `GVL_Line` |
| Most | `docker logs linesight-bridge --tail 3` | `subskrypcja 15 z 15 zmiennych`, bez `brak połączenia` |

## 3. Jetson

| Okno | Komenda | Sprawdzenie |
|---|---|---|
| LAPTOP | `ssh grzegorz@192.168.0.124` (otwórz dwa okna: SSH1, SSH2) | prompt `grzegorz@grzegorz-desktop` |
| SSH1 | `sudo nvpmodel -m 0 && sudo jetson_clocks` | po restarcie zegary są dynamiczne; bez tego mniej FPS |
| SSH1 | `cd ~/linesight && git pull` | – |
| SSH1 | `python3 jetson/model_sync.py status` | wdrożona wersja (v1) = wskazana w chmurze; wymaga brokera tokenów |
| SSH2 | `python3 ~/linesight/jetson/serve_clips.py` | serwer klipów na porcie 8080 (zostaje otwarty) |
| SSH1 | `cd ~/linesight && python3 deepstream/linesight_app.py --rtsp --clips --mqtt 192.168.0.203` | ok. 30 FPS w logu |
| LAPTOP | `"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe" --network-caching=50 --rtsp-tcp rtsp://192.168.0.124:8554/linesight` | obraz z ramkami detekcji |

## 4. Grafana i start linii

| Krok | Czynność | Sprawdzenie |
|---|---|---|
| Dashboard | http://localhost:3000 (admin / hasło z `GRAFANA_PASSWORD`, domyślnie `linesight`) | panel „Łącza”: PLC i Kamera `online` |
| Start PackML | CODESYS (online, `GVL_Line`): `xCmdReset` TRUE → FALSE, potem `xCmdStart` TRUE → FALSE (komendy na zbocze) | `iStateCurrent` = 6 (Execute); w Grafanie ok. 40 szt./min z PLC |
| Kamera | butelki przesuwane przed kamerą | słupki „kamera: bottle” obok słupków PLC |

## 5. Demo: postój → przyczyna → asystent

1. Przewróć butelkę przed kamerą, w ciągu kilku sekund ustaw `xInjJam` = TRUE (zator → Held, kod 101).
2. Po kilku sekundach `xInjJam` = FALSE (linia sama wraca do Execute).
3. Grafana, tabela postojów: nowy wiersz `zator` / `potwierdzona`, link do klipu.
4. Kliknij „Zapytaj” przy postoju → asystent odpowiada z przyczyną, sygnałami sprzed postoju, procedurą i źródłami.
5. Napęd: `xInjWear` = TRUE → po kilku minutach spada kondycja i pojawia się alarm; FALSE = naprawa.

## Wyłączanie

SSH1 i SSH2: Ctrl+C → `sudo shutdown -h now` (Jetson). Laptop: `docker compose -f infra\docker-compose.yml stop`
(dane w bazie zostają w wolumenie `pgdata`), Ctrl+C w oknie OLLAMA. Sterownik: wyłączenie zasilania
(program wraca dzięki boot application).

## Typowe problemy

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| Status PLC co 5 s online/offline | most łączy się ze sterownikiem bez aplikacji | `opcua_browse.py`; właściwy `OPCUA_URL` albo wgranie aplikacji |
| Kamera `offline` w Grafanie | `linesight_app.py` bez `--mqtt` albo zły adres laptopa | `ipconfig` na laptopie, poprawny adres w `--mqtt` |
| Mniej niż 30 FPS | zegary Jetsona po restarcie | `sudo nvpmodel -m 0 && sudo jetson_clocks` |
| Link do klipu nie działa | `serve_clips.py` nie działa | uruchomić w SSH2 |
| Asystent: błąd połączenia z LLM | Ollama nie działa | `ollama serve` albo `LLM_BACKEND=gemini` |
| `model_sync.py`: błąd tokenu | usługa `tokens` nie działa | `docker logs linesight-tokens`; `BROKER_SECRET` |
