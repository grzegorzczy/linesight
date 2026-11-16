# Wyniki ewaluacji asystenta

| przebieg | n | postój | recall@k | fakty | fakty PL | fakty EN | cytaty | odmowy OK | zbędne odmowy | zmyślenia | poprawność 0-2 | s/odp. | złe cytaty |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| norag_ollama | 28 | – | – | 10 % | 11 % | 8 % | – | 80 % | 91 % | – | – | 3.76 | 0 |
| rag_gemini_v3 | 28 | 100 % | 100 % | 94 % | 100 % | 83 % | 96 % | 100 % | 4 % | 0 % | 2.00 | 1.42 | 0 |
| rag_ollama | 28 | 93 % | 81 % | 78 % | 86 % | 64 % | 96 % | 80 % | 4 % | – | – | 6.32 | 0 |
| rag_ollama_v2 | 28 | 100 % | 100 % | 82 % | 92 % | 62 % | 91 % | 100 % | 9 % | – | – | 5.84 | 0 |
| rag_ollama_v2__gemini-3.5-flash-lite | 28 | 100 % | 100 % | 82 % | 92 % | 62 % | 91 % | 100 % | 9 % | 43 % | 1.61 | 5.84 | 0 |
| rag_ollama_v2__gemini-3.6-flash | 12 | 100 % | 100 % | 90 % | 89 % | 92 % | 100 % | – | 0 % | 44 % | 1.67 | 7.64 | 0 |
| rag_ollama_v3 | 28 | 100 % | 100 % | 85 % | 94 % | 68 % | 96 % | 100 % | 9 % | 14 % | 1.86 | 5.76 | 0 |
