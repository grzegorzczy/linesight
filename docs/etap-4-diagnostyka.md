# Etap 4 – diagnostyka postojów

Cel: na pytanie „dlaczego linia stanęła” odpowiada zdarzenie postoju z przyczyną, dowodami (sygnały PLC
z 30 s wstecz, zdarzenia z kamery) i linkiem do klipu. Osobno model PyTorch (własna pętla treningowa)
wykrywa anomalie czasu cyklu, zanim linia stanie. Plan zadań: `docs/backlog.md`, sekcja „Etap 4”.

## E4-01 – Mosquitto: kolejka i trwałość (laptop)

Luka znaleziona przy pytaniach z etapu 3: ingest ma sesję trwałą, więc broker kolejkuje dla niego
wiadomości QoS 1, gdy ingest nie działa – ale:

| Problem | Przyczyna | Poprawka (`infra/mosquitto/mosquitto.conf`) |
|---|---|---|
| Przerwa ingest > ok. 8 min gubi dane | domyślnie `max_queued_messages 1000` na klienta, most wysyła ok. 120 wiad./min; nadmiar broker po cichu odrzuca | `max_queued_messages 100000` (≈ 14 h) |
| Restart brokera kasuje kolejkę, sesje trwałe i retained | `persistence false` – wszystko w RAM | `persistence true`, `persistence_location /mosquitto/data/`, wolumen `mosquitto-data` |
| Twarde zabicie brokera gubi do 30 min | zapis na dysk przy zatrzymaniu i co `autosave_interval` (domyślnie 1800 s) | `autosave_interval 60` |

Po co diagnostyce: postój bez sygnałów z 30 s wstecz jest nie do wyjaśnienia, a dziura w danych wygląda
jak postój. Wolumen nazwany (`mosquitto-data`) tworzy Docker; katalog `/mosquitto/data` w obrazie należy
do użytkownika `mosquitto`, więc broker ma prawo zapisu.

Uruchomienie (LAPTOP, w folderze repo):
```
git pull
docker compose -f infra/docker-compose.yml up -d mosquitto
docker logs --tail 20 linesight-mosquitto
```
Compose odtwarza tylko kontener `mosquitto` (zmieniona konfiguracja i wolumen). Most i ingest same się
połączą ponownie.

Test 1 – przerwa ingest 10 min (linia w `Execute`, 40 szt./min):
```
docker stop linesight-ingest
:: odczekać 10 min (ok. 1200 wiadomości > dawny limit 1000)
docker start linesight-ingest
docker exec linesight-db psql -U linesight -d linesight -c "SELECT count(*) AS wiersze, max(value)-min(value)+1 AS oczekiwane FROM plc_signal WHERE name='udiProdProcessed' AND time > now() - interval '15 minutes'"
```
`wiersze` = `oczekiwane` → licznik bez dziur (każda sztuka to jedna zmiana licznika).

Test 2 – restart brokera przy zatrzymanym ingest:
```
docker stop linesight-ingest
:: odczekać 2 min
docker restart linesight-mosquitto
docker start linesight-ingest
:: ponownie zapytanie z testu 1, okno '5 minutes'
```

Wynik (14.11, linia cały czas w `Execute`, 40 szt./min):
- Test 2 (restart brokera, ingest zatrzymany 2 min): 595 = 595 – kolejka i sesja trwała przetrwały restart.
- Test 1 (ingest zatrzymany 12 min): w ciągu 30 min `udiProdProcessed` 2038 → 3226, 1189 wierszy = 1189 oczekiwanych.
  Most wysyła 3 zmienne na sztukę (`udiProdProcessed`, `udiCycleTime_ms`, `rMachSpeed`) ≈ 120 wiad./min,
  więc w kolejce było ok. 1400 wiadomości – ponad dawny limit 1000. Bez dziur.
- Pułapka: zapytanie zaraz po `docker start` pokazało 30 = 30 – ingest dopiero oddawał kolejkę (zapis po jednej
  wiadomości). Dane z przerwy docierają z opóźnieniem; diagnostyka postoju (E4-02) musi na nie poczekać,
  zanim policzy okno 30 s.

## E4-02 – zdarzenie postoju (laptop)

Postój = od wyjścia ze stanu `Execute` (6) do powrotu do `Execute`. Cały łańcuch stanów (np. Stopping → Stopped →
Resetting → Idle → Starting) to jeden postój; zapisujemy **pierwszy** stan po Execute, bo on mówi, co zatrzymało linię:

| Pierwszy stan | Znaczenie | `iStopReason` |
|---|---|---|
| 11 Held | zator w maszynie | 101 |
| 5 Suspended | brak produktu na wejściu | 201 |
| 8 Aborting | awaria | 301 / 302 |
| 7 Stopping | zatrzymanie przez operatora | 1 |

Pliki:
- `infra/db/30-diag.sql` – tabela `stop_event` (zwykła, nie hypertabela: kilkadziesiąt wierszy dziennie);
  kolumny `cause`, `evidence`, `clip` wypełnią E4-03 i E4-04.
- `diag/stops.py` – `find_stops()`: czysta funkcja (lista zmian stanu → postoje), bez bazy; `diag/test_stops.py` – 8 testów
  (zator, pełny łańcuch operatora, awaria + drugi postój, powtórzona wartość po ponownym połączeniu mostu, postój trwający,
  start linii poza Execute to nie postój, brak wartości).
- `diag/diag.py` – usługa: co 5 s czyta historię `iStateCurrent` z ostatnich 24 h, wylicza postoje i zapisuje je
  **UPSERT-em** (`INSERT … ON CONFLICT (t_start) DO UPDATE` – wstaw, a gdy wiersz o tym kluczu już jest, zaktualizuj).
  Kod PLC: ostatnia wartość `iStopReason` najpóźniej 1 s po początku postoju.

Dlaczego odpytywanie bazy, a nie reakcja na wiadomość MQTT: dane z przerwy docierają z opóźnieniem (E4-01); każdy przebieg
liczy od nowa i zapisuje idempotentnie, więc spóźnione dane same poprawiają wynik, restart usługi niczego nie gubi ani nie
dubluje, a pierwszy przebieg odtwarza postoje z ostatniej doby. Koszt: opóźnienie do 5 s. Zakres zaczyna się najpóźniej
od początku najstarszego trwającego postoju – postój dłuższy niż 24 h też zostanie zamknięty.

Ograniczenie: gdy most nie ma połączenia z PLC, a linia w tym czasie stanie i ruszy, postoju nie zobaczymy
(most wysyła zmiany, nie historię). Oznaczanie takich luk – E4-03 (`link_status`).

Uruchomienie (LAPTOP):
```
git pull
git checkout etap4/e4-02-stop-event
docker exec -i linesight-db psql -U linesight < infra\db\30-diag.sql
python diag\test_stops.py
docker compose -f infra/docker-compose.yml up -d --build diag
docker logs linesight-diag
docker exec linesight-db psql -U linesight -d linesight -c "SELECT t_start::time, t_end::time, round(extract(epoch FROM t_end - t_start)) AS s, state, stop_reason FROM stop_event ORDER BY t_start"
```
Test na żywo: w CODESYS `xInjJam := TRUE` → w ciągu 5 s w logu `NOWY postój …, stan 11 (Held), kod PLC 101`;
`xInjJam := FALSE` → `ZMIANA postój … – <koniec>`.

Wynik: *(uzupełnić po teście)*
