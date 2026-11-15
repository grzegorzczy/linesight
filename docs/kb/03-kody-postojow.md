# Kody przyczyn postoju (iStopReason)

## Lista kodów
Kod przyczyny postoju to sygnał `iStopReason` (PackTag Admin.StopReason.ID): 0 – brak postoju, 1 – stop operatora, 101 – zator, 201 – brak produktu, 301 – awaria, 302 – abort operatora (wyłącznik awaryjny). Kod jest ustawiany w chwili wyjścia ze stanu Execute i kasowany do 0 przy powrocie do Execute z Held lub Suspended, w stanie Resetting oraz na końcu Clearing.

## Kod 101 – zator
Kod 101 oznacza zator w maszynie: najczęściej przewrócona butelka blokuje taśmę. Stan linii: Held (11). Przyczyna w diagnostyce: `zator`. Kamera potwierdza zator, gdy w oknie przed postojem widziała obiekt klasy `fallen` (przewrócona butelka) – wtedy pewność to `potwierdzona`, a do postoju dołączany jest klip z przewróconą butelką. Linia wraca do pracy sama po usunięciu zatoru. Procedura: patrz „Procedura – zator (kod 101)”.

## Kod 201 – brak produktu
Kod 201 oznacza brak produktu na wejściu linii (przyczyna zewnętrzna, np. pusty podajnik). Stan linii: Suspended (5). Przyczyna w diagnostyce: `brak_produktu`. Kamera potwierdza brak produktu, gdy przez co najmniej 10 s przed postojem nie przeszła żadna butelka. Jeśli kamera widziała butelkę krócej niż 10 s przed postojem, pewność to `sprzeczna` – czujnik produktu mógł dać fałszywy sygnał. Linia wraca do pracy sama, gdy produkt wróci.

## Kod 301 – awaria
Kod 301 oznacza awarię maszyny, np. napędu taśmy. Stan linii: Aborting (8), potem Aborted (9). Przyczyna w diagnostyce: `awaria`. Kamera nie potwierdza awarii, więc pewność to `tylko_plc`. Wyjście z Aborted wymaga usunięcia awarii i komendy Clear, potem Reset i Start. Przed postojem z kodem 301 warto sprawdzić kondycję napędu (moment, prąd, temperatura).

## Kod 302 – abort operatora
Kod 302 oznacza, że operator użył komendy Abort (wyłącznik awaryjny), a nie że wystąpiła awaria. Stan linii: Aborting (8), potem Aborted (9). Przyczyna w diagnostyce: `awaria` (ta sama kategoria co 301, rozróżnienie po kodzie). Po wyjaśnieniu powodu zatrzymania: Clear, Reset, Start.

## Kod 1 – stop operatora
Kod 1 oznacza planowe zatrzymanie linii komendą Stop. Stan linii: Stopping (7), potem Stopped (2). Przyczyna w diagnostyce: `operator`. To nie jest awaria. Ponowne uruchomienie: Reset, Start.

## Brak kodu – restart sterownika
Postój ze stanem 0 albo innym numerem spoza listy stanów PackML oznacza restart sterownika lub wgranie programu (zmienne wyzerowane). Przyczyna w diagnostyce: `restart_plc`, pewność `tylko_plc`. Licznik sztuk może wtedy wrócić do zera.
