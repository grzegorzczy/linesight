# Baza wiedzy asystenta (E5-02)

Instrukcja mini linii pakującej LineSight – źródło fragmentów dla asystenta RAG (etap 5).
Ten plik (`README.md`) NIE jest indeksowany.

Zasady pisania (od nich zależy jakość wyszukiwania i cytowań):
- jeden plik = jeden temat; nagłówek `##` = jedna sekcja = zwykle jeden fragment (chunk);
- sekcja ma sens bez czytania sąsiednich – powtarzamy kod błędu i nazwę stanu zamiast pisać „ten stan”;
- tylko fakty zgodne z kodem PLC (`plc/src`) i usługą `diag` – asystent cytuje te zdania jako źródło;
- liczby (progi, czasy) w jednym miejscu; gdy zmienia się kod, zmieniamy instrukcję w tym samym PR.

| Plik | Temat |
|---|---|
| `01-linia.md` | budowa linii, sygnały, wartości nominalne |
| `02-stany-packml.md` | stany PackML i komendy operatora |
| `03-kody-postojow.md` | kody iStopReason 0/1/101/201/301/302 |
| `04-procedury.md` | co zrobić przy każdym rodzaju postoju |
| `05-naped.md` | kondycja napędu taśmy: moment, prąd, temperatura, alarm |
| `06-diagnostyka.md` | jak czytać postój: przyczyna, pewność, dowody, klip |

Historia postojów nie jest tu pisana ręcznie – opisy zamkniętych postojów generuje E5-03 z tabeli `stop_event`.
