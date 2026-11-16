# Instrukcja etykietowania

Obowiązuje dla całego zbioru LineSight. Każde zdjęcie etykietujemy według
tych samych zasad – niespójne etykiety uczą model sprzecznych rzeczy
i obniżają mAP bardziej niż mała liczba zdjęć.

## Klasy

| ID | Nazwa | Kiedy |
|---|---|---|
| 0 | `bottle` | butelka **stoi** i **ma nakrętkę** |
| 1 | `missing_cap` | butelka **stoi** i **nie ma nakrętki** (widać sam pierścień szyjki) |
| 2 | `fallen` | butelka **leży** lub jest przechylona **o więcej niż 45°** od pionu – **niezależnie od nakrętki** |

Jedna butelka = jedna ramka = jedna klasa. Pierwszeństwo: `fallen` >
`missing_cap` > `bottle`. Leżąca butelka bez nakrętki to `fallen`, bo na
linii przewrócona butelka to zator i postój – brak nakrętki jest wtedy
drugorzędny.

## Butelka przechylona (reguła 45°) – E6-08

Dodana 16.11 po analizie niepewnych klatek z E6-06: dwie klatki z tą samą sytuacją (butelka przechylona ok. 20–30°
w trakcie przewracania) model v1 nazwał raz `fallen`, raz `bottle`, obie z pewnością ok. 0,5. Dotąd reguła
mówiła „wyraźnie przechylona”, więc granica nie była zdefiniowana – także w etykietach v1.

| Oś butelki (dno → szyjka) względem pionu | Klasa |
|---|---|
| ≤ 45° | `bottle` / `missing_cap` – według nakrętki |
| > 45° albo leży | `fallen` |

Ocena „na oko”: 45° to połowa drogi między stojącą a leżącą. Gdy naprawdę nie da się rozstrzygnąć (ok. 40–50°),
zdjęcie **pomijamy** – lepiej mniej przykładów niż sprzeczne etykiety.

## Rozmycie ruchu i ręka – E6-08

- Butelka rozmyta, ale rozpoznawalna (widać kształt i kolor nakrętki / szyjki) – etykietujemy normalnie.
- Rozmycie tak duże, że nie widać, czy jest nakrętka: stojąca → `bottle` (jak przy ciętej butelce – nie zgadujemy
  braku nakrętki), przechylona > 45° → `fallen`.
- Ręka trzymająca butelkę: ramka tylko na butelkę (widoczną część), ręki nie etykietujemy.

## Jak rozpoznać nakrętkę

| Co widać na górze butelki | Klasa |
|---|---|
| różowa nakrętka | `bottle` |
| niebieskawy walec szyjki (gwint) z pierścieniem, bez różu | `missing_cap` |
| butelka leży – z otworem lub z nakrętką | `fallen` |

Z boku goła szyjka wygląda prawie jak nakrętka – rozstrzyga kolor
(różowy = nakrętka).

## Ramka

- Obejmuje **widoczną część** butelki, od dna do nakrętki (albo szyjki),
  ciasno – bez marginesu tła.
- Butelka częściowo zasłonięta przez inną: ramka tylko na widoczną część.
- Butelka ucięta przez krawędź kadru: etykietujemy, jeśli widać co
  najmniej ok. 1/3 butelki. Mniej – pomijamy.
- Klasę ciętej butelki ustalamy po tym, co widać. Jeśli nie widać szyjki,
  a butelka stoi – `bottle` (nie zgadujemy braku nakrętki).

## Czego nie etykietujemy

- Odłożonych nakrętek, rąk, przedmiotów w tle.
- Zdjęć z sesji `empty` – zostają bez etykiet jako tło (negatywy).

## Kontrola

- Po zakończeniu przejrzeć po 5 losowych zdjęć z każdej sesji.
- Liczba obiektów na klasę – zakładka `Classes` na Ultralytics Platform.
  Cel: co najmniej ok. 150 na klasę.
