# Etap 7 – dokumentacja końcowa i liczby

Bez filmu demo (decyzja 18.11, `backlog.md`). Analiza pokrycia ogłoszenia: [analiza.md](analiza.md).

## Status łącza PLC w Grafanie (E7-02)

**Objaw:** status PLC w Grafanie co 5 s online / offline, choć dane płynęły.

Diagnoza (laptop, cmd):

```
docker exec linesight-db psql -U linesight -d linesight -c "SELECT time, online FROM link_status WHERE source='plc' AND time > now() - interval '24 hours' ORDER BY time DESC LIMIT 40;"
docker logs linesight-bridge --tail 6
python tools\opcua_browse.py
python tools\opcua_browse.py --url opc.tcp://192.168.0.90:4840
```

| Pomiar | Wynik |
|---|---|
| `link_status` | przełączenie co 5,0 s = `WATCHDOG_S` + `RETRY_S` |
| log mostu | `BadNodeIdUnknown` po każdym połączeniu |
| `opcua_browse` na 192.168.0.244 | 0 zmiennych `GVL_Line` – w sterowniku nie ma aplikacji LineSight |
| `opcua_browse` na 192.168.0.90 | 22 zmienne, w tym wszystkie 15 mostu (aplikacja tymczasowo na tym sterowniku) |

**Przyczyna:** asyncua przy subskrypcji listy węzłów nie rzuca wyjątku dla złego węzła – zwraca `StatusCode` zamiast
uchwytu. Most uznawał połączenie za udane, a strażnik czytał zmienną aplikacji (`iStateCurrent`) → `BadNodeIdUnknown`
→ „offline” → po 5 s ponownie. Brak aplikacji wyglądał jak zerwane łącze.

**Poprawka** (`bridge/opcua_mqtt_bridge.py`, PR #83, #84):
- strażnik czyta `Server.ServerStatus.CurrentTime` (`i=2258`) – węzeł, który ma każdy serwer OPC UA,
- `missing_signals()`: brakujące zmienne w logu z nazwami; gdy brak wszystkich – status zostaje „offline”,
- `publish_status()`: status tylko przy zmianie (wcześniej przy wyjętym kablu „offline” co ok. 10 s),
- `OPCUA_URL` w compose nadpisywalny: `set OPCUA_URL=opc.tcp://192.168.0.90:4840` przed `up -d bridge`
  (domyślnie 192.168.0.244),
- testy: `bridge/test_bridge.py` (4 testy) i test na lokalnym serwerze asyncua (2/15 zmiennych → online
  z ostrzeżeniem, 0/15 → offline).

Przebudowa mostu: `docker compose -f infra\docker-compose.yml up -d --build bridge`.

**Test na sterowniku .90 (18.11):** 15 z 15 zmiennych; kabel wyjęty → offline, podłączony → online po ok. 5 s
(wyjście na offline do ok. 10 s: sen strażnika + jego limit czasu); potem 12 min bez żadnej zmiany statusu.

## Diagram architektury (E7-03)

Dwa diagramy Mermaid w README (GitHub rysuje je sam, bez pliku graficznego): przepływ danych w pracy
(linia → Jetson → laptop) i pętla MLOps (rejestr w GCS → Jetson → niepewne klatki → retrening). Jeden wspólny
diagram był nieczytelny – linie się krzyżowały.

## H.264 vs H.265 na NVENC (E7-04)

**Po co:** ogłoszenie wymienia kodowanie H.264/H.265; dotąd potok używał tylko H.264.

Jetson (SSH):

```
cd ~/linesight && git pull
bash jetson/codec_bench.sh ~/linesight_clips/20261116-171024_fallen_id26.mp4
PRESET=4 bash jetson/codec_bench.sh ~/linesight_clips/20261116-171024_fallen_id26.mp4
```

`codec_bench.sh`: z klipu zdarzenia ffmpeg robi referencję (stałe 30 FPS, libx264 High crf 10, 512 klatek
640x360); GStreamer dekoduje ją sprzętowo (`nvv4l2decoder`) i koduje `nvv4l2h264enc` (profil High, `profile=4`)
albo `nvv4l2h265enc` (Main) w CBR (`control-rate=1`), GOP 30; ffmpeg liczy PSNR i SSIM względem referencji.
Właściwości kodera wg „Accelerated GStreamer” L4T R32 i opisu gst-nvvideo4linux2.

| Preset | Bitrate | H.264 PSNR / SSIM | H.265 PSNR / SSIM | H.265 − H.264 | FPS H.264 / H.265 |
|---|---|---|---|---|---|
| UltraFast (domyślny) | 500 kb/s | 44,62 / 0,9857 | 43,59 / 0,9822 | −1,03 dB | 652 / 658 |
| | 1000 kb/s | 47,81 / 0,9914 | 47,09 / 0,9899 | −0,72 dB | 660 / 647 |
| | 2000 kb/s | 50,38 / 0,9947 | 48,70 / 0,9934 | −1,68 dB | 658 / 653 |
| Slow (`preset-level=4`) | 500 kb/s | 44,95 / 0,9864 | 45,65 / 0,9877 | **+0,70 dB** | 598 / 432 |
| | 1000 kb/s | 48,02 / 0,9918 | 48,29 / 0,9919 | +0,27 dB | 581 / 377 |
| | 2000 kb/s | 50,68 / 0,9950 | 50,35 / 0,9944 | −0,33 dB | 588 / 340 |

FPS = dekodowanie + kodowanie pliku tak szybko, jak się da (czas rzeczywisty to 30 FPS).

**Wnioski:**
- Na domyślnym presecie H.265 przegrywa przy każdym bitrate. Zysk H.265 bierze się z większych bloków
  (CTU do 64x64) i dłuższego przeszukiwania; przy 640x360 i najkrótszym przeszukiwaniu narzędzia się nie zwracają.
- Na presecie Slow H.265 wygrywa tylko przy niskim bitrate: przy 500 kb/s ta sama jakość co H.264 przy ok. 580 kb/s
  (interpolacja w skali log bitrate'u), czyli ok. 15-17 % mniej bitów – nie podręcznikowe 30-50 %. Kosztuje to ok. 30-40 %
  przepustowości kodera H.265 (432-340 vs 650 FPS).
- **Decyzja: potok zostaje przy H.264.** Zysk z H.265 jest mały przy tej rozdzielczości, a H.264 ma lepszą zgodność
  z klientami RTSP i przeglądarkami. H.265 miałby sens przy wielu kamerach / wyższej rozdzielczości albo przy wysyłce
  klipów przez wolne łącze – wtedy z presetem Slow.

**Znaleziska po drodze:**
- `nvv4l2h264enc` domyślnie koduje w profilu **Baseline** (log: `H264: Profile = 66`) – bez ramek B i CABAC.
  Uczciwe porównanie wymaga `profile=4` (High). Potok na żywo (`linesight_app.py`, 4 Mb/s) też koduje w Baseline –
  do sprawdzenia, czy High pozwala obniżyć bitrate RTSP (backlog, otwarte).
- Klipy zdarzeń mają nieregularne znaczniki czasu (`r_frame_rate` 12000/1 – bufor kołowy sklejany `ffmpeg concat`).
  Porównanie PSNR wprost z klipem parowało złe klatki: PSNR płaski ok. 31-34 dB niezależnie od bitrate'u, także po
  przenumerowaniu klatek (`setpts=N/(30*TB)`). Dopiero wspólna referencja o stałym FPS dała wiarygodny pomiar.
  Klipy się odtwarzają; nieregularne czasy przeszkadzają tylko w analizie klatka po klatce.
- Polska lokalizacja na Jetsonie: `printf %f` oczekuje przecinka – w skryptach `LC_NUMERIC=C`.
- H.265 2000 kb/s na presecie domyślnym raz zgubił ostatnią klatkę (511/512) przy zamykaniu strumienia;
  w powtórce na Slow – 512.
