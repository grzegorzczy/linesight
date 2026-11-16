# Ewaluacja asystenta (E5-06, E5-07)

`questions.jsonl` – zestaw 28 pytań (19 PL, 9 EN), jeden JSON na linię:

| Pole | Znaczenie |
|---|---|
| `id` | P = konkretny postój, M = instrukcja, H = historia, R = pytanie bez odpowiedzi w źródłach |
| `type` | `stop`, `no_stop`, `manual`, `history`, `refusal` |
| `question` | pytanie dokładnie tak, jak zadaje je użytkownik |
| `stop` | początek postoju (czas lokalny), który asystent ma znaleźć; `null` = postoju być nie powinno |
| `answerable` | `false` = poprawna odpowiedź to odmowa („nie wiem”) |
| `must` | wymagane fakty: lista grup, w grupie warianty (PL/EN, odmiana); fakt jest, gdy w odpowiedzi jest dowolny wariant (bez rozróżniania wielkości liter) |
| `sources` | sekcje instrukcji, które wyszukiwanie powinno zwrócić w top-k (fragment nazwy sekcji z `docs/kb`) |
| `reference` | wzorcowa odpowiedź – dla sędziego LLM i dla człowieka |
| `note` | dlaczego pytanie jest trudne |

Zasady:
- Wzorcowe odpowiedzi wynikają z kontekstu, który asystent faktycznie dostaje (`data/eval_contexts.json`, zrzut
  `assistant/dump_contexts.py`) i z logu sesji `tools/scenario_rag.py` (16.11) – nie z wiedzy autora o symulacji.
- Zestaw zmieniamy tylko wtedy, gdy zmieniają się dane albo instrukcja – NIE pod wynik modelu. Poprawki promptu
  oceniamy na tym samym zestawie przed i po.
- Pytania o postoje mają datę w treści, więc wynik nie zależy od dnia uruchomienia ewaluacji.

## Sędzia LLM i jego sprawdzenie

Sędzia (`--judge gemini --judge-model …`) dzieli odpowiedź na pojedyncze twierdzenia i każde ocenia: `supported`,
`unsupported` (brak w źródłach, także własne interpretacje), `contradicted` (sprzeczne ze źródłami). Zmyślenie =
co najmniej jedno twierdzenie `unsupported`/`contradicted` albo cytat nieistniejącego źródła.

Sędzia też może się mylić (test 16.11: pierwsza wersja promptu uznała „the stop was confirmed as a jam” przy
pewności `tylko_plc` za poprawne). Dlatego `judge_labels.jsonl` – 12 odpowiedzi z przebiegu `rag_ollama_v2` ocenionych
ręcznie (4 ze zmyśleniem, 8 bez) – i tryb:

    python eval\run_eval.py --rejudge rag_ollama_v2 --judge gemini --judge-model gemini-3.6-flash --judge-check

Wynik: zgodność z człowiekiem, czułość (ile zmyśleń wykrył) i fałszywe alarmy. Sędziego, który nie wykrywa
oznaczonych zmyśleń, nie używamy do porównań.

Uwaga: Ollama przy `temperature 0` nie jest w pełni deterministyczna (16.11: P01 inna w dwóch przebiegach) – stąd
`seed` w zapytaniu i kontrola `answer_start` w etykietach.
