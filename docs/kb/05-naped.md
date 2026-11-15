# Kondycja napędu taśmy

## Parametry napędu w normalnej pracy
Napęd taśmy raportuje po każdej sztuce średni moment `rTorqueMean_Nm`, moment szczytowy `rTorquePeak_Nm` i prąd `rCurrent_A`; temperatura `rMotorTemp_C` jest liczona ciągle. Rozgrzany, sprawny napęd: moment średni ok. 2,0 Nm (szum ok. 0,06 Nm), moment szczytowy ok. 1,6 × średni, czyli ok. 3,2 Nm, prąd ok. 3,2 A, temperatura ustalona ok. 45 °C. Silnik nagrzewa się ze stałą czasową 10 minut, więc temperaturę ustaloną osiąga po ok. 30 minutach pracy.

## Zimny start
Po dłuższym postoju zimny smar zwiększa tarcie: moment średni jest wyższy o do 12 % (do ok. 2,24 Nm), gdy silnik ma temperaturę otoczenia 22 °C. Nadwyżka maleje liniowo z temperaturą i znika powyżej 40 °C. Wyższy moment na zimnym napędzie jest normalny i nie oznacza zużycia – dlatego prosty próg na samym momencie daje fałszywe alarmy po każdym dłuższym postoju.

## Objawy zużycia napędu (łożysko)
Zużycie łożyska narasta stopniowo. Przy pełnym zużyciu: moment średni rośnie o 15 % (do ok. 2,3 Nm), moment szczytowy rośnie bardziej niż średni (stosunek szczyt/średnia z 1,6 do 1,85, ok. 4,25 Nm), rozrzut momentu z sztuki na sztukę rośnie 2,5 raza, prąd rośnie do ok. 3,6 A, a temperatura ustalona do ok. 50 °C. Odróżnienie od zimnego startu: przy zużyciu moment jest wysoki mimo ciepłego silnika i rośnie stosunek szczyt/średnia oraz rozrzut.

## Wskaźnik kondycji i alarm
Kondycję ocenia model (autoenkoder) na oknie 32 kolejnych sztuk; wynik to błąd odtworzenia podzielony przez próg wyznaczony na danych walidacyjnych. Kondycja w Grafanie: 100 % gdy wynik ≤ 0,3 progu, ok. 66 % na progu, 0 % przy wyniku ≥ 10 progów (skala logarytmiczna). Alarm napędu włącza się, gdy wynik jest powyżej progu przez co najmniej 20 kolejnych sztuk – pojedyncze skoki nie dają alarmu. Na danych testowych model wykrywał zużycie przy ok. 14-17 % jego rozwoju, bez fałszywych alarmów.

## Co zrobić przy alarmie napędu
1. Sprawdź w Grafanie, czy alarm nie pojawił się zaraz po dłuższym postoju (zimny start) – wtedy obserwuj, czy kondycja wraca po nagrzaniu.
2. Porównaj moment szczytowy z średnim: rosnący stosunek szczyt/średnia wskazuje na łożysko lub mechanikę taśmy.
3. Zaplanuj przegląd łożyska i smarowanie w najbliższym postoju planowym, zanim napęd spowoduje awarię (kod 301).
4. Po naprawie kondycja powinna wrócić do ok. 100 %; jeśli nie wraca, sprawdź naciąg taśmy.
