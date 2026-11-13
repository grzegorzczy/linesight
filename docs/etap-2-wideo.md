# Etap 2 – wideo: DeepStream, tracking, zliczanie

Status: zakończony 13.11.2026 (E2-01…E2-06, E2-08). E2-07 (wysyłka zdarzeń MQTT) przeniesione do etapu 3 – po E3-01 (broker).

## Cel etapu
Potok wideo na Jetsonie bez przechodzenia klatek przez CPU: kamera → GPU → model → tracker →
zliczanie sztuk → strumień RTSP i klipy ze zdarzeń.

Wymagania z ogłoszenia: wideo na NVIDIA Jetson, GStreamer/DeepStream, integracja własnego modelu,
logika aplikacji nad potokiem (liczenie sztuk, zdarzenia na linii).

## Mapa potoku

```
kamera USB (YUY2 640x360@30)
  │ v4l2src
  ▼
nvvideoconvert ──► pamięć NVMM (GPU, bez kopiowania)          blok VIC, nie CPU
  ▼
nvstreammux (batch 1, 640x360) ──► metadane DeepStream (NvDsBatchMeta)
  ▼
nvinfer: letterbox 384x640 + /255 + silnik TensorRT FP16      E2-03
         + nasz parser .so [7, 5040] + NMS (IoU 0,7, conf 0,45)
  ▼
nvtracker: IOU (CPU), stałe ID śladów                          E2-04
  ▼
sonda w Pythonie (pyds): zliczanie na linii, klasa z głosowania, zdarzenia JSON
  ▼
nvdsosd (ramki, linia, liczniki) ─► nvv4l2h264enc (sprzętowy) ─► MP4 / RTSP (E2-05)
```

| Pojęcie | Co to jest |
|---|---|
| **GStreamer** | Biblioteka do budowy potoków multimedialnych z elementów (źródło → filtry → ujście) połączonych `!` |
| **DeepStream** | Zestaw wtyczek GStreamera od NVIDII: inferencja TensorRT, tracking, OSD, wszystko na buforach GPU |
| **NVMM** | Bufory w pamięci GPU/sprzętowej; VIC, GPU i koder czytają je bez kopiowania przez CPU |
| **nvstreammux** | Składa klatki w batch i dołącza metadane DeepStreama – wymagany przed `nvinfer` |
| **nvinfer** | Inferencja TensorRT z preprocessingiem (skalowanie, letterbox, normalizacja) i postprocessingiem (parser, NMS) |
| **parser (custom bbox parser)** | Funkcja w bibliotece `.so`, która zamienia surowy tensor wyjściowy na listę ramek |
| **nvtracker** | Wtyczka trackingu; algorytm w bibliotece `libnvds_nvmultiobjecttracker.so`, parametry w YAML |
| **pyds** | Powiązania DeepStreama z Pythonem: odczyt i zapis metadanych w sondzie (probe) |
| **sonda (pad probe)** | Funkcja wołana dla każdego bufora przechodzącego przez dane miejsce potoku |

---

## E2-01 – instalacja DeepStream 6.0.1 (Jetson)

Dla JetPack 4.6.1 (L4T 32.7.1, TensorRT 8.2.1) właściwa wersja to **DeepStream 6.0.1**
(6.0 jest pod JetPack 4.6 / TensorRT 8.0). Pakiet nazywa się `deepstream-6.0`, katalog
`/opt/nvidia/deepstream/deepstream-6.0`. 6.0.1 to ostatnie wydanie z nowymi funkcjami dla Nano.

```
df -h /                                   # miejsce przed
sudo apt update
apt-cache policy deepstream-6.0           # Candidate: 6.0.1-1 = jest w repozytorium JetPacka
sudo apt install -y libssl1.0.0 libgstreamer1.0-0 gstreamer1.0-tools gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav libgstrtspserver-1.0-0 \
  libjansson4=2.11-1
sudo apt install -y deepstream-6.0
```

Sprawdzenie:
```
dpkg -l deepstream-6.0                    # ii  deepstream-6.0  6.0.1-1
ls /opt/nvidia/deepstream/deepstream-6.0/lib/gst-plugins/
gst-inspect-1.0 nvinfer | head -20        # Version 6.0.1
gst-inspect-1.0 nvtracker | head -5
gst-inspect-1.0 nvv4l2h264enc | head -5   # sprzętowy koder H.264 (z L4T)
df -h /                                   # +ok. 0,9 GB (60% -> 63% karty 29 GB)
```

Świadomie pominięte z quickstartu: `librdkafka` (Kafka – my wysyłamy przez MQTT), podmiana
`libgstvideo` (poprawka dla wielu wejść RTSP – mamy jedną kamerę), SDK Manager i Docker.

Ostrzeżenia `libnvdsgst_udp.so: librivermax` i `libnvdsgst_inferserver.so: libtritonserver`
przy `gst-inspect` są nieszkodliwe – tych wtyczek nie używamy.

## E2-02 – kamera w potoku DeepStream (Jetson)

Przed pomiarami zawsze stałe zegary (po restarcie wracają do trybu dynamicznego):
```
sudo nvpmodel -m 0          # tryb MAXN (10 W, 4 rdzenie)
sudo jetson_clocks          # zegary CPU/GPU/EMC na maksimum; w tegrastats CPU @1479
v4l2-ctl --list-devices     # kamera ASUS = /dev/video0
tegrastats --interval 1000  # SSH2: RAM, CPU na rdzeń, GR3D_FREQ (GPU)
```

Test A – kamera → NVMM; test B – z `nvstreammux` (kształt docelowego potoku):
```
gst-launch-1.0 -v v4l2src device=/dev/video0 ! video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 \
  ! nvvideoconvert ! "video/x-raw(memory:NVMM),format=NV12" \
  ! fpsdisplaysink video-sink=fakesink text-overlay=false sync=false

gst-launch-1.0 -v v4l2src device=/dev/video0 ! video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 \
  ! nvvideoconvert ! "video/x-raw(memory:NVMM),format=NV12" \
  ! m.sink_0 nvstreammux name=m batch-size=1 width=640 height=360 live-source=1 \
  ! fpsdisplaysink video-sink=fakesink text-overlay=false sync=false
```

| | FPS | dropped | RAM | CPU (najbardziej obciążony rdzeń) | GPU |
|---|---|---|---|---|---|
| spoczynek | – | – | 896 MB | ~2% | 0% |
| test A | 30 | 0 | 905 MB | 4-6% | 0% |
| test B | 30 | 0 | 916 MB | 4-6% | 0% |

Wniosek: konwersję YUY2 → NV12 robi blok VIC, nie CPU (`videoconvert` niepotrzebny).
Porównanie: w etapie 1 przygotowanie klatki w Pythonie kosztowało 12-15 ms CPU na klatkę
(36-45% rdzenia przy 30 FPS).

## E2-03 – nasz model w `nvinfer` (Jetson + laptop)

### API sprawdzone w zainstalowanym SDK (nie z pamięci)
```
DS=/opt/nvidia/deepstream/deepstream-6.0
grep -n -A5 "typedef bool (\* NvDsInferParseCustomFunc)" $DS/sources/includes/nvdsinfer_custom_impl.h
grep -n -B14 "} NvDsInferObjectDetectionInfo;" $DS/sources/includes/nvdsinfer.h
grep -rn '"symmetric-padding"\|"maintain-aspect-ratio"\|"nms-iou-threshold"\|"pre-cluster-threshold"\|"cluster-mode"\|"parse-bbox-func-name"' \
  $DS/sources/gst-plugins/gst-nvinfer/
grep -n "offset" $DS/sources/gst-plugins/gst-nvinfer/gstnvinfer_meta_utils.cpp | head
```
Ostatni grep: `obj.top = (obj.top - frame.offset_top) / frame.scale_ratio_y` – nvinfer odejmuje pasy
letterboxa przed przeskalowaniem ramek, więc `symmetric-padding=1` jest poprawne.

### Pliki
| Plik | Rola |
|---|---|
| `deepstream/parser/nvdsparse_yolo26.cpp` | Parser [7, N]: dla każdej kotwicy klasa o najwyższej pewności, odrzucenie poniżej progu, ramki w pikselach wejścia sieci |
| `deepstream/parser/Makefile` | Budowa `libnvdsparse_yolo26.so` (g++, nagłówki DS i CUDA 10.2); `.so` nie trafia do repo |
| `deepstream/configs/nvinfer_yolo26.txt` | Konfiguracja nvinfer: silnik FP16, RGB /255, letterbox symetryczny, parser, NMS (IoU 0,7), próg 0,45 (E1-08) |
| `deepstream/configs/nvinfer_yolo26_eval.txt` | To samo z progiem 0,001 i 300 ramkami – tylko do pomiaru mAP |
| `deepstream/test_nvinfer.sh` | `fps` – pomiar potoku z inferencją; `mp4` – nagranie z ramkami (koder sprzętowy) |
| `jetson/ds_dump.py` | Zdjęcia z folderu przez potok DeepStream → detekcje w JSON (sonda pyds) |
| `training/eval_ds.py` | mAP i zgodność decyzji: DeepStream vs TensorRT z Pythona (te same zdjęcia, ten sam kod metryk) |

### Komendy
```
# Jetson: budowa parsera
cd ~/linesight/deepstream/parser && make
nm -D libnvdsparse_yolo26.so | grep NvDsInferParseYolo26     # T = funkcja eksportowana

# Jetson: płynność i nagranie
cd ~/linesight/deepstream
bash test_nvinfer.sh fps
bash test_nvinfer.sh mp4            # Ctrl+C, czekać na "Zapisano: /tmp/e2-03.mp4"

# Jetson: pyds (Python bindings DS 6.0.1 = tag v1.1.1)
sudo apt install -y python3-gi python3-dev python3-gst-1.0 python3-pip
cd ~ && wget https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/releases/download/v1.1.1/pyds-1.1.1-py3-none-linux_aarch64.whl
pip3 install --user --no-deps ./pyds-1.1.1-py3-none-linux_aarch64.whl
python3 -c "import pyds, gi; gi.require_version('Gst','1.0'); from gi.repository import Gst; Gst.init(None); print('pyds OK', Gst.version_string())"

# Jetson: detekcje DeepStreama na zbiorach z E1-08
cd ~/linesight
python3 jetson/ds_dump.py deepstream/configs/nvinfer_yolo26_eval.txt data/eval/val models/ds_val.json
python3 jetson/ds_dump.py deepstream/configs/nvinfer_yolo26_eval.txt data/eval/test models/ds_test.json

# Laptop
scp grzegorz@192.168.0.124:~/linesight/models/ds_*.json models\
python training\eval_ds.py
```

### Wyniki
| | P | R | mAP50 | mAP50-95 | TP/FP/FN @0,48* |
|---|---|---|---|---|---|
| val: TensorRT + Python | 0,989 | 0,992 | 0,995 | 0,771 | 108/1/2 |
| val: DeepStream | 0,988 | 0,989 | 0,995 | 0,754 | 108/1/2 |
| test: TensorRT + Python | 0,964 | 0,989 | 0,964 | 0,764 | 51/1/1 |
| test: DeepStream | 0,965 | 0,989 | 0,964 | 0,760 | 51/1/1 |

- \* Pomiar wykonany przy 0,48 (pomyłka – próg wdrożeniowy z E1-08 to 0,45; na val oba progi dają
  te same TP/FP/FN). `eval_ds.py` liczy teraz przy 0,45.
- Decyzje przy progu identyczne: wszystkie ramki mają parę (val 109, test 52), maks. różnica ramki ~9 px.
- Spadek mAP50-95 (0,4-1,7 pp) = preprocessing: dekodowanie JPEG w GStreamerze, konwersja przez NV12
  w `nvvideoconvert`, prawdopodobnie czarne zamiast szarych (114) pasów letterboxa. Silnik ten sam.
- Na żywo: 30 FPS, dropped 0, GPU 80-98%, RAM 1830 MB (+0,9 GB: CUDA/cuDNN/TensorRT + silnik).
  Zapas GPU ok. 13% (silnik ~29 ms, klatka co 33 ms).

## E2-04 – tracking i zliczanie (Jetson)

### Pliki
| Plik | Rola |
|---|---|
| `deepstream/linesight_app.py` | Potok: kamera lub MP4 → nvinfer → nvtracker → sonda (zliczanie, OSD) → MP4 / fakesink |
| `deepstream/configs/tracker_iou.yml` | Tracker IOU (CPU), `checkClassMatch: 1` |
| `deepstream/configs/tracker_iou_noclassmatch.yml` | Wariant porównawczy `checkClassMatch: 0` |
| `deepstream/record_raw.sh` | Surowe nagranie z kamery (bez inferencji) + podgląd w VLC na laptopie |
| `deepstream/test_counter.py` | 7 testów logiki licznika bez Jetsona (`python deepstream/test_counter.py`) |

### Logika zliczania
- Przejście = środek ramki śladu przechodzi przez pionową linię (`--line 0.5` szerokości)
  w kierunku taśmy (`--direction L->R`; `both` do testów).
- **Histereza** `--margin 20`: strona linii zmienia się dopiero poza strefą ±20 px
  (bez niej leżąca butelka dawała 2-3 przejścia w 1-12 klatek – drgania środka ramki).
- **Klasa z głosowania** po klatkach śladu, ustalana `--decide 150` klatek (5 s) po przecięciu
  albo przy zniknięciu śladu – ręka na szyjce przy linii dawała chwilowo `missing_cap`.
- Ślad, który wróci na stronę wejściową, może zostać policzony ponownie.
- Zdarzenie JSON (stdout + `/tmp/linesight_events.jsonl`): `frame` przecięcia, `decided_at`,
  `track_id`, `class`, `direction`, `votes` – wejście dla E2-06 (klipy) i E2-07 (MQTT).

### Komendy
```
# Jetson: surowe nagranie testowe (podgląd: VLC na laptopie, plik jetson.sdp, port 5000)
cd ~/linesight/deepstream && bash record_raw.sh /tmp/raw_e204.mp4      # Ctrl+C kończy

# Jetson: zliczanie na nagraniu (powtarzalne, bez kamery)
python3 linesight_app.py --source /tmp/raw_e204.mp4 --out /tmp/e2-04.mp4
# porównanie trackerów
for t in tracker_iou tracker_iou_noclassmatch; do echo "=== $t"; \
  python3 linesight_app.py --source /tmp/raw_e204.mp4 --tracker configs/$t.yml --events "" 2>/dev/null | grep PODSUMOWANIE; done
# na żywo z kamery
python3 linesight_app.py --source /dev/video0

# Laptop: sam podgląd kamery (Jetson wysyła RTP/UDP na 192.168.0.203:5000)
# plik jetson.sdp, jeśli go brak:
(echo v=0& echo o=- 0 0 IN IP4 192.168.0.124& echo s=Jetson& echo c=IN IP4 192.168.0.203& echo t=0 0& echo m=video 5000 RTP/AVP 96& echo a=rtpmap:96 H264/90000) > jetson.sdp
```

### Wyniki (test ręczny, kierunek L->R, prawda 3/2/2 bottle/missing_cap/fallen)
| wariant | bottle | missing_cap | fallen | suma błędów |
|---|---|---|---|---|
| pierwsza wersja (ślad liczony raz, klasa przy linii) | 2 | 3 | 2 | – (7 = przypadek, 13 przejść w obu kierunkach) |
| klasa 1 s po linii | 1 | 3 | 5 | 6 |
| klasa 5 s po linii | 3 | 1 | 5 | 4 |
| + histereza ±20 px, `checkClassMatch: 0` | 3 | 1 | 4 | 3 |
| **+ histereza, `checkClassMatch: 1` (wybrany)** | **3** | **2** | **1** | **1** |

- 33 FPS przy przetwarzaniu pliku (detekcja + tracker + sonda + OSD + koder).
- Test liczony przy progu 0,48 (przed poprawką na 0,45 z E1-08).
- `checkClassMatch: 0` pozwalał śladowi leżącej butelki przeskoczyć na stojącą obok (zamiana ID);
  przy `1` zmiana klasy dzieli ślad (17 śladów zamiast 9), ale krótkie części nie przechodzą przez linię.
- Ograniczenia testu: butelki przesuwane ręką, okno w kadrze (niezgodne z kryterium sceny z E1-01),
  prawda z pamięci + przegląd nagrania. Przesunięcie domeny przez światło dzienne: różowa nakrętka
  na tle okna znika → `bottle` mylony z `missing_cap`. Dalsze testy w backlogu (poza MVP).

## E2-05 – strumień RTSP H.264 (Jetson → laptop)

### Pliki
| Plik | Co robi |
|---|---|
| `deepstream/linesight_app.py` | `--rtsp` (+ `--rtsp-port 8554`, `--rtsp-mount /linesight`, `--bitrate 4000000`) |
| `laptop/stoper.py` | Stoper z ms (tkinter) do pomiaru opóźnienia od szkła do szkła |

### Jak to działa
```
nvdsosd ─► nvvideoconvert (I420) ─► nvv4l2h264enc (NVENC) ─► h264parse ─► tee ─┬─► qtmux ─► MP4 (--out)
                                                                                 └─► rtph264pay ─► udpsink 127.0.0.1:5400
GstRtspServer (ten sam proces, port 8554, /linesight): udpsrc :5400 ─► klienci RTSP (set_shared: jeden strumień dla wszystkich)
```
- Jeden koder sprzętowy, `tee` za koderem – RTSP i MP4 bez podwójnego kodowania (to samo `tee` wykorzysta E2-06).
- `insert-sps-pps=1 iframeinterval=30`: klatka I + nagłówki co 1 s – klient dołącza w każdej chwili,
  po zgubionym pakiecie obraz wraca najpóźniej po 1 s.
- `udpsink sync=false` dla kamery (klatka wychodzi od razu), `sync=true` dla pliku (tempo 30 FPS).
- Układ z przykładu NVIDIA `deepstream-test1-rtsp-out` (deepstream_python_apps v1.1.1 = DS 6.0.1).
- Ostrzeżenie `GstUDPSrc has no property named 'pt'` – nieszkodliwe: serwer próbuje ustawić typ ładunku
  na `pay0`, a u nas `pay0` to `udpsrc` z gotowymi pakietami RTP (`pt=96`).

### Komendy
```
# Jetson (jednorazowo): typelib GstRtspServer dla Pythona (biblioteka libgstrtspserver jest od E2-01)
sudo apt-get install -y gir1.2-gst-rtsp-server-1.0

# Jetson: kamera -> RTSP
cd ~/linesight/deepstream && python3 linesight_app.py --rtsp

# Laptop (cmd): odbiór; VLC jest 32-bitowy -> Program Files (x86)
"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe" --network-caching=50 --rtsp-tcp rtsp://192.168.0.124:8554/linesight

# Laptop: stoper do pomiaru opóźnienia
python laptop\stoper.py

# Jetson: opóźnienie samego potoku (tracer GStreamera, v4l2src -> udpsink)
GST_TRACERS=latency GST_DEBUG=GST_TRACER:7 GST_DEBUG_FILE=/tmp/latency.log python3 linesight_app.py --rtsp
grep -o 'time=(guint64)[0-9]*' /tmp/latency.log | cut -d')' -f2 | sort -n | \
  awk '{a[NR]=$1} END {print "n=" NR, "mediana=" a[int(NR/2)]/1e6 " ms", "min=" a[1]/1e6, "max=" a[NR]/1e6}'
```
`--network-caching` – bufor sieciowy VLC (domyślnie 1000 ms). `--rtsp-tcp` – RTP w połączeniu TCP z RTSP
(omija blokadę przychodzącego UDP przez zaporę Windows).

### Wyniki
| Pomiar | Wynik |
|---|---|
| FPS z RTSP (kamera, 3844 klatki) | **30,0** (jak bez RTSP) |
| RAM / GPU (GR3D) / CPU (tegrastats) | 1873 MB (+~40 MB względem E2-04) / 61-99 % / 20-30 % na rdzeń |
| Opóźnienie od szkła do szkła, VLC `network-caching=200` | 610-960 ms (2 odczyty) |
| **Opóźnienie od szkła do szkła, VLC `network-caching=50`** | **mediana ~620 ms** (522 / 614 / 622 / 636 ms + 2 odczyty z obrazu w obrazie: 604, 625) |
| **Potok na Jetsonie (tracer `latency`, v4l2src → udpsink)** | **mediana 73 ms** (n = 657; max 1,7 s = pierwsze klatki przy starcie) |

Rozkład opóźnienia (~620 ms):
- **potok na Jetsonie ~73 ms** – zmierzone (mux, nvinfer, tracker, sonda, OSD, NVENC, pakowanie RTP);
- kamera USB (naświetlanie + bufory UVC/v4l2, 1-3 klatki po ~33 ms) i sieć LAN – razem szacunkowo ~50-100 ms;
- **reszta, ~450 ms – odbiornik (VLC)**: bufor na jitter i zegar odtwarzania, dekodowanie, wyświetlanie.
  Zmniejszenie `network-caching` z 200 do 50 ms prawie nic nie dało, więc to nie jest sam bufor sieciowy.

Wnioski:
- NVENC to osobny blok sprzętowy – RTSP nie zmniejszył FPS ani nie zabrał GPU detekcji.
- Wąskim gardłem opóźnienia jest klient, nie Jetson. Do podglądu dla operatora 0,6 s wystarcza;
  diagnoza postojów korzysta z klipów (E2-06) i zdarzeń, które powstają na Jetsonie przed koderem.
- Gdyby było trzeba poniżej ~200 ms: klient o niskim opóźnieniu (np. `ffplay -fflags nobuffer -flags low_delay`
  albo GStreamer na laptopie) – w backlogu, poza MVP.
- Dokładność pomiaru stoperem: ±1 odświeżenie ekranu (~16 ms) i ±1 klatka kamery (~33 ms).
- Tracer obniża FPS (28,1 zamiast 30) – pomiar opóźnienia osobno od pomiaru FPS.

## E2-06 – bufor kołowy i klipy ze zdarzeń (Jetson)

### Pliki
| Plik | Co robi |
|---|---|
| `deepstream/linesight_app.py` | `--clips` (+ `--clips-dir ~/linesight_clips`, `--clip-classes missing_cap,fallen`, `--pre 10`, `--post 5`); `select_segments`, `ClipMaker` |
| `deepstream/test_counter.py` | +2 testy: wybór kawałków bufora, nazwa klipu w zdarzeniu (razem 9) |

### Jak to działa
```
... nvv4l2h264enc ─► h264parse ─► tee ─┬─► MP4 (--out)
                                        ├─► RTP ─► RTSP (--rtsp)
                                        └─► splitmuxsink: /dev/shm/linesight/seg00000..00014.mp4 (--clips)
zdarzenie (missing_cap/fallen) ─► czekaj post + 3 s ─► wybierz kawałki z [przecięcie-10 s, przecięcie+5 s]
                               ─► ffmpeg -f concat -c copy ─► ~/linesight_clips/<data>_<klasa>_id<N>.mp4
```
- **Bufor kołowy = `splitmuxsink` z `max-files=15`**: kawałki ~2 s, nazwy krążą, najstarszy nadpisywany → 30 s historii.
- **`/dev/shm` (tmpfs w RAM, 2 GB)**: ciągły zapis nie zużywa karty SD; bufor zajmuje ~15 MB.
- **`max-size-time` 2,5 s, nie 2 s**: przy klatce I co 1 s i limicie dokładnie 2 s część kawałków zamykała się po 1 s
  (pliki na zmianę ~0,5 i ~1 MB) – 15 plików dawało ~22 s historii. Przy 2,5 s mieszczą się zawsze 2 GOP-y.
- **Klip centrowany na przecięciu linii**, nie na chwili zdarzenia (klasa ustalana 5 s później):
  `t_przecięcia = t_zdarzenia − (decided_at − frame) / 30`.
- **Wybór kawałków po czasie modyfikacji pliku**: `mp4mux` dopisuje nagłówek przy zamknięciu, więc mtime ≈ koniec
  kawałka; najnowszy plik (wciąż zapisywany, bez `moov`) jest pomijany. Logika w `select_segments` – testowana bez Jetsona.
- **Sklejanie `ffmpeg -c copy`** (concat demuxer): bez dekodowania i kodowania, ułamek sekundy, prawie 0 CPU.
  Każdy kawałek zaczyna się od klatki I, więc klip odtwarza się od pierwszej klatki.
- **Zdarzenie dostaje pole `clip`** (nazwa pliku) – wejście dla E2-07 (MQTT) i asystenta (etap 5).
- Klip ma dokładność ±1 kawałek (2 s) – granice na klatkach I. Klipy nieukończone przy Ctrl+C program wypisuje.
- Z pliku MP4 (`--source plik.mp4`) czasy są przybliżone (wybór po zegarze ściennym) – klipy mają sens na żywo.

### Odrzucone
- **Smart Record DeepStreama (NvDsSR)** – w DS 6.0 tylko API w C, brak w pyds 1.1.1.
- **Bufor klatek w Pythonie (deque + appsrc)** – więcej kodu i CPU, ta sama funkcja.

### Komendy
```
# Jetson: sprawdzenie narzędzi (jednorazowo)
gst-inspect-1.0 --version                     # 1.14.5
gst-inspect-1.0 splitmuxsink | grep -E "max-size-time|max-files|muxer|location"
which ffmpeg; ffmpeg -version | head -1       # 3.4.8 (jest w systemie)
df -h /dev/shm                                # tmpfs 2,0 G

# Jetson: kamera + RTSP + klipy (test: klip dla każdej klasy)
cd ~/linesight/deepstream
python3 linesight_app.py --rtsp --clips --clip-classes bottle,missing_cap,fallen
# drugie okno: podgląd bufora co 1 s
watch -n 1 ls -l --time-style=+%T /dev/shm/linesight
# długość klipu
ffprobe -v error -show_entries format=duration -of csv=p=0 ~/linesight_clips/<klip>.mp4

# Laptop (cmd): pobranie klipów
scp grzegorz@192.168.0.124:~/linesight_clips/*.mp4 .
```
`watch -n 1` – powtarza komendę co 1 s. `ffprobe` – odczyt parametrów pliku (część ffmpeg). `scp` – kopiowanie przez SSH.

### Wyniki
| Pomiar | Wynik |
|---|---|
| FPS (kamera + RTSP + bufor) | **30,0** |
| Kawałki bufora po poprawce | ~1 MB, co 2 s (0,77 MB przy małym ruchu – H.264 kompresuje lepiej) |
| Klip `20261113-221731_bottle_id0.mp4` | 9 kawałków, **17 s**, przecięcie linii w **10. s** (oczekiwane 10 ± 2 s) |
| Odtwarzanie | od pierwszej klatki, bez szarego obrazu i zacięć na sklejeniach |

---

## Pułapki i rozwiązania
| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| `apt install` kończy się „Abort.” | Kilka komend wklejonych naraz – następna linia wzięta za odpowiedź na `[Y/n]` | `apt install -y`, komendy wklejane pojedynczo |
| `No such element or plugin 'nvinfer'` | DeepStream nie zainstalowany (patrz wyżej) | Powtórzyć instalację, sprawdzić `dpkg -l deepstream-6.0` |
| `pip3 install pyds…whl` buduje PyGObject/pycairo i pada | Koło deklaruje zależności PyGObject i pgi; pip próbuje kompilować ze źródeł | `--no-deps`; PyGObject z apt (`python3-gi`). Biblioteki z kodem C na Jetsonie bierzemy z apt |
| `index.lock: File exists` w gicie na laptopie | Polecenia git uruchomione równolegle z innego środowiska na tym samym folderze | `del .git\index.lock`; operacje git z jednego miejsca |
| `moov atom not found` przy odtwarzaniu MP4 | Plik skopiowany (`scp`), zanim aplikacja domknęła MP4 (`106%` w scp) | Kopiować po `PODSUMOWANIE` / `Zapisano` |
| Brak podglądu w trybie `mp4` | Potok zapisuje do pliku, SSH nie ma ekranu | Podgląd przez RTP/UDP → VLC (`record_raw.sh`), w E2-05 RTSP |
| `sudo` zjada kolejne wklejone linie („Sorry, try again”) | Linie po `sudo` wzięte jako hasło | `sudo …` wklejać osobno, resztę po podaniu hasła |
| `pathspec 'etap2/…' did not match` przy `git checkout` | Jetson nie wie o nowej gałęzi z GitHuba | Najpierw `git fetch`, potem `git checkout <gałąź>` |
| `unrecognized arguments: --rtsp` | Uruchomiona stara wersja z `main` (checkout się nie udał) | j.w. |
| VLC: „System nie może odnaleźć określonej ścieżki” | VLC 32-bitowy | `C:\Program Files (x86)\VideoLAN\VLC\vlc.exe` |
| VLC: „nie mógł połączyć się z 192.168.0.124:8554” | Na Jetsonie nie działa serwer RTSP | Najpierw `linesight_app.py --rtsp`, potem VLC |
| Kawałki bufora na zmianę ~0,5 i ~1 MB | `max-size-time` = dokładnie 2 GOP-y; splitmuxsink czasem tnie po 1 GOP | `max-size-time` 2,5 s |
| `scp: ~/linesight_clips/*.mp4: No such file` | Brak klipów: zwykła `bottle` nie zapisuje klipu (domyślnie tylko `missing_cap,fallen`) | Do testu `--clip-classes bottle,missing_cap,fallen` |
| CPU w tegrastats `@102` | Zegary dynamiczne po restarcie | `sudo nvpmodel -m 0 && sudo jetson_clocks` |
| Biały balans kamery 15000 K zamiast 5500 K | Ustawienia v4l2 nie przetrwały | `extra-controls=c,white_balance_temperature_auto=0,white_balance_temperature=5500` w `v4l2src` |

## Decyzje etapu
- **DeepStream 6.0.1** (nie 6.0) – jedyna wersja dla JetPack 4.6.1.
- **NMS w nvinfer** (`cluster-mode=2`, IoU 0,7, próg 0,45 z E1-08) – parser tylko dekoduje tensor.
- **Tracker IOU, `checkClassMatch: 1`** – GPU zajęte w 80-98% przez model, NvDCF poza MVP.
- **Testy zliczania na nagraniu**, nie na żywo – powtarzalne po każdej zmianie parametrów.
- **RTSP przez `GstRtspServer` w procesie aplikacji**, jeden koder NVENC + `tee` – bez drugiego procesu i bez podwójnego kodowania.
- **Klipy: `splitmuxsink` w `/dev/shm` + `ffmpeg -c copy`** – bez NvDsSR (brak w pyds) i bez ponownego kodowania; klip centrowany na przecięciu linii.
- **Opóźnienie mierzone dwiema metodami**: od szkła do szkła (cały tor) i tracerem GStreamera (sam Jetson) – rozkład zamiast jednej liczby.
