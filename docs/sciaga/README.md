# Ściąga Word – generator

`build_sciaga.js` buduje `LineSight-sciaga.docx` (komendy krok po kroku,
SSH1 / SSH2 / LAPTOP). Plik `.docx` jest poza repozytorium (`.gitignore`),
źródłem jest ten skrypt – zmiany w ściądze = zmiany tutaj.

```
npm install docx          # raz
node docs/sciaga/build_sciaga.js LineSight-sciaga.docx
```
