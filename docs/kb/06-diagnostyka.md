# Jak czytać diagnostykę postoju

## Czym jest postój w systemie
Postój (tabela `stop_event`) to okres od wyjścia linii ze stanu Execute do powrotu do Execute. Łańcuch stanów (np. Held, potem Stopping, Stopped) to jeden postój; przerwy w Execute krótsze niż 2 s są łączone. Postój ma: początek `t_start`, koniec `t_end` (pusty, gdy postój trwa), pierwszy stan po Execute, kod `iStopReason`, przyczynę, pewność, dowody i link do klipu. Usługa `diag` przelicza postoje co 5 s.

## Przyczyna postoju
Przyczyna pochodzi z reguł: najpierw z kodu `iStopReason` (101 zator, 201 brak_produktu, 301 i 302 awaria, 1 operator), a gdy kodu brak – ze stanu (11 zator, 5 brak_produktu, 8 awaria, 7 operator). Stan spoza listy PackML daje przyczynę `restart_plc`. Gdy postój składa się z kilku stanów, kolejne przyczyny trafiają do pola `secondary` w dowodach.

## Pewność przyczyny
Pewność mówi, czy kamera potwierdza kod ze sterownika. `potwierdzona` – kamera widziała to samo (przewróconą butelkę przed zatorem albo brak butelek przez 10 s przed brakiem produktu). `tylko_plc` – kamera nic nie wnosi (awaria, operator), nic nie widziała albo była offline. `sprzeczna` – kamera przeczy sterownikowi, np. kod brak produktu, a butelki płynęły tuż przed postojem; wtedy podejrzany jest czujnik.

## Dowody postoju
Dowody (pole `evidence`) obejmują okno 30 s przed postojem: stany PLC, kod przyczyny, liczbę sztuk w oknie, ostatni czas cyklu, informację o braku połączenia z PLC; z kamery: liczbę obiektów każdej klasy, czasy przewróconych butelek względem początku postoju (ujemne = przed postojem), ile sekund przed postojem przeszła ostatnia sztuka i czy kamera była offline. Zdarzenia kamery liczone są najwcześniej od końca poprzedniego postoju, aby jedna przewrócona butelka nie potwierdziła dwóch zatorów.

## Klip wideo
Do postoju dołączany jest link do klipu z Jetsona (serwer klipów, port 8080). Klipy powstają tylko dla wad (`missing_cap`, `fallen`) i obejmują czas przed i po zdarzeniu. Pierwszeństwo ma klip pasujący do przyczyny (przewrócona butelka przy zatorze), potem zdarzenie najbliższe początkowi postoju. Brak klipu oznacza, że kamera nie widziała wady – to informacja, nie błąd.
