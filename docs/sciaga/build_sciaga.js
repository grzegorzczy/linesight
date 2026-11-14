const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, AlignmentType, Footer, PageNumber,
  TableOfContents,
} = require('docx');

const FONT = 'Arial';
const MONO = 'Consolas';
const W = 9638; // A4 content width (DXA) with 2 cm margins

const TAGS = {
  JETSON: { label: 'JETSON (monitor + klawiatura)', color: '7A3E9D' },
  SSH1: { label: 'SSH1', color: '1F6F3F' },
  SSH2: { label: 'SSH2', color: '2E7D7D' },
  LAPTOP: { label: 'LAPTOP (cmd)', color: '1F4E8C' },
  FIZ: { label: 'FIZYCZNIE', color: '8C5A1F' },
  ADMIN: { label: 'LAPTOP (cmd jako administrator)', color: '8C1F1F' },
  PLC: { label: 'CODESYS', color: 'B5651D' },
  WWW: { label: 'PRZEGLĄDARKA', color: '555555' },
};

const children = [];

function h1(t) { children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] })); }
function h2(t) { children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] })); }
function p(t, opts = {}) {
  const runs = Array.isArray(t) ? t : [new TextRun({ text: t, ...opts })];
  children.push(new Paragraph({ spacing: { after: 100 }, children: runs }));
}
function bullet(t) {
  const runs = Array.isArray(t) ? t : [new TextRun(t)];
  children.push(new Paragraph({ numbering: { reference: 'bul', level: 0 }, spacing: { after: 40 }, children: runs }));
}
function code(s) { return new TextRun({ text: s, font: MONO, size: 19 }); }

// Step: tag + short title, then command block(s), then optional note
function step(tag, title, cmds, note) {
  const t = TAGS[tag];
  children.push(new Paragraph({
    spacing: { before: 160, after: 60 }, keepNext: true,
    children: [
      new TextRun({ text: ` ${t.label} `, bold: true, color: 'FFFFFF', shading: { type: ShadingType.CLEAR, fill: t.color, color: 'auto' }, size: 18 }),
      new TextRun({ text: '  ' + title, bold: true }),
    ],
  }));
  const lines = Array.isArray(cmds) ? cmds : (cmds ? [cmds] : []);
  lines.forEach((line, i) => {
    children.push(new Paragraph({
      shading: { type: ShadingType.CLEAR, fill: 'F2F2F2', color: 'auto' },
      indent: { left: 200 },
      keepNext: i < lines.length - 1 || !!note,
      spacing: { before: 0, after: i === lines.length - 1 ? 60 : 0 },
      children: [new TextRun({ text: line === '' ? ' ' : line, font: MONO, size: 18 })],
    }));
  });
  if (note) children.push(new Paragraph({ spacing: { after: 80 }, indent: { left: 200 }, children: [new TextRun({ text: note, italics: true, color: '555555', size: 19 })] }));
}

const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
const borders = { top: border, bottom: border, left: border, right: border };
function table(widths, rows, header = true) {
  const sum = widths.reduce((a, b) => a + b, 0);
  children.push(new Table({
    width: { size: sum, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: header && ri === 0,
      children: r.map((c, ci) => new TableCell({
        borders,
        width: { size: widths[ci], type: WidthType.DXA },
        shading: header && ri === 0 ? { type: ShadingType.CLEAR, fill: 'D9E2F3', color: 'auto' } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({
          children: [new TextRun({
            text: c, bold: header && ri === 0, size: 19,
            font: (!(header && ri === 0) && ci === 0 && /^[a-z\/~`"\.]|^\w+-|^\w+\s+-/.test(c) && widths.length === 2 && false) ? MONO : FONT,
          })],
        })],
      })),
    })),
  }));
  children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
}

// ---------- CONTENT ----------
children.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun('LineSight – ściąga konfiguracji')] }));
p([new TextRun({ text: 'Od zera do podglądu kamery i środowiska na laptopie. Same komendy, w kolejności. Stan: 14.11.2026, etap 3 (MVP) zakończony. Kamera: DeepStream → zdarzenia MQTT. PLC: variTRON 300 (PackML) → OPC UA → most → MQTT. Laptop: Mosquitto, TimescaleDB, Grafana w Dockerze.', color: '555555' })]);

h1('0. Dane i układ okien');
table([3000, 6638], [
  ['Co', 'Wartość'],
  ['Jetson', 'grzegorz@192.168.0.124, nazwa: grzegorz-desktop'],
  ['System Jetsona', 'JetPack 4.6.1 (L4T R32.7.1), Ubuntu 18.04, TensorRT 8.2.1.8, CUDA 10.2'],
  ['Laptop', 'IP 192.168.0.203 (Wi-Fi), Windows, cmd'],
  ['GPU laptopa', 'RTX 3050 Ti Laptop 4 GB, sterownik 595.95, CUDA Version (max) 13.2'],
  ['Środowisko laptopa', '.venv: torch 2.11.0+cu128, torchvision 0.26.0+cu128, ultralytics 8.4.208, onnx 1.23.2'],
  ['Python laptopa', '3.12.4'],
  ['Folder projektu', 'C:\\Users\\Grzesiek\\Desktop\\linesight'],
  ['GitHub', 'github.com/grzegorzczy/linesight'],
  ['Kamera', 'ASUS „web camera”, /dev/video0, YUYV 640x360 @ 30 FPS'],
  ['Model', 'YOLO26n, ONNX opset 13, silnik FP16 ok. 20 FPS (640x640)'],
  ['Sterownik (PLC)', 'JUMO variTRON 300 (705003), 192.168.0.244, CODESYS V3.5 SP22 Patch 4, MainTask 10 ms (t#10ms)'],
  ['OPC UA', 'opc.tcp://192.168.0.244:4840, anonimowo, ns=4, zmienne GVL_Line'],
  ['Docker na laptopie', 'mosquitto :1883, bridge (OPC UA → MQTT), db (TimescaleDB) :5432, ingest (MQTT → baza), grafana :3000'],
  ['Tematy MQTT', 'linesight/vision/events, linesight/vision/status, linesight/plc/<zmienna>, linesight/plc/status'],
  ['Baza', 'linesight / linesight (Grafana: grafana_ro / grafana_ro, tylko odczyt)'],
]);

h1('Szybki start: wszystko naraz');
step('LAPTOP', 'Usługi w Dockerze (Docker Desktop uruchomiony)', ['cd /d "C:\\Users\\Grzesiek\\Desktop\\linesight"', 'git pull', 'docker compose -f infra/docker-compose.yml up -d --build', 'docker ps'], 'Oczekiwane: linesight-mosquitto, -bridge, -db, -ingest, -grafana – wszystkie „Up”.');
step('PLC', 'Linia', 'Online → Login, Start (F5); w GVL_Line: xCmdReset TRUE→FALSE, xCmdStart TRUE→FALSE (Ctrl+F7 zapisuje)', 'iStateCurrent = 6 (Execute).');
step('SSH1', 'Kamera i zdarzenia', ['sudo nvpmodel -m 0 && sudo jetson_clocks', 'cd ~/linesight && git pull', 'cd deepstream && python3 linesight_app.py --rtsp --clips --mqtt 192.168.0.203']);
step('LAPTOP', 'Odpalenie kamery w cmd (podgląd RTSP)', '"C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe" --network-caching=200 --rtsp-tcp rtsp://192.168.0.124:8554/linesight', 'Najpierw program na Jetsonie, potem VLC.');
step('WWW', 'Dashboard', 'http://localhost:3000', 'Login admin, hasło linesight.');
p('Trzy okna cmd na laptopie:');
table([2200, 7438], [
  ['Okno', 'Do czego'],
  ['SSH1', 'Sesja SSH na Jetsonie – uruchamia potoki gst-launch (okno jest wtedy zajęte)'],
  ['SSH2', 'Druga sesja SSH – zmiana ustawień kamery na żywo, tegrastats'],
  ['LAPTOP', 'Zwykły cmd na laptopie – ipconfig, scp, VLC, git, Python'],
]);
p([new TextRun({ text: 'Zasada: przed zamknięciem okna z gst-launch zawsze Ctrl+C. Inaczej proces zostaje na Jetsonie i blokuje kamerę („Device is busy”).', bold: true })]);

h1('Teoria w skrócie: od GPU do silnika TensorRT');
table([1900, 3900, 1900, 1938], [
  ['Warstwa', 'Co to jest', 'Laptop', 'Jetson'],
  ['GPU', 'Sprzęt: tysiące prostych rdzeni liczących równolegle', 'RTX 3050 Ti, 2560 rdzeni', 'Maxwell, 128 rdzeni'],
  ['Sterownik', 'Pozwala systemowi rozmawiać z GPU', '595.95', 'w L4T'],
  ['CUDA', 'Platforma NVIDII do obliczeń na GPU (język, kompilator, biblioteki). To nie karta – to „język” do karty', '12.8 (w pakiecie PyTorch)', '10.2 (w JetPacku)'],
  ['cuDNN', 'Gotowe, szybkie operacje sieci: splot, pooling, aktywacje', 'w PyTorch', 'w JetPacku'],
  ['PyTorch', 'Framework do definiowania i trenowania sieci (gradienty)', '2.11', '–'],
  ['ultralytics', 'Modele YOLO + trening i eksport jedną komendą', '8.4.208', '–'],
  ['TensorRT', 'Kompilator i silnik inferencji pod konkretne GPU', '–', '8.2.1'],
]);
bullet('Trening (laptop): model uczy się na tysiącach zdjęć – dużo obliczeń, potrzebna elastyczność.');
bullet('Inferencja (Jetson): wagi zamrożone, model tylko odpowiada 30 razy na sekundę – liczy się szybkość.');
bullet('CUDA nie instalowaliśmy osobno: jest w pakiecie PyTorch (+cu128). Bez CUDA PyTorch liczyłby na CPU, 10–50 razy wolniej.');
p([new TextRun({ text: 'Analogia z CODESYS', bold: true })]);
table([4819, 4819], [
  ['CODESYS', 'LineSight'],
  ['Program w ST w IDE', 'Model wytrenowany w PyTorch (.pt)'],
  ['Eksport do PLCopen XML (format wymiany)', 'Eksport do ONNX (format wymiany)'],
  ['Kompilacja pod konkretny sterownik', 'TensorRT buduje silnik (.engine) pod konkretne GPU i wersję TensorRT'],
  ['Binarka z PLC A nie ruszy na PLC B', 'Silnik budujemy na Jetsonie, nie na laptopie'],
  ['Stary runtime nie zna nowych bloków', 'TensorRT 8.2 zna operacje tylko do opset 13'],
]);
p([new TextRun({ text: 'Co robi TensorRT przy budowie silnika', bold: true })]);
bullet('Łączy warstwy (splot + normalizacja + aktywacja = jeden kernel) – mniej ruchu w pamięci.');
bullet('Dobiera najszybszą implementację każdej operacji na danym GPU (autotuning) – dlatego budowa trwa minuty.');
bullet('Obniża precyzję: FP32 (trening) → FP16 (ok. 2x szybciej, bez straty) → INT8 (wymaga kalibracji na naszych zdjęciach; na Jetsonie Nano może nic nie dać – Maxwell nie ma sprzętowego INT8).');
bullet('Planuje pamięć – ważne przy 4 GB współdzielonych z CPU.');
p([new TextRun({ text: 'Droga modelu', bold: true })]);
[
  'LAPTOP                                       JETSON',
  '[E1-03] zdjęcia z kamery --scp--> laptop',
  '[E1-04] etykiety (Ultralytics Platform)',
  '[E1-06] trening PyTorch -> best.pt',
  '[E1-07] eksport -> best.onnx (opset 13) --scp--> trtexec -> best.engine',
  '                                             [E1-08] benchmark FP32/FP16/INT8',
  '                                             [etap 2] DeepStream: kamera > silnik > tracking > RTSP',
].forEach((l, i, a) => children.push(new Paragraph({ shading: { type: ShadingType.CLEAR, fill: 'F2F2F2', color: 'auto' }, spacing: { before: 0, after: i === a.length - 1 ? 120 : 0 }, children: [new TextRun({ text: l, font: MONO, size: 16 })] })));
p('E1-02 przechodzi tę drogę „na sucho” na gotowych modelach YOLO: architektura, która nie przejdzie przez TensorRT 8.2, odpada przed zbieraniem zdjęć.');
p('Docker: na Jetsonie jest (przyszedł z JetPackiem), ale go nie używamy – kamera, TensorRT i DeepStream działają bezpośrednio w systemie. Sprawdzenie: sudo docker ps (pusta lista = nic nie działa). Docker pracuje na laptopie w etapie 3 (MQTT, TimescaleDB, Grafana). SSH to tylko zdalny terminal.');

h1('1. Jetson: IP, nazwa, SSH');
p('Robione raz, przy monitorze i klawiaturze podpiętych do Jetsona (albo gdy IP się zmieni).');
step('JETSON', 'Czy działa serwer SSH', 'systemctl status ssh', 'Oczekiwane: active (running).');
step('JETSON', 'Adres IP Jetsona', 'hostname -I', 'Pierwszy adres 192.168.0.x to Jetson. 172.17.0.1 to wewnętrzna sieć Dockera.');
step('JETSON', 'Nazwa urządzenia i użytkownik', ['hostname', 'whoami']);
step('LAPTOP', 'Adres IP laptopa', 'ipconfig', 'Szukaj „IPv4 Address” przy karcie Wi-Fi (192.168.0.x). 169.254.x.x = karta bez DHCP, pomijamy.');

h1('2. Połączenie SSH');
step('SSH1', 'Logowanie (to samo w SSH2)', 'ssh grzegorz@192.168.0.124', 'Zawsze z „grzegorz@”. Bez tego SSH loguje się jako użytkownik Windows (Grzesiek), którego na Jetsonie nie ma. Pierwsze połączenie: wpisz yes.');
step('SSH1', 'Wylogowanie', 'exit');

h1('3. Folder projektu i repozytorium');
table([3000, 6638], [
  ['Co', 'Ścieżka'],
  ['Folder projektu (lokalne repo)', 'C:\\Users\\Grzesiek\\Desktop\\linesight'],
  ['Ta ściąga', 'C:\\Users\\Grzesiek\\Desktop\\linesight\\LineSight-sciaga.docx'],
  ['Dokumentacja etapów', 'C:\\Users\\Grzesiek\\Desktop\\linesight\\docs\\'],
  ['Zdjęcia do dokumentacji', 'C:\\Users\\Grzesiek\\Desktop\\linesight\\docs\\img\\'],
  ['Środowisko Python', 'C:\\Users\\Grzesiek\\Desktop\\linesight\\.venv\\'],
  ['Plik SDP dla VLC', 'C:\\Users\\Grzesiek\\Desktop\\jetson.sdp'],
]);
step('LAPTOP', 'Wejście do folderu projektu (każde nowe okno cmd)', 'cd /d "C:\\Users\\Grzesiek\\Desktop\\linesight"', '/d zmienia też dysk, gdy cmd startuje na innym (np. D:). Krótsza wersja: cd /d "%USERPROFILE%\\Desktop\\linesight".');
step('LAPTOP', 'Otwarcie folderu w Eksploratorze / VS Code', ['explorer "C:\\Users\\Grzesiek\\Desktop\\linesight"', 'code "C:\\Users\\Grzesiek\\Desktop\\linesight"']);
p('Praca z Claude: w aplikacji Claude (desktop) podłącz folder C:\\Users\\Grzesiek\\Desktop\\linesight („+” → Add folder). Claude zapisuje tam ściągę i dokumentację, a GitHub obsługuje przez repo grzegorzczy/linesight. Na początku nowej rozmowy podaj tę ścieżkę razem z podsumowaniem etapu.');
step('LAPTOP', 'Na nowym komputerze: pobranie repo', ['cd "%USERPROFILE%\\Desktop"', 'git clone https://github.com/grzegorzczy/linesight.git']);
step('LAPTOP', 'Na co dzień: aktualizacja z GitHuba', ['cd "%USERPROFILE%\\Desktop\\linesight"', 'git switch main', 'git pull']);
step('LAPTOP', 'Stan i historia', ['git status', 'git log --oneline --all --graph']);
step('LAPTOP', 'Gdy git push zwraca 403 (zapamiętane inne konto GitHub)', ['cmdkey /list | findstr github', 'cmdkey /delete:git:https://github.com'], 'Przy następnym push Git poprosi o logowanie w przeglądarce.');
p('Konwencje: gałąź na etap/zadanie (etap1/scena), zmiany do main tylko przez PR, commity z prefiksem feat: / fix: / docs: / chore:.');

h1('4. Kontrola Jetsona');
step('SSH1', 'Wersja L4T', 'cat /etc/nv_tegra_release');
step('SSH1', 'RAM, swap, dysk', ['free -h', 'swapon --show', 'df -h /'], 'Po starcie bez pulpitu: ok. 3,4 GB RAM dostępne, swap 5,9 GB (zram + plik 4 GB), ok. 12 GB wolne na karcie.');
step('SSH2', 'Obciążenie CPU/GPU/RAM na żywo', 'tegrastats', 'Ctrl+C kończy.');
p([new TextRun({ text: 'Nie uruchamiać apt upgrade – może zepsuć zgodność z JetPack 4.6.1. Komend z sudo nie wklejać hurtem z innymi (kolejne linie lecą do pola hasła).', italics: true })]);

h1('5. Kamera: identyfikacja i zwalnianie');
step('SSH1', 'Jakie kamery widzi system', 'v4l2-ctl --list-devices');
step('SSH1', 'Formaty, rozdzielczości, FPS', 'v4l2-ctl -d /dev/video0 --list-formats-ext', 'Kamera ASUS: YUYV tylko 640x360; MJPG i H.264 do 1920x1080. Wszystko 30 FPS.');
step('SSH1', 'Ustawienia kamery i ich zakresy', 'v4l2-ctl -d /dev/video0 -l');
step('SSH1', 'Urządzenia USB', 'lsusb');
step('SSH1', 'Pomiar FPS (300 klatek)', 'v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=360,pixelformat=YUYV --stream-mmap --stream-count=300', 'Wynik: ok. 29–30 fps.');
p('Gdy gst-launch zgłasza „Device \'/dev/video0\' is busy”:');
step('SSH1', 'Kto trzyma kamerę', ['sudo fuser -v /dev/video0', 'pgrep -a gst-launch']);
step('SSH1', 'Zakończenie procesu', ['pkill gst-launch', 'kill 7532        # albo konkretny PID z fuser (liczba, nie słowo PID)', 'kill -9 7532     # gdy zwykły kill nie pomógł']);
step('SSH1', 'Kontrola (pusty wynik = kamera wolna)', 'sudo fuser -v /dev/video0');

h1('6. Ustawienia kamery (po każdym restarcie i podłączeniu)');
step('SSH1', 'Balans bieli zablokowany na 5500 K', 'v4l2-ctl -d /dev/video0 -c white_balance_temperature_auto=0 -c white_balance_temperature=5500', 'Niżej = cieplej, wyżej = zimniej. Krok co 60. Białe elementy żółte → podnieś; niebieskie → obniż.');
step('SSH1', 'Odczyt kontrolny', 'v4l2-ctl -d /dev/video0 --get-ctrl=white_balance_temperature_auto,white_balance_temperature');
p('Ekspozycja: kamera ASUS ma tylko exposure_absolute (10–2000), który nie działa – ekspozycja jest automatyczna, bez gain. Jedyna dźwignia przeciw rozmyciu ruchu: więcej światła od przodu. Ostrość: ręczna, pierścieniem na obiektywie (zablokowany taśmą).');

h1('7. Podgląd na żywo na laptopie (VLC)');
p('Jetson koduje obraz sprzętowo do H.264 i wysyła RTP/UDP na port 5000 laptopa. VLC odbiera według pliku jetson.sdp.');
step('LAPTOP', 'Plik jetson.sdp (raz) – wklej cały blok', [
  '(',
  'echo v=0',
  'echo o=- 0 0 IN IP4 127.0.0.1',
  'echo s=Jetson',
  'echo c=IN IP4 0.0.0.0',
  'echo t=0 0',
  'echo m=video 5000 RTP/AVP 96',
  'echo a=rtpmap:96 H264/90000',
  ') > "%USERPROFILE%\\Desktop\\jetson.sdp"',
]);
step('LAPTOP', 'Kontrola pliku (7 linii)', 'type "%USERPROFILE%\\Desktop\\jetson.sdp"');
step('LAPTOP', 'Uruchomienie VLC', 'start "" "C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe" --network-caching=150 "%USERPROFILE%\\Desktop\\jetson.sdp"', 'Przy pierwszym uruchomieniu: zezwól VLC na sieć prywatną w zaporze Windows.');
step('SSH1', 'Ustawienia kamery (punkt 6), potem nadawanie', [
  "gst-launch-1.0 -e v4l2src device=/dev/video0 ! \\",
  "  video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 ! \\",
  "  nvvidconv ! 'video/x-raw(memory:NVMM),format=I420' ! \\",
  "  nvv4l2h264enc insert-sps-pps=1 iframeinterval=30 bitrate=4000000 ! \\",
  "  h264parse ! rtph264pay config-interval=1 pt=96 ! \\",
  "  udpsink host=192.168.0.203 port=5000 sync=false",
], 'host = IP laptopa. Okno zostaje zajęte. Koniec: Ctrl+C i czekaj na „Freeing pipeline”.');
step('SSH2', 'Strojenie na żywo (gdy strumień leci)', 'v4l2-ctl -d /dev/video0 -c white_balance_temperature=5000');
step('SSH1', 'Sprawdzenie, czy koder ma potrzebne opcje', 'gst-inspect-1.0 nvv4l2h264enc | grep -E "insert-sps-pps|iframeinterval|bitrate"');
table([3200, 6438], [
  ['Element potoku', 'Co robi'],
  ['v4l2src', 'Czyta obraz z kamery'],
  ['video/x-raw,...', 'Wymuszony format: YUYV 640x360, 30 FPS'],
  ['nvvidconv', 'Przenosi klatkę do pamięci NVMM (dla sprzętowego kodera)'],
  ['nvv4l2h264enc', 'Sprzętowy koder H.264; klatka kluczowa co 30 klatek z nagłówkami SPS/PPS'],
  ['h264parse, rtph264pay', 'Pakowanie strumienia w RTP'],
  ['udpsink', 'Wysyłka UDP na laptopa; sync=false = bez czekania na zegar'],
]);

h1('8. Scena (E1-01)');
bullet('Kamera nieruchoma, ostrość pierścieniem, potem pierścień zablokowany taśmą. Kamery już nie ruszamy.');
bullet('Tło: kaloryfer (jednolity, stały), bez okna, drzwi i przedmiotów z pokoju w kadrze.');
bullet('Butelki całe w kadrze (dno i nakrętka z marginesem), nie stawiać wyżej ani bliżej niż na zdjęciu referencyjnym.');
bullet('Światło od przodu lub z boku, nigdy zza butelek (pod światło = ciemna sylwetka).');
bullet('Balans bieli 5500 K, ekspozycja automatyczna (ograniczenie kamery).');
bullet('Paski kaloryfera prześwitują przez butelki – sprawdzone w E1-06: model patrzy na butelki; jedyny ślad to słaba aktywacja na żebrach przy prawej krawędzi pustego kadru (pod progiem).');
p('Zdjęcie referencyjne: docs\\img\\etap1-scena.jpg');

h1('9. Zdjęcie sceny i kopiowanie na laptopa');
step('SSH1', 'Zatrzymaj podgląd', 'Ctrl+C', 'Kamera może mieć tylko jeden strumień naraz.');
step('SSH1', 'Usuń stare i zapisz 30 klatek', [
  'rm -f scena_*.jpg',
  "gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=30 ! \\",
  "  video/x-raw,format=YUY2,width=640,height=360,framerate=30/1 ! \\",
  "  jpegenc ! multifilesink location=scena_%02d.jpg",
], '30 klatek, bo automatyczna ekspozycja potrzebuje chwili po starcie – bierzemy ostatnią (scena_29.jpg).');
step('SSH1', 'Kontrola', 'ls -l scena_*.jpg');
step('LAPTOP', 'Kopiowanie', 'scp grzegorz@192.168.0.124:~/scena_29.jpg "%USERPROFILE%\\Desktop\\linesight\\docs\\img\\etap1-scena.jpg"');
step('LAPTOP', 'Podgląd zdjęcia', 'start "" "%USERPROFILE%\\Desktop\\linesight\\docs\\img\\etap1-scena.jpg"');

h1('10. Laptop: środowisko Python (trening i eksport ONNX)');
p('Po co: na laptopie trenujemy model (PyTorch + GPU) i eksportujemy go do ONNX. ONNX to plik przenoszony na Jetsona, gdzie TensorRT buduje z niego silnik.');
table([2600, 3500, 3538], [
  ['', 'LAPTOP', 'JETSON'],
  ['Rola', 'trening, eksport ONNX', 'silnik TensorRT, inferencja, wideo'],
  ['CUDA', '12.8 (w kole PyTorch +cu128)', '10.2 (w JetPack 4.6.1)'],
  ['Biblioteki', 'PyTorch 2.11, ultralytics 8.4.208, onnx 1.23.2', 'TensorRT 8.2.1, trtexec'],
  ['Plik wyjściowy', 'model.pt → model.onnx', 'model.engine (budowany tylko na Jetsonie)'],
]);
step('LAPTOP', 'Wersja Pythona i GPU', ['cd /d "C:\\Users\\Grzesiek\\Desktop\\linesight"', 'python --version', 'nvidia-smi'], 'Wynik: Python 3.12.4; RTX 3050 Ti Laptop 4 GB, sterownik 595.95, CUDA Version (max) 13.2.');
p([new TextRun({ text: 'Długie komendy (pip install) wklejamy pojedynczo i czekamy na znak zachęty. Wklejony blok przerywa pobieranie („Operation cancelled by user”).', bold: true })]);
step('LAPTOP', 'Nowe środowisko (raz)', 'python -m venv .venv', 'Folder .venv jest w .gitignore.');
step('LAPTOP', 'Włączenie środowiska (każde nowe okno cmd)', '.venv\\Scripts\\activate', 'Przed znakiem zachęty pojawia się (.venv). Wyłączenie: deactivate.');
step('LAPTOP', 'Aktualizacja pip', 'python -m pip install --upgrade pip');
step('LAPTOP', 'Instalacja z pliku wersji (zalecana)', 'pip install -r training\\requirements.txt', 'Plik zawiera indeks pytorch.org, więc PyTorch przyjdzie z CUDA. Ok. 3 GB pobierania.');
p('Albo ręcznie, w tej kolejności (PyTorch przed ultralytics, inaczej pip dociągnie PyTorch bez CUDA):');
step('LAPTOP', 'PyTorch z CUDA 12.8 (ok. 2,8 GB)', 'pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128');
step('LAPTOP', 'Ultralytics i ONNX', 'pip install ultralytics onnx');
step('LAPTOP', 'Czy PyTorch widzi GPU', 'python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"', 'Oczekiwane: 2.11.0+cu128 True NVIDIA GeForce RTX 3050 Ti Laptop GPU');
step('LAPTOP', 'Raport środowiska ultralytics', 'yolo checks', 'Oczekiwane: CUDA:0 (NVIDIA GeForce RTX 3050 Ti Laptop GPU, 4096MiB).');
step('LAPTOP', 'Wersje pakietów', 'pip list | findstr /i "torch ultralytics onnx"', 'findstr /i = grep w cmd, bez rozróżniania wielkości liter.');
step('LAPTOP', 'Usunięcie środowiska (gdy trzeba zacząć od zera)', ['deactivate', 'rmdir /s /q .venv']);
p('Dysk laptopa: ok. 17 GB wolne – nie trzymać kopii zbioru ani starych folderów runs.');

h1('10b. Test modeli: ONNX → TensorRT (E1-02)');
p('Po co: każdy kandydat przechodzi drogę .pt → ONNX (laptop) → silnik TensorRT (Jetson). Opset 13, bo parser ONNX w TensorRT 8.2 obsługuje operacje tylko do opset 13.');
step('LAPTOP', 'Folder roboczy (z aktywnym .venv)', ['mkdir training\\e1-02', 'cd training\\e1-02']);
step('LAPTOP', 'Eksport do ONNX (wagi bazowe pobiorą się same)', [
  'yolo export model=yolov8n.pt format=onnx opset=13 imgsz=640 simplify=True',
  'yolo export model=yolo11n.pt format=onnx opset=13 imgsz=640 simplify=True',
  'yolo export model=yolo26n.pt format=onnx opset=13 imgsz=640 simplify=True',
], 'Każdą komendę osobno. Pliki .pt i .onnx są w .gitignore.');
step('LAPTOP', 'Kontrola opsetu i kształtu wyjścia', 'python -c "import onnx; [print(f, [o.version for o in onnx.load(f).opset_import], [[d.dim_value for d in o.type.tensor_type.shape.dim] for o in onnx.load(f).graph.output]) for f in [\'yolov8n.onnx\',\'yolo11n.onnx\',\'yolo26n.onnx\']]"', 'Oczekiwane: [13] i [[1, 84, 8400]] dla każdego.');
step('SSH1', 'Folder na Jetsonie', 'mkdir -p ~/e1-02');
step('LAPTOP', 'Kopiowanie na Jetsona', 'scp yolov8n.onnx yolo11n.onnx yolo26n.onnx grzegorz@192.168.0.124:~/e1-02/');
step('SSH1', 'Tryb mocy (tylko odczyt)', 'sudo nvpmodel -q', 'Wynik: MAXN (tryb 0) = pełna moc.');
step('SSH1', 'Flagi trtexec w tej wersji TensorRT', ['cd ~/e1-02', '/usr/src/tensorrt/bin/trtexec --help | grep -iE "workspace|fp16"']);
step('SSH1', 'Budowa silnika FP16 (każdy model osobno, ok. 12–15 min)', [
  '/usr/src/tensorrt/bin/trtexec --onnx=yolov8n.onnx --saveEngine=yolov8n_fp16.engine --fp16 --workspace=1024 2>&1 | tee build_yolov8n.log',
  '/usr/src/tensorrt/bin/trtexec --onnx=yolo11n.onnx --saveEngine=yolo11n_fp16.engine --fp16 --workspace=1024 2>&1 | tee build_yolo11n.log',
  '/usr/src/tensorrt/bin/trtexec --onnx=yolo26n.onnx --saveEngine=yolo26n_fp16.engine --fp16 --workspace=1024 2>&1 | tee build_yolo26n.log',
], 'Ekran „stoi” podczas autotuningu – to normalne. Koniec: &&&& PASSED TensorRT.trtexec. „Some tactics do not have sufficient workspace memory” to informacja [I], nie błąd.');
step('SSH2', 'Podgląd pamięci i GPU w trakcie budowy', 'tegrastats', 'RAM ok. 2,1/3,9 GB, SWAP 0, GR3D_FREQ 70–99% = GPU pracuje.');
step('SSH2', 'Wyniki i rozmiar silników', ['grep -E "PASSED|FAILED|Throughput|GPU Compute Time: min" build_*.log', 'ls -lh *.engine'], 'W komendach zamieniaj nazwę modelu – nie wpisuj <model> (bash czyta < jako przekierowanie).');
table([1700, 1300, 1500, 1700, 1400, 2038], [
  ['Model', 'trtexec', 'Throughput', 'GPU Compute', 'Silnik', 'mAP COCO (docs)'],
  ['YOLOv8n', 'PASSED', '20,7 qps', '47,5 ms', '13 MB', '37,3'],
  ['YOLO11n', 'PASSED', '19,6 qps', '50,1 ms', '9,4 MB', '39,5'],
  ['YOLO26n ✔', 'PASSED', '20,0 qps', '49,2 ms', '9,0 MB', '40,9'],
]);
bullet('Wybór: YOLO26n – szybkość ≈ najszybszy, najwyższa dokładność, najmniejszy silnik.');
bullet('98% czasu inferencji to obliczenia GPU (kopiowanie < 1 ms) – przyspiesza tylko mniej obliczeń.');
bullet('FLOPs ≠ czas: YOLOv8n ma najwięcej GFLOPs, a jest najszybszy na Maxwellu.');
bullet('ok. 20 FPS < 30 FPS kamery – do E1-07/E1-08: wejście 640x384, stałe zegary, INT8.');

h1('10c. Zbieranie zdjęć (E1-03)');
p('Skrypt jetson/capture.py działa na Jetsonie (tam jest kamera): zapisuje zdjęcie co 8 s i jednocześnie wysyła podgląd do VLC. Zwykły Python 3.6 + OpenCV z JetPacka, bez TensorRT.');
step('SSH1', 'Repo na Jetsonie (raz)', ['cd ~', 'git clone https://github.com/grzegorzczy/linesight.git'], 'Aktualizacja: cd ~/linesight && git pull. Git na Jetsonie (2.17) nie zna git switch – używaj git checkout main.');
step('LAPTOP', 'Skrypt na laptopie (do podglądu w VS Code)', ['cd /d "C:\\Users\\Grzesiek\\Desktop\\linesight"', 'git pull', 'dir jetson']);
step('SSH1', 'Czy OpenCV ma GStreamer (raz)', 'python3 -c "import cv2; print(cv2.__version__); print([l.strip() for l in cv2.getBuildInformation().splitlines() if \'GStreamer\' in l])"', 'Oczekiwane: 4.1.1 i GStreamer: YES (1.14.5).');
step('SSH1', 'Kamera wolna (pusty wynik)', 'sudo fuser -v /dev/video0');
step('SSH1', 'Sesja zdjęć – NAJPIERW skrypt', ['cd ~/linesight', 'python3 jetson/capture.py --tag bottle --count 40'], 'Opcje: --interval (domyślnie 8 s), --start-delay (5 s), --no-preview. Ctrl+C kończy i zwalnia kamerę.');
step('LAPTOP', 'POTEM VLC: gdy w SSH1 pojawi się „Sesja: ...”, kliknij ▶', 'start "" "C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe" --network-caching=150 "%USERPROFILE%\\Desktop\\jetson.sdp"', 'VLC czeka na dane tylko kilka sekund i sam się zatrzymuje – stąd kolejność: Jetson, potem ▶.');
table([2000, 1000, 6638], [
  ['Tag', 'Zdjęć', 'Ustawienie'],
  ['bottle', '40', '1–3 butelki z nakrętkami, różne miejsca (także lewo i krawędzie) i obroty'],
  ['missing_cap', '50', '1–2 butelki bez nakrętki, nakrętki poza kadrem'],
  ['fallen', '50', '1–2 leżące w obie strony, reszta stoi'],
  ['mixed', '60', 'wszystkie stany, butelki na krawędziach, stykające się, zasłonięte'],
  ['empty', '15', 'samo tło (negatywy, bez etykiet)'],
]);
p('Zasady: ręce poza kadrem w chwili zdjęcia; kamery nie ruszamy; butelek nie stawiamy bliżej niż na zdjęciu referencyjnym.');
step('SSH1', 'Ile zdjęć w każdej sesji', ['for d in ~/dataset/raw/*/; do echo "$(ls "$d"*.jpg | wc -l)  $(basename "$d")"; done', 'du -sh ~/dataset/raw']);
step('LAPTOP', 'Kopiowanie na laptopa (data\\raw jest w .gitignore)', ['mkdir "C:\\Users\\Grzesiek\\Desktop\\linesight\\data\\raw"', 'scp -r grzegorz@192.168.0.124:~/dataset/raw/* "C:\\Users\\Grzesiek\\Desktop\\linesight\\data\\raw"'], 'Bez \\ na końcu ścieżki docelowej – w Windows \\" psuje cudzysłów (błąd „Invalid argument”).');
step('SSH1', 'Usunięcie sesji testowej (tylko konkretny tag)', ['rm -rf ~/dataset/raw/*_test', 'ls ~/dataset/raw/']);
step('LAPTOP', 'Usunięcie folderu w cmd', 'rmdir /s /q "C:\\Users\\Grzesiek\\Desktop\\linesight\\data\\raw\\<nazwa_folderu>"');
p([new TextRun({ text: 'Klasy do etykietowania (docs/etykietowanie.md)', bold: true })]);
table([1800, 7838], [
  ['Klasa', 'Kiedy'],
  ['bottle', 'stoi i ma nakrętkę'],
  ['missing_cap', 'stoi, bez nakrętki'],
  ['fallen', 'leży – niezależnie od nakrętki (pierwszeństwo: fallen > missing_cap > bottle)'],
]);

h1('10d. Etykietowanie na Ultralytics Platform (E1-04)');
p('Podział train/val/test robimy sami przed etykietowaniem (warstwowo po sesjach, 70/20/10, ziarno 42) i zamrażamy go w training/splits/split_v1.csv. Test też etykietujemy – to klucz odpowiedzi do oceny (mAP).');
step('LAPTOP', 'Paczka ZIP z podziałem (aktywne .venv)', ['cd /d "C:\\Users\\Grzesiek\\Desktop\\linesight"', 'git pull', 'python training\\make_upload_zip.py'], 'Wynik: data\\upload\\linesight_v1.zip (ok. 9,5 MB) i training\\splits\\split_v1.csv; tabela RAZEM 150 43 22 215.');
p('Przeglądarka (platform.ultralytics.com):');
bullet('Annotate → New Dataset → nazwa linesight, Task Type: Detect, Private.');
bullet('Przeciągnij linesight_v1.zip w pole „Drop images…” → Create & Upload.');
bullet('Classes: bottle, missing_cap, fallen – dokładnie w tej kolejności (indeksy 0, 1, 2). Sprawdź pisownię.');
bullet('Kontrola: 215 zdjęć, Train 150 / Val 43 / Test 22.');
table([2400, 7238], [
  ['Klawisz', 'Działanie w edytorze'],
  ['1 / 2 / 3', 'klasa bottle / missing_cap / fallen'],
  ['S', 'Smart (SAM): klik w środek butelki → ramka; Enter zatwierdza'],
  ['A', 'auto-zapis po każdym kliknięciu w trybie Smart'],
  ['V', 'ręczne rysowanie ramki'],
  ['← / →', 'poprzednie / następne zdjęcie'],
  ['Delete', 'usuń zaznaczoną ramkę'],
  ['Ctrl+Z', 'cofnij'],
  ['H', 'ukryj / pokaż ramki'],
  ['Ctrl+kółko', 'przybliżenie'],
]);
table([4400, 5238], [
  ['Co widać', 'Klasa'],
  ['stoi, różowa nakrętka', '1 bottle'],
  ['stoi, niebieskawa szyjka z pierścieniem, bez różu', '2 missing_cap'],
  ['leży (z nakrętką lub bez)', '3 fallen (pierwszeństwo)'],
  ['stoi, górę ucina kadr / zasłania inna butelka', '1 bottle (nie zgadujemy)'],
  ['samo tło (sesja empty), nakrętka na blacie', 'bez ramek'],
]);
p('Ramka ciasno na widocznej części butelki, bez marginesu tła. Przy przezroczystych butelkach SAM łapie tło – poprawiaj uchwytami albo rysuj ręcznie (V). Butelka ucięta przez kadr: etykietuj, jeśli widać ≥ 1/3.');
bullet('Kontrola: filtr Annotations → Unannotated = 15 zdjęć (tylko empty). Liczniki na platformie odświeżają się z opóźnieniem.');
p('Eksport: ikona ⬇ obok New Model → plik NDJSON (opis zbioru + rekord na zdjęcie: nazwa, podział, ramki, link ważny 7 dni).');
step('LAPTOP', 'Folder na eksport', 'mkdir data\\export', 'Zapisz plik jako data\\export\\linesight.ndjson.');
step('LAPTOP', 'Kontrola + foldery YOLO', 'python training\\prepare_dataset.py data\\export\\linesight.ndjson', 'Raport: liczby na część i klasę, zgodność z split_v1.csv, zapomniane etykiety; na końcu „Do treningu: data=...\\data.yaml”. W folderach pliki mają nazwy hash – oryginalne nazwy są w NDJSON.');
table([1300, 1300, 1500, 1600, 1900, 2038], [
  ['Część', 'Zdjęcia', 'Z ramkami', 'bottle', 'missing_cap', 'fallen'],
  ['train', '150', '140', '213', '72', '89'],
  ['val', '43', '40', '58', '25', '27'],
  ['test', '21', '19', '29', '10', '13'],
  ['razem', '214', '199', '300', '107', '129'],
]);

h1('10e. Trening i ocena modelu (E1-06)');
step('LAPTOP', 'Trening + ocena best.pt na val i raz na test', 'python training\\train.py', 'Ok. 4 min. Early stopping: 30 epok bez poprawy (patience=30) – stanęło po 81/100, best.pt = epoka 51. Wynik: runs\\detect\\yolo26n_v1\\ (folder runs\\ poza Gitem).');
step('LAPTOP', 'Analiza: próg conf, błędy TP/FP/FN, mapy aktywacji', 'python training\\evaluate.py', 'Cały raport w konsoli i w runs\\detect\\yolo26n_v1\\analysis\\report.md.');
step('LAPTOP', 'Podgląd wykresów', ['cd runs\\detect\\yolo26n_v1', 'start results.png', 'start analysis\\val_errors\\confusion_matrix.png', 'explorer analysis\\cam'], 'Wracasz: cd ..\\..\\..');
table([2400, 1500, 1500, 1500, 2638], [
  ['Zbiór', 'P', 'R', 'mAP50', 'mAP50-95'],
  ['val (43 zdjęcia)', '0,983', '1,000', '0,995', '0,788'],
  ['test (21 zdjęć)', '0,965', '0,989', '0,987', '0,778'],
]);
table([3000, 6538], [
  ['Plik', 'Co z niego czytam'],
  ['results.png', 'straty val spadają razem z train → brak przeuczenia; mAP50 ~0,99 od 20. epoki'],
  ['labels.jpg', 'liczby ramek na klasę; butelki w jednym pasie, x 0,3–1,0'],
  ['val_errors\\confusion_matrix.png', 'macierz przy conf 0,48: 0 pomyłek klas, 0 przeoczeń, 1 FP'],
  ['val_metrics\\confusion_matrix_normalized.png', 'kolumna background = udział klas wśród FP (suma 1), nie odsetek FP'],
  ['analysis\\val_errors\\visualizations\\', 'GT / TP / FP / FN dla każdego zdjęcia'],
  ['analysis\\cam\\*_cam.jpg', 'mapy aktywacji: patrzy na butelki, nie na kaloryfer'],
]);
bullet('Próg do wdrożenia: conf = 0,48 (maks. F1 na val). Do eksportu: best.pt.');
bullet('Ograniczenie: dokładność ramek (mAP50-95), nie wykrywanie.');
bullet('Jedyny błąd: szyjka ucięta górną krawędzią kadru → dwie ramki (missing_cap + bottle). W etapie 2 kadr z zapasem nad szyjkami.');
bullet('Puste stanowisko: słaba aktywacja na żebrach kaloryfera przy prawej krawędzi (pod progiem). Sprawdzić przy INT8 (E1-08) i na wideo.');

h1('10f. Eksport ONNX i silniki TensorRT (E1-07)');
step('LAPTOP', 'Eksport best.pt do ONNX (opset 13): 640x640 i 384x640', 'python training\\export_onnx.py', 'Wynik: models\\yolo26n_v1_640x640.onnx [1,7,8400] i yolo26n_v1_384x640.onnx [1,7,5040]. 384 = kamera 360 zaokrąglona do wielokrotności 32 → −41% obliczeń.');
step('SSH1', 'Pobranie skryptów, folder na modele', 'cd ~/linesight && git pull && mkdir -p models');
step('LAPTOP', 'Kopiowanie ONNX na Jetsona', 'scp models\\yolo26n_v1_640x640.onnx models\\yolo26n_v1_384x640.onnx grzegorz@192.168.0.124:~/linesight/models/');
step('SSH1', 'Budowa 4 silników w tle (FP32/FP16 × 2 rozmiary, ok. 40 min)', ['nohup bash jetson/build_engines.sh > models/build_all.log 2>&1 &', 'tail -f models/build_all.log'], 'nohup … & = proces w tle, przeżyje zerwanie SSH i wyłączenie laptopa. Ctrl+C wychodzi tylko z podglądu. Po ponownym logowaniu: cat models/build_all.log.');
step('SSH1', 'Czekanie na zadanie w tle', 'wait %1', 'Terminal stoi, aż skończy się zadanie nr 1 z listy jobs.');
step('SSH1', 'Test INT8 (tylko pomiar, bez zapisu silnika)', ['cd ~/linesight/models', '/usr/src/tensorrt/bin/trtexec --onnx=yolo26n_v1_384x640.onnx --int8 --workspace=1024 > int8_test.log 2>&1', 'grep -iE "int8|warn|Throughput" int8_test.log'], 'Wynik: „Int8 support requested on hardware without native Int8 support”, 27 qps = jak FP32. Nano (Maxwell) nie ma sprzętowego INT8.');

h1('10g. Benchmark i dokładność silników (E1-08)');
p('Komendy z sudo wpisuj osobno – pytanie o hasło „zjada” kolejne wklejone linie.');
step('SSH1', 'Benchmark 4 silników przy stałych zegarach', 'bash jetson/bench_engines.sh', 'jetson_clocks + trtexec --loadEngine --warmUp=2000 --duration=20 --useSpinWait + tegrastats. Logi: models/bench_<data>/.');
step('SSH1', 'Pamięć silników i obciążenie GPU', ['grep -h "MemUsageChange" models/bench_*/*.log | grep -iE "deserial|ExecutionContext"', 'grep -o "RAM [0-9]*" models/bench_*/tegrastats.log | sort -k2 -n | tail -1', 'grep -o "GR3D_FREQ [0-9]*%" models/bench_*/tegrastats.log | sort | uniq -c | sort -rn | head -3']);
step('SSH1', 'Profil warstw (czas każdej warstwy)', ['sudo jetson_clocks', 'cd ~/linesight/models', 'for p in fp16 fp32; do /usr/src/tensorrt/bin/trtexec --loadEngine=yolo26n_v1_384x640_$p.engine --warmUp=2000 --duration=10 --dumpProfile --separateProfileRun > profile_$p.log 2>&1; done', 'sudo jetson_clocks --restore', 'grep -A 12 "Layer   Time" profile_fp16.log | head -14']);
step('LAPTOP', 'Zdjęcia val i test na Jetsona', ['ssh grzegorz@192.168.0.124 "mkdir -p ~/linesight/data/eval"', 'scp -r data\\datasets\\linesight-5b628dbc\\images\\val data\\datasets\\linesight-5b628dbc\\images\\test grzegorz@192.168.0.124:~/linesight/data/eval/']);
step('SSH1', 'Surowe wyjścia silników (Python 3.6, bez pycuda)', 'for p in fp16 fp32; do for s in val test; do python3 jetson/trt_dump.py models/yolo26n_v1_384x640_$p.engine data/eval/$s models/out_384x640_${p}_$s.npz; done; done');
step('LAPTOP', 'mAP silników vs ONNX (aktywne .venv!)', ['.venv\\Scripts\\activate', 'scp grzegorz@192.168.0.124:~/linesight/models/out_384x640_*.npz models\\', 'python training\\eval_trt.py'], 'Bez (.venv) w znaku zachęty Python bierze globalne, starsze ultralytics → „No module named ultralytics.utils.nms”.');
table([3600, 1500, 1500, 1500, 1438], [
  ['Silnik (Jetson, stałe zegary)', 'FPS', 'GPU ms', 'Pamięć', 'val mAP50-95'],
  ['384x640 FP16, workspace 2048', '34,4', '28,8', '20 MiB', '0,771'],
  ['384x640 FP16, workspace 1024', '33,9', '29,2', '20 MiB', '0,771'],
  ['384x640 FP32', '27,4', '36,1', '33 MiB', '0,776'],
  ['640x640 FP16', '21,1', '46,9', '27 MiB', '–'],
  ['640x640 FP32', '16,1', '61,5', '42 MiB', '–'],
]);
bullet('Wdrażamy: 384x640 FP16, workspace 2048, głowica z NMS, conf 0,45.');
bullet('FP16 = 1,23x, nie 2x: sploty to 71% czasu (Amdahl), FP16 dodaje 25 warstw Reformatting i wolniejsze SiLU.');
bullet('Głowica end-to-end (bez NMS) nie przechodzi przez TRT 8.2: operator Mod (export_onnx.py --e2e).');
bullet('Przygotowanie zdjęcia w Pythonie na CPU: 12–15 ms → w etapie 2 na GPU (DeepStream).');

h1('10h. DeepStream 6.0.1 i pyds (E2-01)');
p('Jednorazowo. DeepStream 6.0.1 = jedyna wersja dla JetPack 4.6.1.');
step('SSH1', 'Zależności GStreamera', ['sudo apt update', 'sudo apt install -y libssl1.0.0 libgstreamer1.0-0 gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav libgstrtspserver-1.0-0 libjansson4=2.11-1']);
step('SSH1', 'DeepStream 6.0.1', ['sudo apt install -y deepstream-6.0', 'dpkg -l deepstream-6.0', 'gst-inspect-1.0 nvinfer | head -20'], 'Oczekiwane: 6.0.1-1, Version 6.0.1. Zajmuje ok. 0,9 GB.');
step('SSH1', 'pyds 1.1.1 (bez zależności – PyGObject z apt)', [
  'sudo apt install -y python3-gi python3-dev python3-gst-1.0 python3-pip',
  'cd ~ && wget https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/releases/download/v1.1.1/pyds-1.1.1-py3-none-linux_aarch64.whl',
  'pip3 install --user --no-deps ./pyds-1.1.1-py3-none-linux_aarch64.whl',
  'python3 -c "import pyds; print(pyds.__file__)"',
]);
step('SSH1', 'RTSP w Pythonie (E2-05)', 'sudo apt-get install -y gir1.2-gst-rtsp-server-1.0');

h1('10i. Parser i model w nvinfer (E2-03)');
step('SSH1', 'Budowa parsera C++', ['cd ~/linesight/deepstream/parser', 'make', 'ls -l libnvdsparse_yolo26.so']);
step('SSH1', 'Test nvinfer', ['cd ~/linesight/deepstream', 'bash test_nvinfer.sh fps'], 'bash test_nvinfer.sh mp4 → nagranie /tmp/e2-03.mp4 (Ctrl+C).');
bullet('Konfiguracja: deepstream/configs/nvinfer_yolo26.txt (letterbox symetryczny, NMS IoU 0,7, próg 0,45).');

h1('10j. Uruchomienie potoku LineSight (E2-04 – E2-06)');
p('Zawsze najpierw (po restarcie):');
step('SSH1', 'Pełna moc', ['sudo nvpmodel -m 0', 'sudo jetson_clocks'], 'sudo wklejać osobno – kolejne linie zjada pytanie o hasło.');
step('SSH1', 'Najnowszy kod', ['cd ~/linesight', 'git checkout main', 'git pull']);
step('SSH1', 'Kamera na żywo: zliczanie + RTSP + klipy', ['cd ~/linesight/deepstream', 'python3 linesight_app.py --rtsp --clips'], 'Ctrl+C kończy i wypisuje PODSUMOWANIE (liczniki, FPS).');
step('LAPTOP', 'Podgląd RTSP', '"C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe" --network-caching=50 --rtsp-tcp rtsp://192.168.0.124:8554/linesight', 'Najpierw program na Jetsonie, potem VLC.');
step('SSH2', 'Obciążenie', 'tegrastats');
h2('Inne warianty');
table([4600, 5038], [
  ['Komenda (w ~/linesight/deepstream)', 'Co robi'],
  ['python3 linesight_app.py', 'kamera, tylko zliczanie (bez wyjścia wideo)'],
  ['python3 linesight_app.py --source /tmp/raw_e204.mp4 --out /tmp/e2-04.mp4', 'nagranie testowe → MP4 z ramkami'],
  ['bash record_raw.sh /tmp/raw.mp4', 'surowe nagranie z kamery (podgląd: VLC + jetson.sdp)'],
  ['python3 linesight_app.py --rtsp --clips --clip-classes bottle,missing_cap,fallen', 'klip dla każdej klasy (test)'],
  ['python3 test_counter.py', '9 testów logiki licznika i klipów (bez Jetsona)'],
  ['cat /tmp/linesight_events.jsonl', 'zdarzenia JSON (z polem clip)'],
]);
h2('Parametry');
table([3000, 6638], [
  ['Opcja', 'Domyślnie / znaczenie'],
  ['--line 0.5', 'linia zliczania w połowie kadru'],
  ['--direction L->R', 'liczone tylko przejścia w kierunku taśmy'],
  ['--margin 20', 'histereza ±20 px'],
  ['--decide 150', 'klasa z głosowania 5 s po przecięciu'],
  ['--rtsp-port 8554 --rtsp-mount /linesight', 'adres strumienia'],
  ['--bitrate 4000000', 'H.264 4 Mbit/s, klatka I co 1 s'],
  ['--pre 10 --post 5', 'klip 10 s przed i 5 s po przecięciu'],
  ['--clips-dir ~/linesight_clips', 'katalog klipów (bufor: /dev/shm/linesight, 15 × 2 s)'],
]);

h1('10k. Klipy i bufor (E2-06)');
step('SSH2', 'Podgląd bufora kołowego', 'watch -n 1 ls -l --time-style=+%T /dev/shm/linesight', 'Ctrl+C kończy. Pliki ~1 MB, nowy co 2 s.');
step('SSH1', 'Lista i długość klipów', ['ls -lh ~/linesight_clips', 'ffprobe -v error -show_entries format=duration -of csv=p=0 ~/linesight_clips/<klip>.mp4']);
step('LAPTOP', 'Pobranie klipów', ['cd C:\\Users\\Grzesiek\\Desktop', 'scp grzegorz@192.168.0.124:~/linesight_clips/*.mp4 .']);
step('SSH1', 'Sprzątanie klipów', 'rm ~/linesight_clips/*.mp4');

h1('10l. Pomiar opóźnienia (E2-05)');
step('LAPTOP', 'Stoper', ['cd C:\\Users\\Grzesiek\\Desktop\\linesight', 'python laptop\\stoper.py'], 'Kamera na okno stopera, VLC obok, zrzut Win+Shift+S: opóźnienie = stoper − stoper w VLC.');
step('SSH1', 'Opóźnienie samego Jetsona (tracer GStreamera)', [
  'GST_TRACERS=latency GST_DEBUG=GST_TRACER:7 GST_DEBUG_FILE=/tmp/latency.log python3 linesight_app.py --rtsp',
  "grep -o 'time=(guint64)[0-9]*' /tmp/latency.log | cut -d')' -f2 | sort -n | awk '{a[NR]=$1} END {print \"n=\" NR, \"mediana=\" a[int(NR/2)]/1e6 \" ms\"}'",
]);

h1('10m. Wyniki etapu 2');
table([5200, 4438], [
  ['Pomiar', 'Wynik'],
  ['Potok na żywo (detekcja + tracker + OSD + RTSP + bufor)', '30 FPS, RAM 1873 MB, GPU 61-99%'],
  ['DeepStream vs TensorRT+Python (mAP50-95 val / test)', '0,754 / 0,760 (było 0,771 / 0,764)'],
  ['Zliczanie, test ręczny (prawda 3/2/2)', '3/2/1'],
  ['Opóźnienie od szkła do szkła (VLC, caching 50)', '~620 ms'],
  ['W tym potok na Jetsonie (tracer)', '73 ms; reszta głównie VLC'],
  ['Klip testowy', '17 s, przecięcie linii w 10. s'],
]);

h1('10n. Broker MQTT (E3-01)');
p('Mosquitto w Dockerze na laptopie. Broker tylko przekazuje wiadomości; nadawcy (Jetson, most) i odbiorcy (MQTT Explorer, ingest) znają tylko jego adres i nazwę tematu.');
step('LAPTOP', 'Obraz z kopii u Google (Docker Hub / CloudFront zrywa pobieranie: EOF)', ['docker pull mirror.gcr.io/library/eclipse-mosquitto:2.0', 'docker tag mirror.gcr.io/library/eclipse-mosquitto:2.0 eclipse-mosquitto:2.0']);
step('LAPTOP', 'Start i logi', ['docker compose -f infra/docker-compose.yml up -d', 'docker logs linesight-mosquitto'], 'Oczekiwane: „mosquitto version 2.0.x running”. Linia „chown: … Read-only file system” jest niegroźna.');
step('SSH1', 'Czy Jetson widzi brokera', 'nc -zv 192.168.0.203 1883', 'Oczekiwane: „succeeded!”. Brak odpowiedzi = Zapora Windows.');
step('LAPTOP', 'Podgląd wiadomości', 'MQTT Explorer: host localhost, port 1883, bez loginu', 'Ostatnia wartość tematu w drzewie; wszystkie wiadomości: temat → Value → History.');

h1('10o. Zdarzenia z Jetsona do MQTT (E2-07)');
step('SSH1', 'Biblioteka MQTT (raz)', 'pip3 install --user paho-mqtt==1.6.1', 'Wersja 2.x wymaga Pythona ≥ 3.7, Jetson ma 3.6.');
step('SSH1', 'Potok z wysyłką zdarzeń', 'python3 linesight_app.py --rtsp --clips --mqtt 192.168.0.203', 'Oczekiwane: „MQTT: połączono”. Tematy: linesight/vision/events (QoS 1), linesight/vision/status (online/offline, Last Will).');
p('Pola zdarzenia: t (ustalenie klasy), t_cross (przecięcie linii, ok. 5 s wcześniej), track_id, class, direction, votes, clip (tylko missing_cap i fallen).');

h1('10p. Zegary (E3-02)');
step('LAPTOP', 'Pomiar zegara Windows', 'python tools\\clock_offset.py');
step('LAPTOP', 'Pomiar zegara kontenera (to nim most znakuje sygnały PLC)', 'docker run --rm -v "%cd%\\tools:/t" linesight-bridge python /t/clock_offset.py');
step('SSH1', 'Pomiar zegara Jetsona', ['timedatectl status', 'python3 ~/linesight/tools/clock_offset.py'], 'Oczekiwane: „System clock synchronized: yes”.');
step('ADMIN', 'Naprawa zegara Windows (gdy offset > 50 ms) – komendy pojedynczo', [
  'sc config w32time start= auto',
  'w32tm /config /manualpeerlist:time.google.com /syncfromflags:manual /update',
  'reg add HKLM\\SYSTEM\\CurrentControlSet\\Services\\W32Time\\Config /v MaxAllowedPhaseOffset /t REG_DWORD /d 1 /f',
  'net stop w32time && net start w32time',
  'w32tm /resync /force',
  'w32tm /query /status',
], 'MaxAllowedPhaseOffset = 1: przy błędzie > 1 s zegar jest przestawiany od razu (domyślnie poza domeną 300 s – tylko powolne dociąganie).');
table([4000, 5638], [
  ['Pomiar 14.11.2026', 'Offset'],
  ['Laptop przed naprawą', '−384 ms rano, −1042 ms po południu (usługa czasu wyłączona, potem nieskuteczna)'],
  ['Laptop (Windows) po naprawie', '+1,8 ms'],
  ['Kontener Dockera (WSL2)', '+6,5 ms'],
  ['Jetson', '−1,1 ms (wcześniej +13 ms)'],
]);

h1('10q. Sterownik: maszyna stanów PackML (E3-03)');
p('Kod w repo: plc/src/E_PackML.st (DUT), GVL_Line.st (GVL), PLC_PRG.st (program). Do projektu CODESYS wklejany ręcznie.');
step('PLC', 'Wgranie i start', ['Build → Generate code (F11)', 'Online → Login (Alt+F8), Debug → Start (F5)']);
step('PLC', 'Zmiana wartości online', 'GVL_Line: kolumna „Prepared value” → Ctrl+F7 (Write values)', 'Komendy xCmd… działają na zbocze – po użyciu ustaw z powrotem FALSE.');
step('PLC', 'Interwał zadania (raz)', 'Task Configuration → MainTask → Interval: t#10ms', 'Przy 200 ms timer cyklu był kwantowany: 2,0 s na sztukę (30/min) zamiast 1,5 s. Czas cyklu jest mierzony TIME().');
table([1600, 2400, 5638], [
  ['iStateCurrent', 'Stan', 'Znaczenie'],
  ['2', 'Stopped', 'zatrzymana'], ['15', 'Resetting', 'przygotowanie (1 s)'], ['4', 'Idle', 'gotowa, czeka na start'],
  ['3', 'Starting', 'rusza (1 s)'], ['6', 'Execute', 'produkuje (sztuka co ok. 1,5 s)'], ['11', 'Held', 'zator (iStopReason 101)'],
  ['5', 'Suspended', 'brak produktu (201)'], ['8 / 9', 'Aborting / Aborted', 'awaria (301), abort operatora (302)'],
  ['7', 'Stopping', 'zatrzymywanie (stop operatora: 1)'], ['1', 'Clearing', 'kasowanie awarii (1 s)'],
]);
table([3000, 6638], [
  ['Zmienna', 'Działanie'],
  ['xCmdReset / xCmdStart / xCmdStop', 'Stopped → Idle; Idle → Execute; stop z Idle/Execute/Held/Suspended'],
  ['xCmdAbort / xCmdClear', 'awaria z dowolnego stanu; Aborted → Stopped (gdy xInjFault = FALSE)'],
  ['xInjJam', 'zator → Held (101), po wyłączeniu powrót do Execute'],
  ['xInjNoProduct', 'brak produktu → Suspended (201)'],
  ['xInjFault', 'awaria → Aborted (301)'],
  ['xInjSlow', 'czas cyklu +40 % (dane do wykrywania anomalii)'],
]);

h1('10r. OPC UA i most do MQTT (E3-04, E3-05)');
step('PLC', 'Serwer OPC UA (raz)', ['Application → Add Object → Symbol Configuration, zaznacz „Support OPC UA features”', 'Build w edytorze symboli, zaznacz całe GVL_Line', 'Login (wgranie), Start']);
step('LAPTOP', 'Lista zmiennych z laptopa (aktywne .venv)', ['.venv\\Scripts\\activate', 'pip install asyncua', 'python tools\\opcua_browse.py'], 'Oczekiwane: „Znaleziono zmiennych: 15”, NodeId ns=4;s=|var|JUMO ARM Cortex A7 Linux iMX6ULL ARM32.Application.GVL_Line.<nazwa>.');
step('LAPTOP', 'Most (usługa bridge) – start i logi', ['docker compose -f infra/docker-compose.yml up -d --build', 'docker logs linesight-bridge'], 'Oczekiwane: „OPC UA: połączono … subskrypcja 9 zmiennych co 200 ms”. Tematy linesight/plc/<zmienna>, treść {"t", "value", "t_src"}.');
p('Most subskrybuje zmiany (serwer sam zgłasza nową wartość), czas t nadaje most (zegar laptopa/kontenera). Zegar sterownika różni się o ok. 1,2 s (t − t_src). Bez sterownika: status offline, ponowna próba co 5 s.');

h1('10s. TimescaleDB i zapis z MQTT (E3-06)');
step('LAPTOP', 'Obraz bazy z kopii u Google', ['docker pull mirror.gcr.io/timescale/timescaledb:2.25.2-pg17', 'docker tag mirror.gcr.io/timescale/timescaledb:2.25.2-pg17 timescale/timescaledb:2.25.2-pg17']);
step('LAPTOP', 'Logi zapisu', 'docker logs linesight-ingest', 'Oczekiwane: „MQTT: połączono (kod Success)” i „DB: połączono”.');
step('LAPTOP', 'Sygnały PLC w bazie', 'docker exec linesight-db psql -U linesight -c "select name, count(*), max(value) from plc_signal group by name order by name;"');
step('LAPTOP', 'Sygnały z 30 s przed chwilą', 'docker exec linesight-db psql -U linesight -c "select * from signals_before(now()) where name <> \'udiProdProcessed\';"', 'Pierwsze wiersze (jednakowy, najstarszy czas) = wartość każdej zmiennej na początku okna.');
step('LAPTOP', 'Zdarzenia z kamery', 'docker exec linesight-db psql -U linesight -c "select time, class, track_id, clip from vision_event order by time desc limit 3;"');
step('LAPTOP', 'Stan linii w chwili ostatniego zdarzenia z kamery', 'docker exec linesight-db psql -U linesight -c "select s.* from signals_before((select max(time) from vision_event)) s where name in (\'iStateCurrent\',\'iStopReason\',\'xInjJam\');"');
table([2600, 7038], [
  ['Tabela', 'Zawartość'],
  ['plc_signal', 'jedna zmiana jednej zmiennej: time, name, value (BOOL = 0/1), t_src'],
  ['vision_event', 'przecięcia linii: time = t_cross, t_decided, track_id, class, clip, votes, raw'],
  ['link_status', 'online/offline mostu (plc) i kamery (vision)'],
]);
p('Czasy w bazie są w UTC (+00); 16:26 w bazie = 17:26 czasu polskiego. Brak wiersza w plc_signal znaczy „bez zmian”, a nie „brak danych”.');

h1('10t. Grafana (E3-07)');
step('LAPTOP', 'Użytkownik tylko do odczytu (raz, na istniejącej bazie)', 'docker exec -i linesight-db psql -U linesight < infra\\db\\20-grafana-ro.sql');
step('LAPTOP', 'Obraz Grafany i start', ['docker pull mirror.gcr.io/grafana/grafana:13.2.4', 'docker tag mirror.gcr.io/grafana/grafana:13.2.4 grafana/grafana:13.2.4', 'docker compose -f infra/docker-compose.yml up -d']);
step('WWW', 'Dashboard „LineSight – linia”', 'http://localhost:3000', 'admin / linesight. Źródło danych i dashboard z plików w infra/grafana (zmiany w przeglądarce nie zapisują się do repo).');

h1('11. Jednorazowa konfiguracja Jetsona (etap 0)');
p('Już zrobione. Tylko przy nowej karcie SD.');
step('SSH1', 'Plik wymiany 4 GB', [
  'sudo fallocate -l 4G /swapfile',
  'sudo chmod 600 /swapfile',
  'sudo mkswap /swapfile',
  'sudo swapon /swapfile',
  "echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab",
]);
step('SSH1', 'Start bez pulpitu (oszczędza ok. 1,3 GB RAM)', ['sudo systemctl set-default multi-user.target', 'sudo reboot'], 'Powrót do pulpitu: sudo systemctl set-default graphical.target');
step('SSH1', 'Narzędzia do kamer', ['sudo apt update', 'sudo apt install -y v4l-utils']);

h1('12. Problemy i rozwiązania');
table([3600, 3000, 3038], [
  ['Objaw', 'Przyczyna', 'Rozwiązanie'],
  ['Device \'/dev/video0\' is busy', 'Inny gst-launch trzyma kamerę (np. okno zamknięte bez Ctrl+C)', 'pkill gst-launch, kontrola: sudo fuser -v /dev/video0'],
  ['kill PID → „arguments must be process or job IDs”', 'Wpisane słowo PID zamiast liczby', 'kill 7532 (liczba z fuser)'],
  ['VLC: „nie może otworzyć MRL ... jetson.sdp”', 'Plik ma 0 bajtów (Notatnik nie zapisał treści)', 'Utworzyć plik blokiem echo z punktu 7'],
  ['„System nie może odnaleźć pliku ... vlc.exe”', 'VLC 32-bit jest w Program Files (x86)', 'Ścieżka z punktu 7'],
  ['scp: No such file or directory', 'Zdjęcie nie powstało (kamera była zajęta)', 'Zwolnić kamerę, zrobić zdjęcie, ls -l, potem scp'],
  ['12 FPS zamiast 30 (RealSense)', 'Ekspozycja 80 ms > 33 ms na klatkę', 'exposure_absolute < 333 (jednostki 100 µs)'],
  ['Obraz rozmyty w całości', 'Ostrość obiektywu', 'Pierścień ostrości, potem zablokować'],
  ['Ciemna sylwetka butelki', 'Scena pod światło', 'Światło od przodu, okno poza kadrem'],
  ['git push → 403', 'Windows pamięta inne konto GitHub', 'cmdkey /delete:git:https://github.com'],
  ['git pull → „untracked working tree files would be overwritten” + Aborting', 'Lokalny nieśledzony plik o tej samej nazwie co plik w repo', 'Gdy to ta sama treść: del plik, potem git pull'],
  ['git: \'switch\' is not a git command (Jetson)', 'Git 2.17 na Ubuntu 18.04', 'git checkout main'],
  ['VLC pokazuje pachołek, bez obrazu', 'VLC uruchomiony przed nadawaniem – po kilku s bez danych się zatrzymał', 'Najpierw skrypt na Jetsonie, potem ▶ w VLC'],
  ['scp: mkdir ... Invalid argument', 'Ścieżka docelowa kończy się \\" – Windows psuje cudzysłów', 'Usunąć \\ z końca ścieżki'],
  ['pip: Operation cancelled by user', 'Wklejony blok komend – kolejne linie przerwały pip', 'Długie komendy wklejać pojedynczo'],
  ['No module named torch', 'PyTorch się nie zainstalował albo .venv nie jest włączone', '.venv\\Scripts\\activate, potem instalacja'],
  ['sudo: „Sorry, try again” po wklejeniu kilku linii', 'Kolejne linie wzięte jako hasło', 'sudo … wklejać osobno'],
  ['git checkout: pathspec \'etap2/…\' did not match', 'Jetson nie zna nowej gałęzi', 'git fetch, potem git checkout'],
  ['git status „up to date”, a brak zmian', 'Porównanie ze starym stanem origin', 'git pull (pobiera i scala)'],
  ['unrecognized arguments: --rtsp', 'Stara wersja kodu (main sprzed scalenia)', 'git pull na właściwej gałęzi'],
  ['VLC: nie mógł połączyć się z …:8554', 'Program na Jetsonie nie działa', 'Najpierw linesight_app.py --rtsp'],
  ['Ostrzeżenie GstUDPSrc has no property named \'pt\'', 'Serwer RTSP ustawia typ ładunku na udpsrc', 'Nieszkodliwe, ignorować'],
  ['scp: ~/linesight_clips/*.mp4: No such file', 'Brak klipów – zwykła bottle nie zapisuje klipu', 'Test z --clip-classes bottle,missing_cap,fallen'],
  ['docker pull / compose: „failed to copy … cloudfront … EOF”', 'Sieć laptopa zrywa pobieranie z CloudFront (Docker Hub)', 'docker pull mirror.gcr.io/…, potem docker tag; albo hotspot z telefonu'],
  ['„System nie może odnaleźć określonej ścieżki” (vlc.exe)', 'VLC jest w Program Files (x86)', '"C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe"'],
  ['w32tm: „Usługa nie została uruchomiona (0x80070426)”', 'Usługa czasu Windows wyłączona', 'Punkt 10p: sc config w32time start= auto, net start w32time'],
  ['Offset zegara laptopa się nie zmienia po resync', 'Domyślny próg skoku 300 s – zegar tylko powoli dociągany', 'Punkt 10p: MaxAllowedPhaseOffset = 1'],
  ['MQTT Explorer: brak stanów 15 i 3', 'Drzewo pokazuje tylko ostatnią wartość', 'Temat → Value → History'],
  ['Grafana: „< 80” zamiast nazw stanów', 'Mapowania nie zadziałały, użyte domyślne progi', 'Poprawione w dashboardzie; po zmianie pliku: F5 w przeglądarce'],
  ['Grafana: 30 szt./min zamiast 40', 'Stary program PLC / MainTask 200 ms', 'Program z plc/src, MainTask t#10ms'],
  ['Komendy cmd sklejone w jedną linię', 'Wklejony blok bez Entera', 'Wklejać pojedynczo'],
]);

h1('Archiwum: Intel RealSense (etap 0, niewykorzystana)');
p('RealSense 8086:0b48, RGB = /dev/video0, 640x480 YUYV 30 FPS. Zastąpiona kamerą ASUS w E1-01 (lepsza jasność sceny).');
step('SSH1', 'Ręczna ekspozycja 20 ms', 'v4l2-ctl -d /dev/video0 -c exposure_auto=1 -c exposure_absolute=200 -c gain=64');

// ---------- DOC ----------
const doc = new Document({
  creator: 'Grzegorz', title: 'LineSight – ściąga',
  styles: {
    default: { document: { run: { font: FONT, size: 20 } } },
    paragraphStyles: [
      { id: 'Title', name: 'Title', basedOn: 'Normal', run: { font: FONT, size: 40, bold: true, color: '1F4E8C' }, paragraph: { spacing: { before: 0, after: 120 } } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 28, bold: true, color: '1F4E8C' }, paragraph: { spacing: { before: 300, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: FONT, size: 24, bold: true }, paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '\u2022', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 260 } } } }] }] },

  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'LineSight – ściąga · strona ', size: 16, color: '888888' }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '888888' })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(process.argv[2], b); console.log('written'); });
