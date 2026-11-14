# PLC (CODESYS) – maszyna stanów PackML

Projekt CODESYS (`*.project`) jest plikiem binarnym, więc źródłem prawdy dla kodu są pliki tekstowe
w `src/` (diff i przegląd w PR). Do projektu wklejamy je ręcznie:

| Plik | Obiekt w CODESYS |
|---|---|
| `src/E_PackML.st` | DUT → Enumeration `E_PackML` |
| `src/GVL_Line.st` | Global Variable List `GVL_Line` |
| `src/PLC_PRG.st` | `PLC_PRG` (część deklaracji i część implementacji osobno) |

Tylko biblioteka `Standard` (TON, R_TRIG); kod nie zależy od urządzenia docelowego.
