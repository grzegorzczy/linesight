# Analiza projektu względem ogłoszenia (18.11.2026, po etapie 6)

Ogłoszenie: ML Engineer – video & industrial data (platforma AI dla linii pakujących:
dane z PLC + wideo na NVIDIA Jetson + asystent z wiedzą techniczną zakładu).

Legenda: ✓ pokryte i zmierzone · ½ częściowo · ✗ projekt tego nie pokrywa

## Must-have

| Wymóg | Pokrycie | Dowód w repozytorium | Uwagi na rozmowę |
|---|---|---|---|
| 3 lata jako ML/CV Engineer, modele na produkcji | ✗ | – | Projekt nie zastąpi stażu. Pokazuje praktyki produkcyjne: bramka jakości, kanarek, rollback w 1 s, monitoring dryfu (etap 6), testy na sprzęcie, a nie w notebooku. |
| Python, PyTorch | ✓ | `anomaly/` – własna pętla treningowa autoenkodera (etap 4) | Detektor trenowany przez API `ultralytics` – świadoma decyzja (backlog, 10.11); umieć opisać, co ta pętla robi w środku. |
| CV: detekcja, analiza wideo, YOLO | ✓ | etap 1 (YOLO26n, własny zbiór), etap 2 (tracking, zliczanie) | |
| Jetson, TensorRT, ONNX, kwantyzacja | ✓ | etap 1: FP32/FP16/INT8 na Nano, profil warstw | Najmocniejsza część: FP16 = 1,23× (Amdahl), INT8 bez zysku na Maxwellu, operator `Mod` a parser TRT 8.2. |
| GStreamer, DeepStream, RTSP, H.264/H.265 | ✓ / ½ | etap 2: potok DeepStream, NVENC, RTSP, klipy z bufora kołowego | H.265 niepokazane → E7-04. |
| Potoki danych, szeregi czasowe, TimescaleDB | ✓ | etap 3: OPC UA → MQTT → TimescaleDB, hipertabele, `signals_before()` | |
| Linux, Docker, Git | ✓ | ok. 80 PR-ów, `infra/docker-compose.yml` | Brak CI → E7-06 (opcjonalne). |
| Samodzielność, doprowadzanie do końca | ✓ | 7 etapów, backlog, decyzje z datami | |
| Angielski | ½ | README i komentarze po angielsku, asystent PL/EN | Dokumenty etapów po polsku. |

## Mile widziane

| Wymóg | Pokrycie | Dowód |
|---|---|---|
| PLC, OPC UA, MQTT, sygnały maszynowe | ✓ | etap 3: PackML na variTRON 300, most OPC UA → MQTT |
| Szeregi czasowe, anomalie, predictive maintenance (kondycja napędu, moment) | ✓ | etap 4: autoenkoder na cechach momentu/prądu/temperatury, porównanie z 2 baseline'ami |
| LLM, RAG, ewaluacja asystenta | ✓ | etap 5: 28 pytań, metryki deterministyczne, sędzia LLM zwalidowany na 12 ocenach ręcznych |
| C# / .NET | ½ | tylko LineGuard (nieukończony), poza tym repozytorium |
| GCP, MLOps: wersjonowanie, monitoring, retrening | ✓ | etap 6: rejestr z bramką, sync na Jetsonie, dryf w Grafanie, retrening v2 |
| Praca na liniach / w fabryce | ✓ | praca zawodowa (automatyka, zakłady spożywcze); w projekcie PackML i kody postojów |

## Obowiązki z ogłoszenia a etapy

| Obowiązek | Etap |
|---|---|
| Potoki danych z PLC i kamer, wideo na urządzeniach NVIDIA | 2, 3 |
| Modele wideo na Jetsonie, optymalizacja wydajności | 1, 2 |
| Model na danych maszynowych (moment, kondycja napędu), od eksploracji po wdrożenie | 4 |
| Warstwa LLM i regularna ewaluacja asystenta | 5 |
| Procesor telemetrii: stany i zdarzenia maszyn, przyczyny strat | 3, 4 |
| Monitorowanie modeli, degradacja, planowanie retreningu | 6 |
| Dokumentowanie rozwiązań | `docs/`, etap 7 |

## Słabe punkty – zanim wytknie je rekruter

1. **Małe zbiory testowe.** Detektor: test 21 zdjęć; v1 vs v2 różnią się o 0,005-0,016 mAP50-95, czyli w granicach
   szumu. Mówić wprost: liczby pokazują metodę (bramka, reguły ustalone przed pomiarem), nie przewagę modelu.
2. **Napęd jest symulowany w PLC.** Autoenkoder uczy się na modelu fizycznym napisanym przez autora; 3 epizody zużycia.
   Wartość: cały potok od cech po wdrożenie ONNX, nie wynik na prawdziwym silniku.
3. **Odtwarzalność.** Bez sterownika variTRON 300 linii nie da się uruchomić (kod ST przenośny na CODESYS Control Win).
4. **Jedna osoba, jedno stanowisko.** Brak testu na wielu liniach / kamerach, oświetlenie kontrolowane.
5. **Otwarty błąd:** status łącza PLC przełącza się w Grafanie → E7-02.
6. **README za długie na pierwsze wrażenie** (ponad 230 linii) → E7-05.

## Co z tego wynika dla etapu 7

Bez filmu demo. Pierwszy ekran README: problem, zrzut Grafany z postojem i odpowiedzią asystenta, diagram, 5 liczb,
ograniczenia. Domknięcie H.265 (E7-04), naprawa statusu łącza (E7-02), opcjonalnie CI (E7-06).
