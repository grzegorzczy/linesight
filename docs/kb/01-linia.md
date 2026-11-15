# Mini linia pakująca LineSight – budowa i sygnały

## Budowa linii
Mini linia pakująca LineSight przesuwa butelki taśmą przed kamerą. Linią steruje sterownik PLC (JUMO variTRON 300, CODESYS) z maszyną stanów PackML. Kamera USB podłączona do NVIDIA Jetson Nano rozpoznaje trzy klasy obiektów: `bottle` (butelka poprawna), `missing_cap` (butelka bez nakrętki) i `fallen` (butelka przewrócona, przyczyna zatoru). Jetson zlicza sztuki przecinające linię w połowie kadru, nagrywa klipy wideo przy wadach i wysyła zdarzenia przez MQTT. Sygnały ze sterownika trafiają przez OPC UA i MQTT do bazy TimescaleDB na laptopie, gdzie usługa `diag` wykrywa postoje i ocenia kondycję napędu.

## Wartości nominalne pracy
Nominalny czas cyklu jednej sztuki wynosi 1500 ms (nastawa `tCycleNominal`) z rozrzutem ±100 ms, co daje około 40 sztuk na minutę. Rzeczywisty zmierzony czas cyklu (`udiCycleTime_ms`) jest nieco dłuższy od zadanego, bo sterownik sprawdza timer raz na cykl zadania (200 ms). Prędkość maszyny `rMachSpeed` [szt./min] liczona jest z ostatniego czasu cyklu i wynosi 0 poza stanem Execute. Degradacja (wstrzyknięta `xInjSlow`) wydłuża czas cyklu o 40 %, do około 2100 ms.

## Sygnały sterownika
Sterownik wystawia przez OPC UA: `iStateCurrent` (numer stanu PackML), `iStopReason` (kod przyczyny postoju), `udiProdProcessed` (licznik sztuk, narastający, nie jest kasowany), `udiCycleTime_ms` (czas ostatniego cyklu), `rMachSpeed` (prędkość), oraz parametry napędu taśmy na każdą sztukę: `rTorqueMean_Nm` (średni moment), `rTorquePeak_Nm` (moment szczytowy), `rCurrent_A` (prąd silnika) i `rMotorTemp_C` (temperatura silnika). Komendy operatora to `xCmdReset`, `xCmdStart`, `xCmdStop`, `xCmdAbort`, `xCmdClear` (reagują na zbocze narastające).

## Wstrzykiwanie awarii (symulacja)
Do testów awarie wywołuje się zmiennymi `xInj*`: `xInjJam` (zator), `xInjNoProduct` (brak produktu), `xInjFault` (awaria, np. napędu), `xInjSlow` (wolniejszy cykl), `xInjWear` (narastające zużycie łożyska napędu przez `tWearRamp`, domyślnie 20 minut). Zmienne `xInj*` są „prawdą” symulacji: w prawdziwym zakładzie ich nie ma, dlatego reguły diagnostyki ich nie używają, a w dowodach postoju pojawiają się tylko w osobnym polu `sim`.
