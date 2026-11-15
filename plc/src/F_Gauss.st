// FUNCTION F_Gauss – szum o rozkładzie zbliżonym do normalnego (średnia 0, odchylenie 1).
// Suma 4 liczb równomiernych z LCG (centralne twierdzenie graniczne); wystarcza do symulacji pomiaru.
// Ziarno przekazywane przez VAR_IN_OUT – stan generatora trzyma wywołujący blok.
// --- część deklaracji ---
FUNCTION F_Gauss : REAL
VAR_IN_OUT
    udiSeed : UDINT;
END_VAR
VAR
    i : INT;
    rSum : REAL;                     // zmienne funkcji startują od 0 przy każdym wywołaniu; nie „s”: S i R to słowa kluczowe IEC (Set/Reset)
END_VAR

// --- część implementacji ---
FOR i := 1 TO 4 DO
    udiSeed := udiSeed * 1103515245 + 12345;
    rSum := rSum + UDINT_TO_REAL((udiSeed / 65536) MOD 32768) / 32768.0;
END_FOR
F_Gauss := (rSum - 2.0) * 1.7320508;    // suma 4 x U(0,1): średnia 2, wariancja 4/12 -> skalowanie do odchylenia 1
