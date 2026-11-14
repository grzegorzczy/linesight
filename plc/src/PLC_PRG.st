// PROGRAM PLC_PRG – maszyna stanów PackML (podzbiór) + symulacja produkcji.
// --- część deklaracji ---
PROGRAM PLC_PRG
VAR
    eState    : E_PackML := E_PackML.Stopped;
    ePrev     : E_PackML := E_PackML.Stopped;
    xNewState : BOOL;
    tonAct    : TON;                 // czas trwania stanów przejściowych (Starting, Stopping, ...)
    tonCycle  : TON;                 // czas cyklu jednej sztuki
    rtReset, rtStart, rtStop, rtAbort, rtClear : R_TRIG;
    tCycle    : TIME := T#1500MS;    // czas bieżącego cyklu (nominalny ± rozrzut)
    udiBase   : UDINT;
    udiSeed   : UDINT := 12345;      // generator pseudolosowy (LCG) do rozrzutu czasu cyklu
    xRun, xRunPrev : BOOL;
    tStart, tNow   : TIME;           // TIME() = czas od startu sterownika; z niego mierzymy rzeczywisty cykl
END_VAR
VAR CONSTANT
    T_ACT : TIME := T#1S;            // ile trwa każdy stan przejściowy
END_VAR

// --- część implementacji ---
rtReset(CLK := GVL_Line.xCmdReset);
rtStart(CLK := GVL_Line.xCmdStart);
rtStop(CLK := GVL_Line.xCmdStop);
rtAbort(CLK := GVL_Line.xCmdAbort);
rtClear(CLK := GVL_Line.xCmdClear);

// Zegar stanu przejściowego: zeruje się w cyklu, w którym stan się zmienił
xNewState := eState <> ePrev;
ePrev := eState;
tonAct(IN := NOT xNewState, PT := T_ACT);

// Abort ma pierwszeństwo przed wszystkim (jak w PackML: z każdego stanu)
IF (rtAbort.Q OR GVL_Line.xInjFault)
   AND eState <> E_PackML.Aborting AND eState <> E_PackML.Aborted AND eState <> E_PackML.Clearing THEN
    IF GVL_Line.xInjFault THEN
        GVL_Line.iStopReason := 301;
    ELSE
        GVL_Line.iStopReason := 302;
    END_IF
    eState := E_PackML.Aborting;
// Stop operatora z każdego stanu „roboczego”
ELSIF rtStop.Q AND (eState = E_PackML.Idle OR eState = E_PackML.Execute
                    OR eState = E_PackML.Held OR eState = E_PackML.Suspended) THEN
    GVL_Line.iStopReason := 1;
    eState := E_PackML.Stopping;
ELSE
    CASE eState OF
        E_PackML.Stopped:
            IF rtReset.Q THEN eState := E_PackML.Resetting; END_IF

        E_PackML.Resetting:
            GVL_Line.iStopReason := 0;
            IF tonAct.Q THEN eState := E_PackML.Idle; END_IF

        E_PackML.Idle:
            IF rtStart.Q THEN eState := E_PackML.Starting; END_IF

        E_PackML.Starting:
            IF tonAct.Q THEN eState := E_PackML.Execute; END_IF

        E_PackML.Execute:
            IF GVL_Line.xInjJam THEN
                GVL_Line.iStopReason := 101;
                eState := E_PackML.Held;
            ELSIF GVL_Line.xInjNoProduct THEN
                GVL_Line.iStopReason := 201;
                eState := E_PackML.Suspended;
            END_IF

        E_PackML.Held:        // zator usunięty -> wracamy do pracy
            IF NOT GVL_Line.xInjJam THEN
                GVL_Line.iStopReason := 0;
                eState := E_PackML.Execute;
            END_IF

        E_PackML.Suspended:   // produkt wrócił -> wracamy do pracy
            IF NOT GVL_Line.xInjNoProduct THEN
                GVL_Line.iStopReason := 0;
                eState := E_PackML.Execute;
            END_IF

        E_PackML.Stopping:
            IF tonAct.Q THEN eState := E_PackML.Stopped; END_IF

        E_PackML.Aborting:
            IF tonAct.Q THEN eState := E_PackML.Aborted; END_IF

        E_PackML.Aborted:     // kasowanie możliwe dopiero po usunięciu awarii
            IF rtClear.Q AND NOT GVL_Line.xInjFault THEN eState := E_PackML.Clearing; END_IF

        E_PackML.Clearing:
            IF tonAct.Q THEN
                GVL_Line.iStopReason := 0;
                eState := E_PackML.Stopped;
            END_IF
    END_CASE
END_IF

// --- Symulacja produkcji: w Execute jedna sztuka co tCycle ---
// udiCycleTime_ms to ZMIERZONY czas od poprzedniej sztuki (TIME()), a nie zadany tCycle:
// timer widzi czas tylko co cykl zadania, więc rzeczywisty cykl jest dłuższy od zadanego.
xRun := eState = E_PackML.Execute;
IF xRun AND NOT xRunPrev THEN
    tStart := TIME();                // wejście w Execute: liczymy od nowa (postój nie wlicza się do cyklu)
END_IF
xRunPrev := xRun;
tonCycle(IN := xRun, PT := tCycle);
IF tonCycle.Q THEN
    tNow := TIME();
    GVL_Line.udiProdProcessed := GVL_Line.udiProdProcessed + 1;
    GVL_Line.udiCycleTime_ms := TIME_TO_UDINT(tNow - tStart);
    tStart := tNow;
    tonCycle(IN := FALSE);           // kasowanie timera; nowy cykl rusza w następnym cyklu zadania

    // czas następnego cyklu: nominalny (x1,4 przy degradacji) z rozrzutem ±100 ms
    udiBase := TIME_TO_UDINT(GVL_Line.tCycleNominal);
    IF GVL_Line.xInjSlow THEN udiBase := udiBase * 14 / 10; END_IF
    IF udiBase < 300 THEN udiBase := 300; END_IF
    udiSeed := udiSeed * 1103515245 + 12345;
    tCycle := UDINT_TO_TIME(udiBase + (udiSeed / 65536) MOD 201 - 100);
END_IF

// --- Status na zewnątrz ---
GVL_Line.iStateCurrent := eState;
IF eState = E_PackML.Execute AND GVL_Line.udiCycleTime_ms > 0 THEN
    GVL_Line.rMachSpeed := 60000.0 / UDINT_TO_REAL(GVL_Line.udiCycleTime_ms);
ELSE
    GVL_Line.rMachSpeed := 0.0;
END_IF
