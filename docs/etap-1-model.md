# Etap 1 – model: scena, środowisko, zgodność z TensorRT

Status: w trakcie (od 10.11.2026)

## Cel etapu
Własny detektor butelek (3 klasy) wytrenowany na laptopie, przeniesiony na
Jetsona jako silnik TensorRT i zmierzony w trzech precyzjach (FP32/FP16/INT8).

Wymagania z ogłoszenia: wizja komputerowa na linii pakującej, trening
w PyTorch, optymalizacja modeli pod NVIDIA Jetson (ONNX → TensorRT).

## Mapa: gdzie jesteśmy

Model przechodzi przez dwa urządzenia z różnymi wersjami CUDA. Łączy je
plik ONNX – niezależny od frameworka opis sieci (warstwy + wagi).

```
LAPTOP (Windows)                              JETSON NANO (Ubuntu 18.04)
Python 3.12, PyTorch 2.11 + CUDA 12.8         JetPack 4.6.1: CUDA 10.2, TensorRT 8.2.1
RTX 3050 Ti 4 GB                              GPU Maxwell, 4 GB współdzielone z CPU

  zdjęcia ─► trening (ultralytics) ─► .pt
                                       │
                         eksport ONNX  ▼
                                    model.onnx ──scp──► trtexec / TensorRT
                                                          │ budowa silnika
                                                          ▼ (tylko na Jetsonie)
                                                        model.engine ─► inferencja
```

| Pojęcie | Co to jest | Gdzie |
|---|---|---|
| **CUDA** | Platforma NVIDII do obliczeń na GPU. Wersja zależy od sterownika i biblioteki, która jej używa | Laptop: 12.8 (w kole PyTorch), Jetson: 10.2 (w JetPacku) |
| **PyTorch** | Framework do trenowania sieci. Koło `+cu128` ma w sobie biblioteki CUDA 12.8 – nie instalujemy CUDA osobno | Laptop |
| **ultralytics** | Biblioteka z modelami YOLO: trening, walidacja, eksport jedną komendą | Laptop |
| **ONNX** | Format wymiany modeli. Opset = wersja zestawu operacji; starszy odbiorca rozumie tylko starsze opsety | Plik przenoszony laptop → Jetson |
| **TensorRT** | Optymalizator i silnik inferencji NVIDII. Łączy warstwy, dobiera kernele pod konkretne GPU, obniża precyzję (FP16/INT8) | Jetson: 8.2.1 |
| **Silnik (.engine)** | Wynik budowy TensorRT. Związany z GPU i wersją TensorRT – budujemy go na Jetsonie, nie na laptopie | Jetson |
| **trtexec** | Narzędzie z TensorRT: buduje silnik z ONNX i mierzy jego wydajność | Jetson |

Dlaczego test zgodności (E1-02) przed zbieraniem zdjęć: TensorRT 8.2 pochodzi
z 2021 r. Nowsze architektury YOLO mogą eksportować operacje, których jego
parser ONNX nie zna. Sprawdzamy to na wagach bazowych, zanim w model
zainwestujemy dzień pracy.

## E1-01 – scena

### Zmiana kamery: RealSense → kamera USB ASUS

RealSense (etap 0) miała ręczną ekspozycję, ale scena była pod światło:
ciemna sylwetka butelki na jasnym tle. Druga kamera dała od razu lepszy
obraz, więc zmieniliśmy ją przed zebraniem pierwszego zdjęcia. Zmiana
kamery po zebraniu zbioru oznaczałaby nowy zbiór (inny obraz = inny rozkład
danych).

| Komenda (Jetson) | Do czego służy |
|---|---|
| `v4l2-ctl --list-devices` | Kamera i jej węzeł `/dev/videoN` |
| `v4l2-ctl -d /dev/video0 --list-formats-ext` | Formaty, rozdzielczości, FPS |
| `v4l2-ctl -d /dev/video0 -l` | Ustawienia kamery z zakresami |
| `lsusb` | Urządzenia USB (identyfikator producenta) |

Wynik:

| Format | Rozdzielczości @ 30 FPS |
|---|---|
| YUYV (surowy) | tylko 640x360 |
| MJPG | 1920x1080, 1280x720, 640x360 |
| H.264 (koder w kamerze) | 1920x1080, 1280x720, 640x360 |

Wybór: **YUYV 640x360 @ 30 FPS** – bez dekodowania, ten sam potok co
wcześniej. 360 px w pionie wystarcza: model i tak skaluje wejście do 640
z wypełnieniem (letterbox).

Ustawienia kamery: brightness, contrast, saturation, hue, balans bieli,
`power_line_frequency`, `exposure_absolute` (10–2000). **Brak
`exposure_auto` i `gain`.**

### Pomiar FPS i test ekspozycji

| Komenda | Wynik |
|---|---|
| `v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=360,pixelformat=YUYV --stream-mmap --stream-count=300` przy `exposure_absolute=200` | 25 → 29 fps (rozgrzewanie) |
| to samo przy `exposure_absolute=2000` (teoretycznie 200 ms = 5 FPS) | 30 fps |
| zmiana 10 ↔ 2000 przy podglądzie na żywo | jasność bez zmian |

Wniosek: **kamera ignoruje `exposure_absolute` i ma własną automatyczną
ekspozycję.** Butelka przesuwana w realnym tempie była ostra, więc przy
obecnym świetle kamera dobiera wystarczająco krótki czas. Jedyna dźwignia
przeciw rozmyciu: więcej światła od przodu.

Znane ograniczenie (temat na rozmowę): automatyczna ekspozycja zmienia
jasność, gdy zmienia się zawartość kadru albo światło dzienne. W systemie
produkcyjnym wybralibyśmy kamerę przemysłową z ręczną ekspozycją i stałe
oświetlenie. Tutaj kompensujemy to zróżnicowaniem zbioru (różne pory dnia
w treningu i w zbiorze testowym).

### Podgląd na żywo: Jetson → laptop

Pulpit Jetsona jest wyłączony, więc obraz wysyłamy po sieci. Przy okazji
pierwszy potok ze sprzętowym koderem H.264 (wstęp do E2-05).

```
gst-launch-1.0 -e v4l2src device=/dev/video0 ! \
  video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 ! \
  nvvidconv ! 'video/x-raw(memory:NVMM),format=I420' ! \
  nvv4l2h264enc insert-sps-pps=1 iframeinterval=30 bitrate=4000000 ! \
  h264parse ! rtph264pay config-interval=1 pt=96 ! \
  udpsink host=192.168.0.203 port=5000 sync=false
```

| Element | Rola |
|---|---|
| `v4l2src` | Odczyt z kamery |
| `nvvidconv` | Kopiuje klatkę do pamięci NVMM, z której czyta sprzętowy koder |
| `nvv4l2h264enc` | Sprzętowy koder H.264 (NVENC). `insert-sps-pps=1` + `iframeinterval=30` = klatka kluczowa z nagłówkami co sekundę, więc odbiornik może dołączyć w dowolnym momencie |
| `rtph264pay` + `udpsink` | Pakowanie w RTP i wysyłka UDP na laptop; `sync=false` – bez czekania na zegar |

Odbiór: VLC z plikiem `jetson.sdp` (opis strumienia RTP: port 5000,
H.264, typ ładunku 96). Wynik: obraz z opóźnieniem poniżej ok. 0,5 s;
koder zgłasza `H264: Profile = 66` (Baseline).

Weryfikacja wersji: właściwości `nvv4l2h264enc` sprawdzone na Jetsonie
(`gst-inspect-1.0 nvv4l2h264enc`) – źródło prawdy dla zainstalowanej wersji L4T.

### Ostrość, balans bieli, kadr

| Ustawienie | Wartość | Jak |
|---|---|---|
| Ostrość | ręczna | pierścień na obiektywie, potem zablokowany taśmą |
| Balans bieli | 5500 K, automatyka wyłączona | `v4l2-ctl -d /dev/video0 -c white_balance_temperature_auto=0 -c white_balance_temperature=5500` |
| Ekspozycja | automatyczna (ograniczenie kamery) | – |
| Tło | kaloryfer, okno poza kadrem | ustawienie stanowiska |

Balans bieli blokujemy, bo automatyka zmienia kolory, gdy w kadrze pojawia
się więcej lub mniej butelek – model widziałby tę samą butelkę w różnych
kolorach. Ustawienia `v4l2-ctl` znikają po restarcie lub odłączeniu kamery;
w E1-03 trafią do skryptu zbierania zdjęć.

Kolejne kadry i co poprawialiśmy:
1. Pokój w tle, butelka 1,5 l zajmuje cały kadr → za blisko, tło niejednolite.
2. Dwie butelki, ucięte dno → model musi widzieć cały obiekt.
3. Okno u góry kadru → zaburza automatyczną ekspozycję.
4. **Kaloryfer jako tło, całe butelki, okno poza kadrem → zaakceptowane.**

![Scena E1-01](img/etap1-scena.jpg)

Zasady od teraz: kamery nie ruszamy (pozycja, kąt, ostrość). Butelek nie
stawiamy wyżej ani bliżej niż na zdjęciu. Do obejrzenia po treningu: paski
kaloryfera prześwitują przez przezroczyste butelki.

Zdjęcie sceny (30 klatek, bo automatyczna ekspozycja potrzebuje chwili po
starcie; bierzemy ostatnią):

```
gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=30 ! \
  video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 ! \
  jpegenc ! multifilesink location=scena_%02d.jpg
```

### Problemy po drodze

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| `Device '/dev/video0' is busy` | Osierocony `gst-launch` (PPID 1, brak terminala) – okno zamknięte bez Ctrl+C | `sudo fuser -v /dev/video0`, `ps -fp <PID>`, `kill <PID>` albo `pkill gst-launch` |
| VLC nie otwiera `jetson.sdp` | Plik miał 0 bajtów (Notatnik nie zapisał) | Plik tworzony w cmd blokiem `echo ... > plik` |
| `scp: No such file` | Zdjęcie nie powstało, bo kamera była zajęta | Zwolnić kamerę, `ls -l`, potem `scp` |
| Pobieranie PyTorch przerwane (`Operation cancelled by user`) | Wklejony blok komend – kolejne linie trafiły do działającego `pip` jako klawisze | Długie komendy wklejamy pojedynczo |

## E1-05 – środowisko treningowe (laptop)

Zrobione przed E1-02, bo eksport ONNX wymaga ultralytics.

| Komenda (laptop, cmd) | Do czego służy |
|---|---|
| `python --version` | 3.12.4 – wspierany przez PyTorch i ultralytics |
| `nvidia-smi` | Karta, sterownik 595.95, najwyższa obsługiwana CUDA: 13.2 |
| `python -m venv .venv` | Osobne środowisko Pythona w folderze projektu (`.venv/` w `.gitignore`) |
| `.venv\Scripts\activate` | Włącza środowisko (prefiks `(.venv)`); w każdym nowym oknie od nowa |
| `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128` | PyTorch z CUDA 12.8 (ok. 2,8 GB). Sterownik 595 obsługuje CUDA do 13.2, więc koło cu128 działa |
| `pip install ultralytics onnx` | YOLO + biblioteka ONNX do eksportu |
| `python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"` | Czy PyTorch widzi GPU |
| `yolo checks` | Pełny raport środowiska ultralytics |
| `pip list \| findstr /i "torch ultralytics onnx"` | Wersje do `requirements.txt` |

Kolejność ma znaczenie: PyTorch przed ultralytics. W odwrotnej pip dociągnie
PyTorch z PyPI, czyli wersję bez CUDA dla Windows.

Wynik `yolo checks`:

| Co | Wartość |
|---|---|
| Ultralytics | 8.4.208 |
| PyTorch | 2.11.0+cu128 |
| CUDA (w PyTorch) | 12.8 |
| GPU | NVIDIA GeForce RTX 3050 Ti Laptop GPU, 4096 MiB |
| CPU / RAM | i5-12500H, 16 wątków / 15,7 GB |
| Dysk | ok. 17 GB wolne – nie trzymamy kopii zbioru ani starych `runs/` |

Wersje przypięte w [`training/requirements.txt`](../training/requirements.txt).
Odtworzenie środowiska: `pip install -r training/requirements.txt` w nowym
`.venv`. Plik zawiera tylko pakiety instalowane ręcznie – pełny
`pip freeze` (ok. 40 pozycji) byłby nieczytelny i zależny od Windows.

## E1-02 – zgodność architektur z TensorRT 8.2 (w toku)

Następny krok: eksport YOLOv8n, YOLO11n i YOLO26n do ONNX na laptopie,
budowa silnika FP16 przez `trtexec` na Jetsonie, tabela wyników.

## Do zrobienia w etapie 1
- [x] E1-01 – scena
- [ ] E1-02 – zgodność z TensorRT 8.2
- [ ] E1-03 – skrypt zbierania zdjęć
- [ ] E1-04 – etykietowanie
- [x] E1-05 – środowisko treningowe
- [ ] E1-06 – trening
- [ ] E1-07 – eksport i silniki
- [ ] E1-08 – benchmark
- [ ] E1-09 – dokumentacja i pytania
