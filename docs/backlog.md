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
- [ ] **E1-08 – benchmark** · Jetson · 0,5 dnia · tabela FP32/FP16/INT8: FPS, opóźnienie,
      mAP na Jetsonie, zużycie pamięci (`tegrastats`); wyjaśnienie wyników, także gdy INT8 nic nie daje
- [ ] **E1-09 – dokumentacja i pytania** · · 1-2 h · `docs/etap-1-model.md`, README, 5 pytań technicznych

## Etap 2 – wideo (szac. 3 dni)
- [ ] **E2-01 – instalacja DeepStream 6.0** · Jetson · 1-2 h · przykładowa aplikacja działa;
      kontrola miejsca na karcie przed i po
- [ ] **E2-02 – kamera USB w DeepStream** · Jetson · 2 h · obraz z `/dev/video0` przechodzi przez
      potok z ustawioną ekspozycją (`extra-controls`)
- [ ] **E2-03 ⚠ – nasz model w `nvinfer`** · Jetson · 0,5-1 dnia · parser wyjścia YOLO dla
      DeepStream 6.0; detekcje zgodne z wynikami z etapu 1
- [ ] **E2-04 – tracking i zliczanie** · Jetson · 0,5 dnia · tracker nadaje stałe ID; licznik
      sztuk po przekroczeniu linii; błąd zliczania zmierzony na nagranym teście
- [ ] **E2-05 – RTSP H.264** · Jetson → laptop · 2-3 h · strumień z ramkami detekcji
      ze sprzętowego kodera, odbiór w VLC na laptopie; zmierzone opóźnienie
- [ ] **E2-06 ⚠ – bufor kołowy i klipy** · Jetson · 0,5-1 dnia · zdarzenie zapisuje klip
      N s przed i M s po; klip odtwarza się na laptopie
- [ ] **E2-07 – wysyłka zdarzeń** · Jetson → laptop · 2-3 h · zdarzenie (JSON: czas UTC, typ,
      klasa, ID obiektu, nazwa klipu) trafia do brokera MQTT; wymaga E3-01
- [ ] **E2-08 – dokumentacja i pytania** · · 1-2 h · `docs/etap-2-wideo.md`, README, 5 pytań

## Etap 3 – PLC i dane (szac. 2-3 dni)
- [ ] **E3-01 – infrastruktura** · laptop, Docker · 2-3 h · `infra/docker-compose.yml`:
      Mosquitto, TimescaleDB, Grafana; wszystko wstaje jedną komendą
- [ ] **E3-02 – synchronizacja czasu** · Jetson + laptop · 1 h · NTP na obu urządzeniach,
      wszystkie znaczniki czasu w UTC; zmierzona różnica zegarów
- [ ] **E3-03 – maszyna stanów PackML** · CODESYS · 0,5-1 dnia · podzbiór stanów PackML,
      liczniki sztuk, kody błędów, ręczne wstrzykiwanie awarii (wizualizacja)
- [ ] **E3-04 – serwer OPC UA** · CODESYS · 1 h · zmienne wystawione przez konfigurację symboli
- [ ] **E3-05 – most OPC UA → MQTT** · laptop, Docker · 0,5 dnia · klient OPC UA w Pythonie
      (subskrypcja zmian) publikuje do MQTT; obsługa zerwania połączenia
- [ ] **E3-06 – zapis do TimescaleDB** · laptop, Docker · 0,5 dnia · hypertabele dla sygnałów
      i zdarzeń; zapytanie „sygnały z 30 s przed zdarzeniem” działa
- [ ] **E3-07 – Grafana** · laptop · 2-3 h · oś czasu stanów, liczniki, detekcje z kamery
- [ ] **E3-08 – Factory I/O jako źródło sygnałów** *(opcjonalne)* · laptop · · tylko jeśli
      zostanie czas
- [ ] **E3-09 – dokumentacja, pytania, demo MVP** · · 2-3 h · `docs/etap-3-plc-dane.md`,
      README, krótkie nagranie działającego MVP

## Decyzje
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
