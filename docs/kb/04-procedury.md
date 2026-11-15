# Procedury postępowania przy postojach

## Procedura – zator (kod 101)
1. Obejrzyj klip dołączony do postoju albo podgląd kamery (RTSP), aby zlokalizować przewróconą butelkę.
2. Usuń przewróconą butelkę z taśmy; nie sięgaj do pracującej taśmy – linia w stanie Held (11) stoi.
3. Sprawdź prowadnice boczne, czy nie są rozregulowane – częste zatory z butelkami `fallen` w tym samym miejscu kadru wskazują na prowadnice albo zbyt duży odstęp między butelkami.
4. Po usunięciu zatoru linia sama wraca do Execute.
Jeśli zatory powtarzają się kilka razy w ciągu godziny, zgłoś to jako problem mechaniczny, nie operatorski.

## Procedura – brak produktu (kod 201)
1. Sprawdź podajnik na wejściu linii – czy są butelki.
2. Jeśli pewność postoju to `sprzeczna` (kamera widziała butelki tuż przed postojem), sprawdź czujnik obecności produktu: zabrudzenie, ustawienie, przewód.
3. Uzupełnij produkt; linia sama wraca ze Suspended (5) do Execute.
Długie postoje z kodem 201 to strata organizacyjna (logistyka podawania), nie usterka maszyny.

## Procedura – awaria (kod 301)
1. Sprawdź kondycję napędu w Grafanie (panel kondycji, moment, prąd, temperatura) z okresu przed postojem.
2. Usuń przyczynę awarii; dopóki awaria trwa, komenda Clear nie działa.
3. Komenda Clear: Aborted (9) → Clearing (1) → Stopped (2).
4. Komenda Reset, potem Start.
5. Pierwsze minuty po dłuższym postoju napęd pracuje na zimno – wyższy moment (do +12 %) jest wtedy normalny.

## Procedura – abort operatora (kod 302) i stop operatora (kod 1)
Kod 302: ustal, dlaczego użyto wyłącznika awaryjnego, usuń zagrożenie, potem Clear, Reset, Start. Kod 1: zatrzymanie planowe; uruchomienie przez Reset i Start. Oba kody nie oznaczają usterki maszyny, ale postój wlicza się do strat dostępności.

## Procedura – restart sterownika
Po restarcie sterownika (postój z przyczyną `restart_plc`) linia jest w stanie Stopped albo w stanie 0. Sprawdź, czy most OPC UA → MQTT ma status `online`, potem Reset i Start. Licznik `udiProdProcessed` po wgraniu programu zaczyna od zera – zestawienia sztuk z okresu restartu trzeba czytać ostrożnie.

## Gdy kamera była offline
Jeśli w dowodach postoju jest „kamera offline w oknie”, brak zdarzeń z kamery niczego nie dowodzi: pewność postoju to `tylko_plc`. Przed kolejnym użyciem uruchom na Jetsonie aplikację kamery (`linesight_app.py --rtsp --clips --mqtt 192.168.0.203`) i serwer klipów (`serve_clips.py`, port 8080).
