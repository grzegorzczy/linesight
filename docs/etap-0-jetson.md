# Etap 0 – Jetson: dostęp, inwentaryzacja, kamera

Status: w trakcie (10.11.2026)

## Cel etapu
Przygotować Jetsona Nano do pracy: zdalny dostęp, znany stan systemu,
działająca kamera RGB, struktura repozytorium i backlog MVP.

Wymagania z ogłoszenia: praca w Linuksie, platformy NVIDIA Edge (Jetson),
przetwarzanie strumieni wideo.

## 1. Dostęp przez SSH

SSH (Secure Shell) to szyfrowane zdalne logowanie do terminala. Pracujemy
z laptopa, żeby kopiować wyjście komend jako tekst. Monitor i klawiatura
zostają podpięte do Jetsona jako awaryjny dostęp.

| Komenda | Urządzenie | Do czego służy |
|---|---|---|
| `systemctl status ssh` | Jetson | Czy działa serwer SSH (oczekiwane: `active (running)`) |
| `hostname -I` | Jetson | Adresy IP Jetsona w sieci lokalnej |
| `whoami` | Jetson | Nazwa zalogowanego użytkownika |
| `ssh grzegorz@192.168.0.124` | Laptop (PowerShell) | Logowanie do Jetsona; przy pierwszym połączeniu akceptujemy klucz hosta (`yes`) |

Wynik:
- Serwer SSH działał od startu systemu, nasłuch na porcie 22.
- IP Jetsona: `192.168.0.124`. Adres `172.17.0.1` to sieć wewnętrzna Dockera,
  więc Docker jest już zainstalowany (przychodzi z JetPackiem).
- Nie używamy rozszerzenia Remote-SSH z VS Code: nowsze wersje wymagają
  nowszej biblioteki systemowej niż ta w Ubuntu 18.04.
- Nie uruchamiamy `apt upgrade`: aktualizacja pakietów NVIDII może zepsuć
  zgodność z JetPack 4.6.1 i zapchać kartę.

## 2. Inwentaryzacja Jetsona

Te komendy tylko odczytują stan systemu.

| Komenda | Do czego służy |
|---|---|
| `cat /etc/nv_tegra_release` | Wersja L4T (system NVIDII dla Jetsona); od niej zależą wersje bibliotek |
| `lsusb` | Urządzenia USB z identyfikatorami producent:model |
| `lsblk` | Dyski, partycje i urządzenia swap |
| `df -h /` | Zajętość partycji systemowej |
| `free -h` | RAM i swap |
| `dpkg -l \| grep -E "nvidia-jetpack\|deepstream\|tensorrt"` | Czy zainstalowane są JetPack, DeepStream, TensorRT i w jakiej wersji |
| `ls /dev/video*` | Urządzenia wideo widoczne przez V4L2 (linuksowy interfejs kamer) |

Wyniki:

| Co | Wynik | Wniosek |
|---|---|---|
| System | L4T R32 rev 7.1 (JetPack 4.6.1), Ubuntu 18.04.6, jądro 4.9.253-tegra | Zgodnie z założeniami |
| TensorRT | 8.2.1.8, CUDA 10.2 | Zainstalowany, nic nie dokładamy |
| DeepStream | brak | Instalacja w etapie 2 (wersja 6.0) |
| Dysk | karta SD 29 GB, 12 GB zajęte, 16 GB wolne | Wystarczy na MVP; zero treningu i zbiorów danych na Jetsonie |
| RAM | 3,9 GB, ok. 2,1 GB dostępne | Pulpit graficzny zajmuje sporo pamięci |
| Swap | 1,9 GB, wyłącznie zram (4 x 495 MB) | Za mało na budowę silnika TensorRT; dodamy plik wymiany |
| Kamera | Intel `8086:0b48`, USB 3.0; `/dev/video0`, `/dev/video1` | Model do potwierdzenia w kroku 3 |

Pojęcia:
- **zram** – swap trzymany w RAM w postaci skompresowanej; nie dokłada
  pamięci fizycznej, tylko ją lepiej upycha.
- **Plik wymiany (swapfile)** – swap na dysku; wolny, ale pozwala przetrwać
  szczyty zużycia pamięci, np. przy budowie silnika TensorRT.

## 3. Identyfikacja kamery (w trakcie)

RealSense wystawia osobne urządzenia dla obrazu RGB i głębi. Ustalamy,
które `/dev/videoX` to RGB i jakie formaty, rozdzielczości i FPS oferuje.

| Komenda | Do czego służy |
|---|---|
| `sudo apt update` | Odświeża listę dostępnych pakietów (nic nie aktualizuje) |
| `sudo apt install -y v4l-utils` | Instaluje narzędzia V4L2, w tym `v4l2-ctl` |
| `v4l2-ctl --list-devices` | Nazwa kamery i przypisane do niej urządzenia |
| `v4l2-ctl -d /dev/video0 --list-formats-ext` | Formaty pikseli, rozdzielczości i FPS urządzenia |

Uwaga z praktyki: komend z `sudo` nie wklejamy hurtem razem z innymi.
`sudo` pyta o hasło, a kolejne wklejone linie trafiają do pola hasła
jako błędne próby.

Wynik:
- `v4l2-ctl --list-devices`: Intel RealSense Depth Camera na porcie USB 3.0
  (`usb-70090000.xusb`), urządzenia `/dev/video0` i `/dev/video1`.
- **`/dev/video0` to RGB**: format `YUYV 4:2:2` (nieskompresowany kolor),
  od 320x180 do 1920x1080. 1920x1080 tylko 30 FPS, od 1280x720 w dół 60/30/10 FPS.
- `/dev/video1` nie zwraca żadnych formatów obrazu – nie jest źródłem RGB,
  nie używamy go.
- Na standardowym jądrze L4T (bez łatek RealSense) obraz głębi nie jest
  dostępny przez V4L2. Projekt i tak używa tylko RGB.
- Wybór na MVP: **640x480 @ 30 FPS, YUYV**. Mieści się w wejściu modelu
  (416-640 px) bez dużego skalowania i nie obciąża CPU konwersją kolorów.

Pojęcia:
- **YUYV 4:2:2** – kolor zapisany jako jasność (Y) dla każdego piksela
  i wspólna informacja o barwie (U, V) dla par pikseli; 2 bajty na piksel.
  Model potrzebuje RGB, więc po drodze jest konwersja.

## 4. Test kamery w GStreamerze

GStreamer: `gst-launch-1.0` buduje potok z elementów połączonych `!`.
Dane płyną od źródła (`v4l2src` = kamera) do ujścia (plik, ekran, `fakesink`).
Wpis `video/x-raw,format=...,width=...` to caps – wymuszony format na łączu.

| Komenda | Urządzenie | Do czego służy |
|---|---|---|
| `gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=300 ! video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 ! fpsdisplaysink video-sink=fakesink text-overlay=false -v 2>&1 \| grep -o "current: [0-9.]*" \| tail -n 3` | Jetson | Pomiar rzeczywistego FPS kamery (300 klatek, obraz wyrzucany) |
| `gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=60 ! video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 ! videoconvert ! jpegenc ! multifilesink location=$HOME/test/frame_%02d.jpg` | Jetson | Zapis 60 klatek do JPEG (`videoconvert` YUYV→format kodera, `jpegenc` JPEG, `multifilesink` plik na klatkę) |
| `scp grzegorz@192.168.0.124:~/test/frame_59.jpg <ścieżka>` | Laptop | Kopiowanie pliku z Jetsona przez SSH |

Wynik:
- **FPS: 12 zamiast 30.** Potwierdza to czas: 60 klatek zapisało się w 5,08 s.
- Klatka (`img/etap0_pierwsza_klatka.jpg`): średnia jasność 55/255 – obraz ciemny.
- Pierwsza hipoteza (priorytet automatycznej ekspozycji) okazała się błędna:
  kamera nie ma kontrolki `exposure_auto_priority`.

### Diagnoza na podstawie kontrolek kamery

| Komenda | Do czego służy |
|---|---|
| `v4l2-ctl -d /dev/video0 --list-ctrls` | Ustawienia kamery wystawione przez sterownik UVC (standard kamer USB) |
| `v4l2-ctl -d /dev/video0 --set-ctrl=nazwa=wartość,...` | Zmiana ustawień kamery; znikają po odłączeniu kamery lub restarcie |

Stan zastany (różnice względem wartości domyślnych):
- `exposure_auto=1` – **ekspozycja ręczna** (domyślnie 3 = automatyczna)
- `exposure_absolute=800` – czas naświetlania (domyślnie 156)
- `white_balance_temperature_auto=0`, `gain=48`, `gamma=400`, `brightness=10`,
  `contrast=60`, `sharpness=70` – również zmienione względem domyślnych

**Przyczyna 12 FPS:** `exposure_absolute` w UVC jest w jednostkach 100 µs,
więc 800 = 80 ms naświetlania na klatkę. Klatka nie może trwać krócej niż
naświetlanie: 1 / 0,080 s = 12,5 FPS. Dokładnie tyle zmierzyliśmy.

Warunek dla 30 FPS: naświetlanie < 33,3 ms, czyli `exposure_absolute` < 333.
Dla przesuwanych butelek lepiej krócej (mniej rozmycia ruchu), a brak
światła nadrabiamy oświetleniem sceny, nie czasem naświetlania.

### Poprawka i ponowny pomiar

| Komenda | Do czego służy |
|---|---|
| `v4l2-ctl -d /dev/video0 --set-ctrl=exposure_auto=1,exposure_absolute=200,gain=64` | Ekspozycja ręczna 20 ms, wzmocnienie domyślne |
| `v4l2-ctl -d /dev/video0 --get-ctrl=exposure_auto,exposure_absolute,gain` | Odczyt kontrolny ustawionych wartości |

Wynik:
- **29-30 FPS** (fpsdisplaysink zaokrągla w dół), 60 klatek w 2,22 s
  (z uruchomieniem potoku). Problem rozwiązany.
- Klatka `img/etap0_klatka_30fps.jpg`: kamera skierowana na jasną ścianę,
  obiekty na pierwszym planie są w cieniu – **pod światło**. To kwestia
  ustawienia sceny, nie kamery.

Decyzja: ekspozycja ręczna, stała. W wizji przemysłowej daje powtarzalny
obraz (te same warunki na treningu i w produkcji). Automatyka zmienia
jasność, gdy w kadrze pojawi się coś jasnego lub ktoś przejdzie obok.
W etapie 2 ustawienia trafią do potoku przez `extra-controls` w `v4l2src`.

Zasady sceny (na etap 1, przed zbieraniem zdjęć):
- światło od strony kamery lub z boku, nigdy za obiektem;
- matowe, jednolite tło kontrastujące z butelkami, bez okna w kadrze;
- kamera zamocowana na sztywno, stały kadr;
- ekspozycję dostrajamy dopiero przy gotowej scenie.

## 5. Pamięć: plik wymiany i system bez pulpitu

Budowa silnika TensorRT to najbardziej pamięciożerny krok projektu.
4 GB RAM są współdzielone z GPU, a zram tylko kompresuje RAM, nie dokłada
pamięci. Dodajemy swap na karcie i zwalniamy RAM zajmowany przez pulpit.

| Komenda | Do czego służy |
|---|---|
| `sudo fallocate -l 4G /swapfile` | Rezerwuje na dysku plik 4 GB |
| `sudo chmod 600 /swapfile` | Dostęp tylko dla roota (swap może zawierać fragmenty pamięci programów) |
| `sudo mkswap /swapfile` | Formatuje plik jako obszar wymiany |
| `sudo swapon /swapfile` | Włącza swap od razu |
| `echo '/swapfile none swap sw 0 0' \| sudo tee -a /etc/fstab` | Włącza swap przy każdym starcie (`tee -a` dopisuje do pliku z uprawnieniami roota) |
| `sudo systemctl set-default multi-user.target` | Start bez środowiska graficznego; powrót: `graphical.target` |
| `sudo reboot` | Restart |
| `free -h`, `swapon --show`, `df -h /` | Kontrola RAM, aktywnych obszarów swap i miejsca na dysku |

Wynik: swap 4 GiB utworzony i włączony, domyślny cel systemd zmieniony
na `multi-user.target`. Pomiar po restarcie:

| | Przed | Po |
|---|---|---|
| RAM dostępny (`available`) | 2,1 GB | **3,4 GB** |
| RAM zajęty | 1,7 GB | 298 MB |
| Swap | 1,9 GB (zram) | 5,9 GB (zram + plik 4 GB) |
| Wolne na karcie | 16 GB | 12 GB |

- Pulpit graficzny zajmował ok. 1,3 GB RAM.
- Priorytety swapu są właściwe: zram ma priorytet 5, plik -1, więc system
  najpierw kompresuje w RAM, a na wolną kartę schodzi dopiero na końcu.
- Ustawienia kamery (`v4l2-ctl --set-ctrl`) nie przetrwały restartu –
  trzeba je ustawiać przy każdym uruchomieniu potoku (etap 2: `extra-controls`).

Kompromis: swap na karcie SD jest wolny i zużywa kartę, ale używany jest
tylko w szczytach (budowa silnika). Lepiej wolniej niż zawieszenie systemu.

## 6. Repozytorium

Folder projektu: `C:\Users\Grzesiek\Desktop\linesight`
GitHub: `github.com/grzegorzczy/linesight`

### Co jest w `.gitignore` i dlaczego

| Grupa | Wzorce | Powód |
|---|---|---|
| Prywatne | `ogloszenie.txt` | Repo jest publiczne; nie pokazujemy celowania w jedno ogłoszenie |
| Sekrety | `.env`, `*.key`, `*-credentials.json` (wyjątek: `.env.example`) | Hasła i klucze GCP nie mogą trafić na GitHuba |
| Python | `__pycache__/`, `.venv/`, `.ipynb_checkpoints/` | Pliki generowane, każdy odtworzy je u siebie |
| Modele | `*.pt`, `*.onnx`, `*.engine`, `*.trt`, `*.cache` | Duże binaria (limit GitHuba 100 MB); silnik TensorRT jest i tak specyficzny dla urządzenia i wersji TensorRT; wersje modeli trzymamy w GCP |
| Dane | `data/`, `datasets/`, `runs/`, `mlruns/` | Zbiór żyje na Ultralytics Platform i lokalnie; wyniki treningu odtwarzalne z kodu |
| Wideo i obrazy | `*.mp4`, `*.h264`, `*.jpg`, `*.png`… | Klipy i klatki są duże i liczne |
| Wyjątek | `!docs/img/**` | Obrazy do dokumentacji mają być w repo |
| Lokalne | `*.db`, `*.log`, pliki tymczasowe CODESYS, `.vscode/` | Stan lokalny, nie kod |

Wzorzec z `!` na początku przywraca plik wykluczony wcześniejszą regułą.

Problem po drodze: `git push` zwrócił 403 – Windows miał zapamiętane
poświadczenia innego konta GitHub. Rozwiązanie:

| Komenda | Do czego służy |
|---|---|
| `cmdkey /list \| findstr github` | Lista poświadczeń zapisanych w Windows dla GitHuba |
| `cmdkey /delete:git:https://github.com` | Usuwa poświadczenie używane przez Gita (wpisy `gh:` należą do GitHub CLI i zostają) |

Przy kolejnym `git push` Git Credential Manager prosi o logowanie przez przeglądarkę.

### Konwencje

- Gałąź `main` – zawsze działający stan; zmiany tylko przez PR.
- Gałąź na etap lub zadanie: `etap0/jetson-setup`, `etap1/dataset` itd.
- Commity: **Conventional Commits** – prefiks mówi o rodzaju zmiany:
  `feat:` nowa funkcja, `fix:` poprawka, `docs:` dokumentacja,
  `chore:` konfiguracja i porządki, `refactor:`, `test:`.
- README po każdym etapie: status w tabeli i link do pliku w `docs/`.
- README po angielsku (wizytówka projektu), notatki w `docs/` po polsku.

### Komendy (laptop, PowerShell, w folderze projektu)

| Komenda | Do czego służy |
|---|---|
| `git init -b main` | Nowe repozytorium z domyślną gałęzią `main` |
| `git add .gitignore` + `git commit -m "chore: add .gitignore"` | Pierwszy commit: same reguły ignorowania |
| `git remote add origin https://github.com/grzegorzczy/linesight.git` | Połączenie z repozytorium na GitHubie |
| `git push -u origin main` | Wysłanie `main`; `-u` zapamiętuje powiązanie gałęzi |
| `git switch -c etap0/jetson-setup` | Nowa gałąź i przejście na nią |
| `git status --ignored` | Kontrola: co Git śledzi, a co ignoruje |
| `git log --oneline --all --graph` | Historia wszystkich gałęzi w skrócie |

## Do zrobienia w etapie 0
- [x] Identyfikacja kamery i formatów RGB
- [x] Test obrazu z kamery (30 FPS)
- [x] Porządek na Jetsonie (swap, pamięć)
- [x] Struktura repozytorium i Git
- [x] Backlog MVP (etapy 1-3) – `docs/backlog.md`
