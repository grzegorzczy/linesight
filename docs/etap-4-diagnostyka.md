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

Wynik: *(uzupełnić po teście)*
