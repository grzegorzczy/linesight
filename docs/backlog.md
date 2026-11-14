# Backlog MVP (etapy 1-3)

Format zadania: **ID – tytuł** · urządzenie · szacunek · kryterium ukończenia.
Gałąź na zadanie lub grupę zadań: `etap1/dataset`, `etap2/rtsp` itd.
W opisie PR podajemy ID zadań, np. „E1-03, E1-04”.

Ryzyka oznaczone ⚠ – robimy je jak najwcześniej, bo mogą zmienić plan.

Szacunek MVP: 7-10 dni przy pełnym dniu pracy. Gdy poślizg – tniemy
pozycje oznaczone *(opcjonalne)*, nie kryteria w pozostałych.

## Etap 0 – zamknięcie
- [x] **E0-01 – scalenie PR etapu 0** · GitHub · 5 min · `main` zawiera README, docs, backlog

## Etap 1 – model (szac. 3-4 dni)
- [x] **E1-01 – scena** · stanowisko · 0,5 dnia · kamera zamocowana na sztywno, jednolite tło
      bez okna, światło od strony kamery; butelka ostra w ruchu i nieprześwietlona; 30 FPS
      *(zmiana 10.11: kamera RealSense → ASUS; kryterium „ręczna ekspozycja” zastąpione „ostrość
      w ruchu”, bo kamera ASUS ma tylko automatyczną ekspozycję – szczegóły w `etap-1-model.md`)*
- [x] **E1-02 ⚠ – test zgodności architektur z TensorRT 8.2** · laptop + Jetson · 0,5 dnia ·
      dla kandydatów (np. YOLOv8n, YOLO11n, YOLO26n) z wagami bazowymi: eksport ONNX na laptopie,
      `trtexec` na Jetsonie buduje silnik FP16; tabela: działa / nie działa / dlaczego; wybór architektury
      *(10.11: wszystkie trzy PASSED, ok. 20 qps; wybrany **YOLO26n** – `etap-1-model.md`)*
- [x] **E1-03 – skrypt zbierania zdjęć** · Jetson · 0,5 dnia · zapis co N klatek z kamery
      z ustawieniami kamery (balans bieli 5500 K); zdjęcia zróżnicowane (pozycje, liczba butelek, wszystkie 3 klasy)
      *(10.11: `jetson/capture.py`, 5 sesji, 215 zdjęć)*
- [x] **E1-04 – etykietowanie** · Ultralytics Platform · 0,5-1 dnia · min. ok. 150 obiektów
      na klasę według `docs/etykietowanie.md`; podział train/val/test ustalony przed treningiem; eksport na laptopa
      *(11.11: 214 zdjęć, 536 ramek – bottle 300, missing_cap 107, fallen 129; podział 150/43/21)*
- [x] **E1-05 – środowisko treningowe** · laptop · 1-2 h · venv, PyTorch z CUDA widzi RTX 3050 Ti;
      *(zrobione wcześniej, bo E1-02 potrzebuje ultralytics do eksportu ONNX)*
      wersje zapisane w `training/requirements.txt`
- [x] **E1-06 – trening** · laptop · 0,5 dnia · mAP50 i mAP50-95 na zbiorze testowym,
      macierz pomyłek, przykłady błędów; batch dobrany do 4 GB VRAM
      → zrobione: test mAP50 0,987, mAP50-95 0,778; conf 0,48; 1 FP / 0 FN na val; mapy CAM
- [x] **E1-07 – eksport i silniki** · laptop + Jetson · 0,5 dnia · ONNX; silniki FP32, FP16, INT8
      (INT8 z kalibracją na zdjęciach ze zbioru)
      → zrobione: ONNX 640x640 i 384x640, silniki FP32/FP16; INT8 = FP32 na Nano (brak sprzętowego INT8), bez kalibracji
- [x] **E1-08 – benchmark** · Jetson · 0,5 dnia · tabela FP32/FP16/INT8: FPS, opóźnienie,
      mAP na Jetsonie, zużycie pamięci (`tegrastats`); wyjaśnienie wyników, także gdy INT8 nic nie daje
      → stałe zegary, pamięć, profil warstw, mAP silników (TRT = ONNX, FP16 bez straty), test głowicy
      end-to-end (Mod nieobsługiwany w TRT 8.2); workspace 2048: +1,6%
- [x] **E1-09 – dokumentacja i pytania** · · 1-2 h · `docs/etap-1-model.md`, README, 5 pytań technicznych

## Etap 2 – wideo (szac. 3 dni)
- [x] **E2-01 – instalacja DeepStream 6.0.1** (pakiet `deepstream-6.0`, wersja 6.0.1-1 – jedyna zgodna z JetPack 4.6.1) · Jetson · 1-2 h · przykładowa aplikacja działa;
      kontrola miejsca na karcie przed i po
- [x] **E2-02 – kamera USB w DeepStream** · Jetson · 2 h · obraz z `/dev/video0` przechodzi przez
      potok z ustawioną ekspozycją (`extra-controls`)
- [x] **E2-03 ⚠ – nasz model w `nvinfer`** · Jetson · 0,5-1 dnia · parser wyjścia YOLO dla
      DeepStream 6.0; detekcje zgodne z wynikami z etapu 1
      → parser `deepstream/parser` (.so, C++), NMS w nvinfer (IoU 0,7, próg 0,45 z E1-08), 30 FPS przy GPU 80-98%;
      decyzje przy progu identyczne (mierzone @0,48) z TensorRT+Python (val 108/1/2, test 51/1/1, 0 ramek bez pary),
      mAP50-95 val 0,771→0,754, test 0,764→0,760 (preprocessing: dekodowanie, NV12, kolor pasów)
- [x] **E2-04 – tracking i zliczanie** · Jetson · 0,5 dnia · tracker nadaje stałe ID; licznik
      sztuk po przekroczeniu linii; błąd zliczania zmierzony na nagranym teście
      → `deepstream/linesight_app.py`: nvtracker IOU (`checkClassMatch: 1`), przejścia w kierunku taśmy,
      histereza ±20 px, klasa z głosowania 5 s po linii; 7 testów logiki (`test_counter.py`); 33 FPS z pliku.
      Test ręczny L->R (prawda 3/2/2 bottle/missing_cap/fallen): **3/2/1** (wariant `checkClassMatch: 0`: 3/1/4).
      Ograniczenia testu: butelki przesuwane ręką, okno w kadrze (scena niezgodna z kryterium E1-01),
      prawda z pamięci + przegląd nagrania
- [x] **E2-05 – RTSP H.264** · Jetson → laptop · 2-3 h · strumień z ramkami detekcji
      ze sprzętowego kodera, odbiór w VLC na laptopie; zmierzone opóźnienie
      → `linesight_app.py --rtsp`: NVENC + `tee`, GstRtspServer `rtsp://192.168.0.124:8554/linesight`;
      30 FPS, +40 MB RAM. Opóźnienie od szkła do szkła ~620 ms (VLC, caching 50 ms), z czego potok
      na Jetsonie 73 ms (tracer `latency`) – resztę dokłada głównie klient VLC
- [x] **E2-06 ⚠ – bufor kołowy i klipy** · Jetson · 0,5-1 dnia · zdarzenie zapisuje klip
      N s przed i M s po; klip odtwarza się na laptopie
      → `linesight_app.py --clips`: splitmuxsink 15 × 2 s w `/dev/shm`, klip 10 s przed / 5 s po przecięciu
      (`missing_cap`, `fallen`), `ffmpeg -c copy`; nazwa klipu w zdarzeniu (`clip`). Test: klip 17 s,
      przecięcie w 10. s, 30 FPS
- [x] **E2-07 – wysyłka zdarzeń** · Jetson → laptop · 2-3 h · zdarzenie (JSON: czas UTC, typ,
      klasa, ID obiektu, nazwa klipu) trafia do brokera MQTT; wymaga E3-01
      → **przeniesione do etapu 3** (zaraz po E3-01); zdarzenie ma już pole `clip` (E2-06)
      → 14.11: `linesight_app.py --mqtt <host>`: paho-mqtt 1.6.1, temat `linesight/vision/events` (QoS 1),
      `linesight/vision/status` online/offline (retained + Last Will); nowe pole `t_cross` (chwila przecięcia, UTC)
      Test 14.11 (kamera na żywo, `--rtsp --clips --mqtt`): zdarzenia `bottle` i `missing_cap` (z polem `clip`)
      w MQTT Explorer, t − t_cross = 5,0 s, klip z 9 kawałków, 30,0 FPS
- [x] **E2-08 – dokumentacja i pytania** · · 1-2 h · `docs/etap-2-wideo.md`, README, 5 pytań
      → README (sekcja potoku wideo), ściąga Word (sekcje 10h–10m), pytania z rozmowy w czacie

## Etap 3 – PLC i dane (szac. 2-3 dni)
- [ ] **E3-01 – infrastruktura** · laptop, Docker · 2-3 h · `infra/docker-compose.yml`:
      Mosquitto, TimescaleDB, Grafana; wszystko wstaje jedną komendą
      → 14.11: Mosquitto 2.0 (`infra/mosquitto/mosquitto.conf`: listener LAN, bez haseł – sieć domowa);
      TimescaleDB i Grafana dochodzą do tego samego pliku w E3-06 / E3-07
- [x] **E3-02 – synchronizacja czasu** · Jetson + laptop · 1 h · NTP na obu urządzeniach,
      wszystkie znaczniki czasu w UTC; zmierzona różnica zegarów
      → 14.11: `tools/clock_offset.py` (SNTP). Jetson +13,0 ms, laptop −384,5 ms → różnica 397,5 ms (cel < 100 ms).
      Na laptopie usługa czasu Windows była wyłączona; włączona (`w32time`, start auto), offset po chwili bez zmian.
      Ponowny pomiar 14.11 po południu: laptop −1042 ms (dryf ok. 100 ms/h, usługa nie korygowała). Naprawa:
      `w32tm /config /manualpeerlist:time.google.com /syncfromflags:manual /update` i próg skoku
      `MaxAllowedPhaseOffset` = 1 s (domyślnie 300 s poza domeną → zegar tylko powoli dociągany).
      Wynik: Windows +1,8 ms, **kontener Dockera (WSL2) +6,5 ms**, Jetson −1,1 ms; błąd pomiaru ≤ 20 ms.
      Liczy się zegar kontenera: to nim most znakuje sygnały PLC. Skok zegara cofnął czas o ok. 1 s
      w danych testowych z ok. 17:31
- [x] **E3-03 – maszyna stanów PackML** · CODESYS · 0,5-1 dnia · podzbiór stanów PackML,
      liczniki sztuk, kody błędów, ręczne wstrzykiwanie awarii (wizualizacja)
      → 14.11: kod w `plc/src/` (E_PackML, GVL_Line, PLC_PRG): 11 stanów, zator → Held (101), brak produktu →
      Suspended (201), awaria → Aborted (301), degradacja czasu cyklu.
      Test 14.11 na sterowniku (CODESYS V3.5 SP22 P4, zmiany wartości w GVL_Line online): Execute 6 → Held 11/101 →
      6 → Suspended 5/201 → 6; `xInjSlow`: czas cyklu ~1500 → 2058 ms (37–42 → 29 szt./min); awaria 8 → 9/301;
      Clear → 2/0. Sterowanie z widoku online zamiast wizualizacji (wystarcza; komendy pójdą też przez OPC UA)
- [x] **E3-04 – serwer OPC UA** · CODESYS · 1 h · zmienne wystawione przez konfigurację symboli
      → 14.11: Symbol Configuration z „Support OPC UA features”, całe `GVL_Line`; `tools/opcua_browse.py` z laptopa:
      `opc.tcp://192.168.0.244:4840`, dostęp anonimowy, 15 zmiennych, NodeId
      `ns=4;s=|var|JUMO ARM Cortex A7 Linux iMX6ULL ARM32.Application.GVL_Line.<nazwa>`
- [x] **E3-05 – most OPC UA → MQTT** · laptop, Docker · 0,5 dnia · klient OPC UA w Pythonie
      (subskrypcja zmian) publikuje do MQTT; obsługa zerwania połączenia
      → 14.11: `bridge/opcua_mqtt_bridge.py` + usługa `bridge` w compose: subskrypcja 9 zmiennych co 200 ms,
      tematy `linesight/plc/<zmienna>` (QoS 1, retained, JSON t/value/t_src), `linesight/plc/status`,
      ponowne łączenie co 5 s; czas `t` nadaje most (zegar laptopa)
      Test 14.11: sekwencja stanów 2 → 15 → 4 → 3 → 6 → 11 (historia tematu w MQTT Explorer), wartości zgodne
      z CODESYS; kabel sterownika wyjęty: status offline, po włożeniu online po ok. 5 s.
      Zegar sterownika różni się od laptopa o ok. 1,2 s (`t` − `t_src`) – dlatego czas nadaje most
- [x] **E3-06 – zapis do TimescaleDB** · laptop, Docker · 0,5 dnia · hypertabele dla sygnałów
      i zdarzeń; zapytanie „sygnały z 30 s przed zdarzeniem” działa
      → 14.11: `timescale/timescaledb:2.25.2-pg17`, schemat `infra/db/init.sql` (plc_signal w formacie wąskim,
      vision_event z time = t_cross, link_status), funkcja `signals_before(t, '30 s')`; usługa `ingest`
      (MQTT → baza, sesja trwała, ON CONFLICT DO NOTHING).
      Test 14.11: 9 zmiennych PLC w `plc_signal`; `signals_before(now())` zwraca stan na początku okna (zator 11/101)
      i jego koniec (6/0); zdarzenie `missing_cap` z Jetsona w `vision_event` z klipem, a `signals_before` dla chwili
      przecięcia: Execute 6, przyczyna 0. Obraz bazy pobrany przez mirror.gcr.io
- [x] **E3-07 – Grafana** · laptop · 2-3 h · oś czasu stanów, liczniki, detekcje z kamery
      → 14.11: `grafana/grafana:13.2.4`, źródło danych i dashboard z plików (provisioning), użytkownik bazy
      `grafana_ro` (tylko SELECT). Panele: stan PackML + przyczyna, łącza PLC/kamera, sztuki/min PLC vs kamera,
      czas cyklu, tabela zdarzeń; wady z kamery jako adnotacje na osi czasu
      Test 14.11: Grafana wczytała źródło danych i dashboard. Poprawki: (1) mapowania stanów w nadpisaniach pól
      nie zadziałały (panel pokazywał progi „< 80”) – jedna tabela mapowań, kod przyczyny +1000 w zapytaniu;
      (2) PLC: wykres pokazał 30 szt./min przy zadanym cyklu 1,5 s (40 szt./min). Timer widzi czas tylko co
      cykl zadania (200 ms) i tracił cykl na kasowanie, a udiCycleTime_ms raportował czas ZADANY. Teraz czas
      cyklu jest mierzony (TIME()), a MainTask ma 10 ms. Dane czasu cyklu sprzed poprawki są niewiarygodne.
      Po poprawce: 40/40/39 szt./min, cykl 1,40–1,62 s
- [~] **E3-08 – Factory I/O jako źródło sygnałów** *(opcjonalne, pominięte 14.11: symulacja w CODESYS wystarcza)* · laptop · · tylko jeśli
      zostanie czas
- [x] **E3-09 – dokumentacja, pytania, demo MVP** · · 2-3 h · `docs/etap-3-plc-dane.md`,
      README, krótkie nagranie działającego MVP

## Etap 4 – diagnostyka postojów (szac. 3-4 dni)
Cel: na pytanie „dlaczego linia stanęła” odpowiada zdarzenie postoju z przyczyną, dowodami (sygnały PLC
z 30 s wstecz, zdarzenia z kamery) i linkiem do klipu; osobno model PyTorch wykrywa anomalie czasu cyklu,
zanim linia stanie. Wszystko na laptopie (Docker), Jetson tylko udostępnia klipy.

- [ ] **E4-01 – Mosquitto: kolejka i trwałość** · laptop, Docker · 30 min · `max_queued_messages 100000`
      (domyślnie 1000 na klienta – przy ok. 120 wiadomościach/min ingest wyłączony > 8 min gubił dane),
      `persistence true` z wolumenem `mosquitto-data` (restart brokera kasował kolejki, sesje trwałe i retained).
      Test: ingest zatrzymany 10 min → licznik `udiProdProcessed` w bazie bez dziur; restart brokera przy
      zatrzymanym ingest → po starcie ingest dane z przerwy są w bazie
- [ ] **E4-02 – zdarzenie postoju** · laptop, Docker · 0,5 dnia · nowa usługa `diag` (Python):
      wyjście z `Execute` (Held / Suspended / Aborting / Stopping) = początek postoju, powrót do `Execute`
      = koniec; tabela `stop_event` (początek, koniec, czas trwania, stan, `iStopReason`); logika jako czysta
      funkcja z testami, uruchamiana także wstecz na danych z bazy (odtworzenie postojów z 14.11)
- [ ] **E4-03 – reguły przyczyny** · laptop · 0,5 dnia · przyczyna (zator / brak produktu / awaria /
      zatrzymanie operatora / nieznana) z dowodami: kod PLC, sygnały z `signals_before(t, '30 s')`,
      zdarzenia kamery w oknie; zgodność PLC–kamera (np. „PLC: zator, kamera: przewrócona butelka 4 s
      wcześniej” vs „PLC: zator, kamera nic nie widziała”); test na scenariuszach wstrzykniętych ręcznie,
      także trudnych (zator bez wady, wada bez postoju)
- [ ] **E4-04 – klip przy postoju** · Jetson + laptop · 1-2 h · klip ze zdarzenia kamery w oknie postoju
      dostępny przez HTTP z Jetsona; link w `stop_event`; brak klipu jest informacją, nie błędem
- [ ] **E4-05 – Grafana: postoje** · laptop · 2 h · tabela postojów (czas, trwanie, przyczyna, dowody,
      link do klipu), liczba i łączny czas postojów wg przyczyny
- [ ] **E4-06 – dane czasu cyklu** · CODESYS + laptop · 0,5 dnia · realistyczny czas cyklu w PLC
      (losowy rozrzut, powolny dryf `xInjDrift` obok skoku `xInjSlow`); sesja 1-2 h; zbiór z bazy
      z etykietami z sygnałów `xInj*`; podział train/val/test wg czasu, nie losowo; baseline bez ML
      (próg na średniej kroczącej / z-score) z wynikami
- [ ] **E4-07 – model anomalii w PyTorch** · laptop · 1 dzień · własna pętla treningowa (Dataset,
      DataLoader, optymalizator, walidacja, early stopping, zapis najlepszego modelu); autoenkoder okien
      czasu cyklu uczony tylko na danych normalnych; próg z błędu rekonstrukcji na walidacji; na teście:
      precision / recall zdarzeń, opóźnienie wykrycia, fałszywe alarmy na godzinę – w tabeli obok baseline;
      eksport ONNX
- [ ] **E4-08 – anomalie online** · laptop, Docker · 2-3 h · `diag` liczy wynik modelu (ONNX Runtime,
      bez PyTorcha w kontenerze) po każdym cyklu; tabela `cycle_anomaly`, panel w Grafanie
- [ ] **E4-09 – dokumentacja i pytania** · · 2 h · `docs/etap-4-diagnostyka.md`, README, ściąga,
      5 pytań technicznych

## Poza MVP (pomysły)
- [ ] Demo MVP (14.11, 3:35 min, lokalnie `2026-11-14 18-46-13.mkv`) – do YouTube i README w etapie 7.
- [ ] Test zliczania na „taśmie” (pasek papieru przeciągany spoza kadru), scena zgodna z E1-01
      (bez okna, sztuczne światło), prawda oznaczona na nagraniu – rzetelny błąd zliczania na klasę.
- [ ] Klatki z nagrania E2-04 (światło dzienne, okno w tle, nakrętka pod światło) do retreningu
      w etapie 6: przykład przesunięcia domeny przez oświetlenie (`bottle` → `missing_cap`).
- [ ] Klient RTSP o niskim opóźnieniu (ffplay `nobuffer`/`low_delay` albo GStreamer na laptopie),
      jeśli podgląd ma być < 200 ms (dziś ~620 ms, z czego ~450 ms to VLC) – E2-05
- [ ] Tracker NvDCF zamiast IOU, jeśli po RTSP i klipach zostanie zapas GPU (dziś 80-98%):
      odporniejszy na zasłonięcia ręką i nachodzące na siebie butelki.
- [ ] Głowica end-to-end YOLO26 na TRT 8.2: zamiana `Mod(a, b)` na `a − (a / b)·b` w grafie ONNX
      (onnx-graphsurgeon). Zysk: +0,012 mAP50-95, 2 przeoczenia mniej na val, brak NMS.

## Decyzje
- **PLC: sterownik JUMO variTRON 300 (705003, 192.168.0.244) zamiast programowego CODESYS Control Win**
  *(decyzja Grzegorza 14.11.2026, E3-03)*. Kod ST nie zależy od urządzenia (tylko biblioteka `Standard`),
  więc przeniesienie na Control Win to wklejenie trzech obiektów. Minus: projektu nie da się odtworzyć bez tego sterownika.
- **Zliczanie: tracker IOU z `checkClassMatch: 1`, linia w połowie kadru, kierunek L->R, histereza ±20 px,
  klasa sztuki z głosowania 5 s po przecięciu** *(przyjęte 13.11.2026, E2-04)*. IOU zamiast NvDCF,
  bo GPU jest zajęte w 80-98% przez model; `checkClassMatch: 0` dawał zamianę ID między leżącą
  a stojącą butelką.
- **Wdrażany silnik: 384x640 FP16, workspace 2048, głowica z NMS, conf 0,45** *(przyjęte 13.11.2026, E1-08)*.
  34,4 qps, 20 MiB; mAP jak ONNX FP32. INT8 na Nano = FP32 (brak sprzętowego INT8), głowica
  end-to-end nie przechodzi przez parser TRT 8.2 (operator `Mod`).
- **Architektura: YOLO26n** *(przyjęte 10.11.2026)*. Wszystkie trzy kandydatki działają z TensorRT 8.2
  przy podobnej szybkości (20 qps FP16); YOLO26n ma najwyższą dokładność na COCO i najmniejszy silnik.
  Eksport ONNX zawsze z `opset=13` (limit parsera TensorRT 8.2).
- **Trening detektora: lokalnie, biblioteka `ultralytics`** *(przyjęte 10.11.2026)*. Model detekcji
  trenujemy na laptopie (RTX 3050) przez API Ultralytics – szybciej i mniej ryzyka w MVP.
  Ultralytics Platform służy tylko do etykietowania. Własną pętlę treningową PyTorch piszę
  w etapie 4 dla modelu anomalii czasu cyklu – tam jest mała i w pełni zrozumiała.
- **Backlog w pliku, nie w GitHub Issues:** jedna osoba, jedno źródło prawdy, zero podwójnego
  utrzymania. W firmie byłby Jira lub Issues.
- **Ściąga Word poza repozytorium:** `*.docx` w `.gitignore`. Ściąga jest kopią komend z `docs/*.md`
  do pracy offline; źródłem prawdy są pliki Markdown (diff, przegląd w PR).
