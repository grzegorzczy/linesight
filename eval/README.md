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
