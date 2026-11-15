// FUNCTION_BLOCK FB_DriveSim – symulacja napędu taśmy (E4-06): moment, prąd, temperatura, zużycie.
// Wartości na sztukę (jak napęd raportujący parametry cyklu), temperatura liczona ciągle.
//   Moment średni   Tm = 2,0 Nm x (1 + 0,15 x zużycie + zimno) + szum 0,06 Nm x (1 + 1,5 x zużycie)
//                   zimno = 0,12 x (40 °C - T) / 18 °C, w zakresie 0..0,12: zimny smar = większe tarcie,
//                   po każdym dłuższym postoju moment jest wyższy o do 12 % i spada, gdy silnik się nagrzeje
//   Moment szczyt.  Tp = Tm x (1,6 + 0,25 x zużycie)     + szum 0,08 Nm x (1 + 2,0 x zużycie)
//   Prąd            I  = 0,8 A + 1,2 A/Nm x Tm            + szum 0,02 A
//   Temperatura     dT/dt = (22 °C + 2,25 x I^2 - T) / 600 s   (inercja 1. rzędu; I = 0 poza Execute)
// Zużycie (np. łożysko): przy xWear rośnie liniowo 0 -> 1 w czasie tWearRamp, bez xWear = 0 (po naprawie).
// Wczesne zużycie ginie w szumie pojedynczej sztuki, a próg na samym momencie myli zużycie z zimnym startem –
// model, który zna temperaturę i kształt cyklu (szczyt/średnia, rozrzut), ma je odróżnić.
// --- część deklaracji ---
FUNCTION_BLOCK FB_DriveSim
VAR_INPUT
    xRun       : BOOL;                 // linia w Execute (napęd pracuje)
    xCycleDone : BOOL;                 // impuls: koniec sztuki – nowe wartości momentu i prądu
    xWear      : BOOL;                 // wstrzyknięte zużycie
    tWearRamp  : TIME := T#20M;        // czas narastania zużycia do 100 %
END_VAR
VAR_OUTPUT
    rTorqueMean : REAL;                // [Nm]
    rTorquePeak : REAL;                // [Nm]
    rCurrent    : REAL;                // [A]
    rTemp       : REAL := 22.0;        // [°C], zaokrąglone do 0,1 (mniej wiadomości przez OPC UA)
    rWear       : REAL;                // 0..1, prawda symulacji – tylko do oceny modelu
END_VAR
VAR
    udiSeed : UDINT := 987654321;
    tLast   : TIME;
    xInit   : BOOL;
    rDt     : REAL;                    // [s] od poprzedniego wywołania
    rT      : REAL := 22.0;            // temperatura bez zaokrąglenia
    rI      : REAL;
    rTm     : REAL;
    rCold   : REAL;                    // dodatkowe tarcie zimnego napędu, 0..0,12
END_VAR
VAR CONSTANT
    T0     : REAL := 2.0;
    TAMB   : REAL := 22.0;
    K_HEAT : REAL := 2.25;
    TAU_S  : REAL := 600.0;
END_VAR

// --- część implementacji ---
IF NOT xInit THEN
    tLast := TIME();
    xInit := TRUE;
END_IF
rDt := TIME_TO_REAL(TIME() - tLast) / 1000.0;
tLast := TIME();

// zużycie
IF xWear AND tWearRamp > T#0S THEN
    rWear := MIN(1.0, rWear + rDt / (TIME_TO_REAL(tWearRamp) / 1000.0));
ELSE
    rWear := 0.0;
END_IF

// temperatura: inercja pierwszego rzędu (metoda Eulera), grzanie proporcjonalne do I^2
IF xRun THEN rI := rCurrent; ELSE rI := 0.0; END_IF
rT := rT + rDt / TAU_S * (TAMB + K_HEAT * rI * rI - rT);
rTemp := DINT_TO_REAL(TRUNC(rT * 10.0)) / 10.0;

// parametry sztuki
IF xCycleDone THEN
    rCold := LIMIT(0.0, 0.12 * (40.0 - rT) / 18.0, 0.12);
    rTm := T0 * (1.0 + 0.15 * rWear + rCold) + 0.06 * (1.0 + 1.5 * rWear) * F_Gauss(udiSeed);
    rTorqueMean := DINT_TO_REAL(TRUNC(rTm * 1000.0)) / 1000.0;
    rTorquePeak := DINT_TO_REAL(TRUNC((rTm * (1.6 + 0.25 * rWear)
                   + 0.08 * (1.0 + 2.0 * rWear) * F_Gauss(udiSeed)) * 1000.0)) / 1000.0;
    rCurrent := DINT_TO_REAL(TRUNC((0.8 + 1.2 * rTm + 0.02 * F_Gauss(udiSeed)) * 1000.0)) / 1000.0;
END_IF
