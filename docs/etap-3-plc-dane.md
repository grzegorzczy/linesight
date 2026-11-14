# Etap 3 – PLC i dane: PackML, OPC UA, MQTT, TimescaleDB, Grafana

Status: zakończony 14.11.2026 (E3-01…E3-07, E2-07). E3-08 (Factory I/O) pominięte – symulacja w CODESYS
daje wszystkie sygnały potrzebne w etapie 4. Do zrobienia w E3-09: nagranie demo MVP.

## Cel etapu
Drugie źródło danych obok kamery: sygnały maszyny (stan, przyczyna postoju, licznik, czas cyklu) ze sterownika,
oba strumienie w jednej bazie szeregów czasowych na wspólnej osi czasu i jeden ekran, który pokazuje,
co działo się na linii.

Wymagania z ogłoszenia: potoki danych z PLC i kamer, PostgreSQL/TimescaleDB, PLC/OPC UA/MQTT, definiowanie stanów
i zdarzeń maszyn (procesor telemetrii), Linux/Docker/Git.

## Architektura

```
Jetson (kamera, DeepStream)                       sterownik JUMO variTRON 300 (CODESYS)
  zdarzenie przecięcia linii (JSON)                 PackML: stan, przyczyna, licznik, czas cyklu
        │ MQTT, QoS 1                                       │ serwer OPC UA (opc.tcp://…:4840)
        │ linesight/vision/events                           ▼
        │                                         bridge (asyncua): subskrypcja zmian co 200 ms
        │                                                   │ MQTT, QoS 1, retained
        ▼                                                   ▼ linesight/plc/<zmienna>
  ┌──────────────────────── Mosquitto (broker, laptop) ────────────────────────┐
  └────────────────────────────────────┬───────────────────────────────────────┘
                                       ▼
                     ingest: MQTT → SQL (sesja trwała, zapis przed potwierdzeniem)
                                       ▼
                     TimescaleDB: plc_signal, vision_event, link_status, signals_before()
                                       ▼
                     Grafana (grafana_ro, tylko odczyt): dashboard „LineSight – linia”
```

Laptop: wszystkie usługi w jednym `infra/docker-compose.yml` (`mosquitto`, `bridge`, `db`, `ingest`, `grafana`).

| Pojęcie | Co to jest |
|---|---|
| **MQTT** | Protokół publikuj/subskrybuj. Nadawcy i odbiorcy znają tylko broker i nazwę tematu, nie siebie nawzajem |
| **Broker** | Serwer MQTT (Mosquitto). Przekazuje wiadomości, nie jest bazą danych |
| **QoS 1** | „Co najmniej raz”: broker potwierdza odbiór (PUBACK); możliwy duplikat, nie ma zgubienia |
| **Retained** | Broker pamięta ostatnią wiadomość tematu i oddaje ją każdemu nowemu subskrybentowi |
| **Last Will** | Wiadomość, którą broker wyśle za klienta, gdy ten zniknie bez pożegnania (status `offline`) |
| **PackML** | Standard stanów maszyn pakujących (ISA-TR88.00.02): Execute, Held, Suspended, Aborted… i PackTagi |
| **OPC UA** | Przemysłowy protokół klient–serwer z modelem danych; tu: serwer w sterowniku, zmienne z GVL |
| **Subskrypcja OPC UA** | Serwer sam zgłasza zmianę wartości (sampling 200 ms) – zamiast odpytywania w pętli |
| **Hypertabela** | Tabela TimescaleDB dzielona automatycznie na kawałki (chunki) według czasu |
| **Provisioning** | Konfiguracja Grafany (źródło danych, dashboard) z plików w repo, nie klikana w UI |

---

## E3-01 – broker MQTT (laptop)

`infra/docker-compose.yml` + `infra/mosquitto/mosquitto.conf`: `listener 1883 0.0.0.0` (Mosquitto 2.x bez
konfiguracji słucha tylko na localhost), `allow_anonymous true` (sieć domowa; w zakładzie hasła i TLS na 8883),
`persistence false` (trwałość daje baza).

```
docker pull mirror.gcr.io/library/eclipse-mosquitto:2.0
docker tag mirror.gcr.io/library/eclipse-mosquitto:2.0 eclipse-mosquitto:2.0
docker compose -f infra/docker-compose.yml up -d
docker logs linesight-mosquitto
# Jetson
nc -zv 192.168.0.203 1883
```

Wynik: Mosquitto 2.0.22, Jetson łączy się z portem 1883.
Pobieranie z Docker Hub kończyło się `EOF` (zerwane połączenie z CloudFront, także z public.ecr.aws) –
obrazy pobieramy z kopii Google `mirror.gcr.io` i nadajemy nazwę oczekiwaną przez compose (`docker tag`).

## E2-07 – zdarzenia z Jetsona do MQTT

`deepstream/linesight_app.py --mqtt <host>`, klasa `MqttPublisher`:
- `paho-mqtt==1.6.1` (wersja 2.x wymaga Pythona ≥ 3.7, Jetson ma 3.6),
- `connect_async` + `loop_start`: sieć w wątku w tle, potok wideo nie czeka; zdarzenia bez połączenia czekają w kolejce,
- temat `linesight/vision/events` (QoS 1), `linesight/vision/status` online/offline (retained + Last Will),
- nowe pole `t_cross` – chwila przecięcia linii (pole `t` to ustalenie klasy, 5 s później).

```
pip3 install --user paho-mqtt==1.6.1
python3 linesight_app.py --rtsp --clips --mqtt 192.168.0.203
```

Wynik: zdarzenia `bottle` i `missing_cap` (z polem `clip`) w MQTT Explorer, `t − t_cross` = 5,0 s,
klip z 9 kawałków, potok 30,0 FPS (MQTT nie kosztuje wydajności).

## E3-02 – zegary

Sygnały PLC znakuje czasem laptop (most w kontenerze), zdarzenia – Jetson. Różnica zegarów przesuwa przyczynę
względem skutku. `tools/clock_offset.py` mierzy offset względem `time.google.com` (SNTP, biblioteka standardowa):
`offset = ((t2 − t1) + (t3 − t4)) / 2`, błąd ≤ połowa opóźnienia sieci.

```
python tools\clock_offset.py                                                   # Windows
docker run --rm -v "%cd%\tools:/t" linesight-bridge python /t/clock_offset.py  # kontener (WSL2)
python3 ~/linesight/tools/clock_offset.py                                      # Jetson
```

| Pomiar | Offset |
|---|---|
| Laptop rano | −384 ms (usługa czasu Windows wyłączona) |
| Laptop po południu | −1042 ms (dryf ok. 100 ms/h, usługa nie korygowała) |
| Laptop po naprawie | +1,8 ms |
| **Kontener Dockera** | **+6,5 ms** |
| Jetson | −1,1 ms |

Naprawa (cmd jako administrator):
```
sc config w32time start= auto
w32tm /config /manualpeerlist:time.google.com /syncfromflags:manual /update
reg add HKLM\SYSTEM\CurrentControlSet\Services\W32Time\Config /v MaxAllowedPhaseOffset /t REG_DWORD /d 1 /f
net stop w32time && net start w32time
w32tm /resync /force
```
`MaxAllowedPhaseOffset` = 1 s: większy błąd jest korygowany skokiem. Domyślnie (komputer poza domeną) 300 s – zegar
był tylko powoli dociągany i nie nadążał za dryfem. Skok cofnął zegar o ok. 1 s – w danych testowych z ok. 17:31
czasy mogą się nakładać (dlatego NTP domyślnie woli dociąganie: czas nie powinien się cofać).

## E3-03 – maszyna stanów PackML (CODESYS, variTRON 300)

Kod: `plc/src/E_PackML.st`, `GVL_Line.st`, `PLC_PRG.st` (wklejany ręcznie do projektu; tylko biblioteka Standard).
Sterownik: JUMO variTRON 300, 192.168.0.244, CODESYS V3.5 SP22 Patch 4, **MainTask 10 ms**.

- 11 stanów z numeracją PackML (Status.StateCurrent), stany przejściowe trwają 1 s.
- Komendy na zbocze (`xCmdReset/Start/Stop/Abort/Clear`), wstrzykiwanie usterek poziomem:
  `xInjJam` → Held/101, `xInjNoProduct` → Suspended/201, `xInjFault` → Aborted/301, `xInjSlow` → cykl +40 %.
  Held = przyczyna w maszynie, Suspended = na zewnątrz (brak materiału) – rozróżnienie z PackML.
- Produkcja: sztuka co ok. 1,5 s ± 100 ms (generator LCG); `udiProdProcessed`, `udiCycleTime_ms`, `rMachSpeed`.

Test (wartości zmieniane online w GVL_Line): 6 → 11/101 → 6 → 5/201 → 6; `xInjSlow`: cykl ~2058 ms; 8 → 9/301; Clear → 2/0.

**Błąd znaleziony dopiero w Grafanie (E3-07):** przy zadaniu 200 ms timer z PT 1,5 s kończył się po 1,6 s, a kasowanie
i ponowny start zabierały 2 kolejne cykle zadania → 2,0 s na sztukę, równo 30 szt./min zamiast 40. `udiCycleTime_ms`
raportował czas **zadany**, więc wykres czasu cyklu pokazywał wartości, których nie było. Wykrył to drugi, niezależny
pomiar tej samej wielkości (przyrosty licznika na minutę). Poprawka: czas cyklu mierzony `TIME()` między sztukami
(postój się nie wlicza), MainTask 10 ms. Wynik: 40/40/39 szt./min, cykl 1,40–1,62 s.
**Dane czasu cyklu sprzed 14.11 ok. 18:08 są niewiarygodne** – w etapie 4 tylko dane po poprawce. Po wgraniu programu
pierwsza wartość `udiCycleTime_ms` to 0 – do odfiltrowania.

## E3-04 – serwer OPC UA

Application → Add Object → Symbol Configuration z „Support OPC UA features”, zaznaczone całe `GVL_Line`.
Sprawdzenie z laptopa: `tools/opcua_browse.py` (asyncua).

```
.venv\Scripts\activate
pip install asyncua
python tools\opcua_browse.py
```

Wynik: `opc.tcp://192.168.0.244:4840`, dostęp anonimowy, 15 zmiennych,
`ns=4;s=|var|JUMO ARM Cortex A7 Linux iMX6ULL ARM32.Application.GVL_Line.<nazwa>` (indeks ns odczytywany po URI
`CODESYSSPV3/3S/IecVarAccess`, bo może się zmienić).

## E3-05 – most OPC UA → MQTT

`bridge/opcua_mqtt_bridge.py` (asyncua + paho-mqtt 2.x), usługa `bridge` w compose:
- subskrypcja 9 zmiennych co 200 ms → `linesight/plc/<zmienna>`, QoS 1, retained, `{"t", "value", "t_src"}`,
- `t` nadaje most (zegar kontenera); `t_src` ze sterownika tylko do wglądu – zegar PLC różni się o ok. 1,2 s
  i nie jest synchronizowany (dwa zegary do pilnowania zamiast trzech),
- strażnik: odczyt co 5 s; zerwanie → `linesight/plc/status = offline`, ponowna próba co 5 s.

Test: sekwencja 2 → 15 → 4 → 3 → 6 → 11 w historii tematu, wartości zgodne z CODESYS; wyjęty kabel sterownika:
`offline`, po włożeniu `online` po ok. 5 s.

## E3-06 – TimescaleDB i zapis

`infra/db/init.sql` (wykonywany tylko przy pustym wolumenie), obraz `timescale/timescaledb:2.25.2-pg17`.

| Tabela | Zawartość | Partycja |
|---|---|---|
| `plc_signal` | jedna zmiana jednej zmiennej: `time, name, value, t_src` (format wąski) | 1 dzień |
| `vision_event` | przecięcie linii: `time = t_cross`, `t_decided`, `track_id`, `class`, `clip`, `votes`, `raw` | 7 dni |
| `link_status` | online/offline mostu (`plc`) i kamery (`vision`) | 7 dni |

- Format wąski: most wysyła tylko zmiany; nowy sygnał nie zmienia schematu. Brak wiersza = „bez zmian”.
- `UNIQUE (time, name)` + `ON CONFLICT DO NOTHING`: duplikaty QoS 1 i wiadomości retained po ponownym połączeniu.
- `signals_before(t_event, win = 30 s)`: sygnały z okna przed zdarzeniem **plus wartość każdej zmiennej na początku
  okna** – bez tego zmienna, która się w oknie nie zmieniła (np. Execute), by zniknęła.
- `ingest/mqtt_to_db.py`: sesja trwała (`clean_session=False`) – broker przechowuje wiadomości, gdy ingest nie działa;
  potwierdzenie dopiero po zapisie; przy niedostępnej bazie ponawia zapis zamiast gubić dane.

```
docker exec linesight-db psql -U linesight -c "select name, count(*), max(value) from plc_signal group by name order by name;"
docker exec linesight-db psql -U linesight -c "select * from signals_before(now()) where name <> 'udiProdProcessed';"
docker exec linesight-db psql -U linesight -c "select s.* from signals_before((select max(time) from vision_event)) s where name in ('iStateCurrent','iStopReason','xInjJam');"
```

Wynik: okno 30 s zaczęte w trakcie zatoru zwraca 11/101 na początku i powrót do 6/0; zdarzenie `missing_cap`
z Jetsona w `vision_event` z nazwą klipu, a stan linii w chwili przecięcia: Execute, przyczyna 0.
Czasy w bazie w UTC.

## E3-07 – Grafana

`grafana/grafana:13.2.4`, http://localhost:3000. Źródło danych i dashboard z plików (`infra/grafana/`).
Użytkownik bazy `grafana_ro` – tylko SELECT (`infra/db/20-grafana-ro.sql`; Grafana wykonuje SQL z paneli,
nie powinna móc nic usunąć – DELETE sprawdzony, odrzucony).

| Panel | Dane |
|---|---|
| Stan linii (PackML) i przyczyna | oś stanów `iStateCurrent`, `iStopReason` (+1000 w SQL, wspólna tabela mapowań) |
| Łącza | online/offline mostu i kamery – brak danych ≠ postój |
| Sztuki na minutę: PLC i kamera | przyrosty licznika (`lag`, `time_bucket`) i przecięcia wg klasy |
| Czas cyklu | `udiCycleTime_ms` – wejście do wykrywania anomalii (etap 4) |
| Zdarzenia z kamery | tabela z klipami |
| Adnotacje | `missing_cap` / `fallen` jako znaczniki na osi czasu |

```
docker exec -i linesight-db psql -U linesight < infra\db\20-grafana-ro.sql
docker pull mirror.gcr.io/grafana/grafana:13.2.4
docker tag mirror.gcr.io/grafana/grafana:13.2.4 grafana/grafana:13.2.4
docker compose -f infra/docker-compose.yml up -d
```

Wynik: oś stanów Execute / Held „Zator” / Suspended „Brak produktu” / Stopped; zdarzenie z kamery w tabeli i jako
adnotacja; 40/40/39 szt./min po poprawce PLC.

## Pułapki i rozwiązania

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| `docker pull`: `failed to copy … cloudfront … EOF` | sieć zrywa pobieranie z CloudFront | `mirror.gcr.io/…` + `docker tag` |
| Mosquitto: `chown … Read-only file system` | konfiguracja montowana `:ro` | niegroźne |
| w32tm: `Usługa nie została uruchomiona` | usługa czasu wyłączona | `sc config w32time start= auto`, `net start w32time` |
| offset zegara bez zmian po resync | próg skoku 300 s | `MaxAllowedPhaseOffset` = 1 |
| MQTT Explorer: brak stanów 15 i 3 | drzewo pokazuje ostatnią wartość | temat → Value → History |
| Grafana: „< 80” zamiast nazw stanów | mapowania w nadpisaniach pól nie zadziałały, użyte domyślne progi | jedna tabela mapowań w `defaults` |
| Grafana pokazuje stary dashboard po zmianie | otwarta karta trzyma model dashboardu | F5 (odświeżanie co 5 s pobiera tylko dane) |
| 30 szt./min zamiast 40 | kwantyzacja timera do cyklu zadania + cykl na kasowanie | czas mierzony `TIME()`, MainTask 10 ms |

## Decyzje etapu
- **Sterownik: variTRON 300 zamiast CODESYS Control Win** (decyzja Grzegorza) – kod niezależny od urządzenia.
- **Czas nadaje most, nie sterownik** – mniej zegarów do synchronizacji; `t_src` zostaje do wglądu.
- **Format wąski w `plc_signal`** – most wysyła zmiany; schemat nie zależy od listy sygnałów.
- **Kamera i PLC bez automatycznego powiązania** – przyczyna nie może być znana z konstrukcji; spójne scenariusze
  wstrzykujemy ręcznie (np. przewrócona butelka, potem `xInjJam`), także przypadki trudne (zator bez wady, wada bez postoju).
- **Factory I/O (E3-08) pominięte** – nie dodaje sygnałów potrzebnych w etapie 4.
