# Stany PackML mini linii

## Numery stanów
Linia używa podzbioru stanów PackML (ISA-TR88.00.02), numer w sygnale `iStateCurrent`: 1 Clearing, 2 Stopped, 3 Starting, 4 Idle, 5 Suspended, 6 Execute, 7 Stopping, 8 Aborting, 9 Aborted, 11 Held, 15 Resetting. Linia produkuje tylko w stanie Execute (6). Brak stanów Holding, Unholding, Suspending, Unsuspending, Completing i Complete. Stan 0 nie jest stanem PackML – pojawia się po wgraniu programu lub restarcie sterownika, gdy zmienne są wyzerowane.

## Uruchomienie linii
Ze stanu Stopped (2) komenda Reset (`xCmdReset`) przeprowadza linię przez Resetting (15, trwa 1 s) do Idle (4). Z Idle komenda Start (`xCmdStart`) przeprowadza linię przez Starting (3, trwa 1 s) do Execute (6). Resetting kasuje kod `iStopReason` do 0.

## Held – zator (stan 11)
Held (11) oznacza przyczynę wewnętrzną w maszynie: zator. Linia przechodzi z Execute do Held, gdy wykryto zator, i ustawia `iStopReason` = 101. Po usunięciu zatoru linia wraca z Held do Execute samoczynnie, bez komendy operatora (w tej linii nie ma komendy Unhold). Z Held można też zatrzymać linię komendą Stop.

## Suspended – brak produktu (stan 5)
Suspended (5) oznacza przyczynę zewnętrzną: brak produktu na wejściu linii. Linia przechodzi z Execute do Suspended i ustawia `iStopReason` = 201. Gdy produkt wróci, linia wraca do Execute samoczynnie. Z Suspended można zatrzymać linię komendą Stop.

## Stopping i Stopped – zatrzymanie przez operatora (stany 7 i 2)
Komenda Stop (`xCmdStop`) działa w stanach Idle, Execute, Held i Suspended: linia przechodzi przez Stopping (7, trwa 1 s) do Stopped (2) i ustawia `iStopReason` = 1. Ponowne uruchomienie wymaga komend Reset, a potem Start.

## Aborting i Aborted – awaria i wyłączenie awaryjne (stany 8 i 9)
Abort ma pierwszeństwo przed wszystkimi innymi przejściami i działa z każdego stanu poza Aborting, Aborted i Clearing. Wywołuje go awaria (`iStopReason` = 301) albo komenda operatora Abort, czyli wyłącznik awaryjny (`iStopReason` = 302). Linia przechodzi przez Aborting (8, trwa 1 s) do Aborted (9). Z Aborted wychodzi się komendą Clear (`xCmdClear`) przez Clearing (1, trwa 1 s) do Stopped (2), ale Clear działa dopiero po usunięciu awarii. Dalej: Reset i Start.
