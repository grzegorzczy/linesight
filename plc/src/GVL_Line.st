// GVL: interfejs linii – wszystko, co wystawiamy przez OPC UA (E3-04).
{attribute 'qualified_only'}
VAR_GLOBAL
    // --- Komendy operatora (zbocze narastające; odpowiednik PackTag Command.CntrlCmd) ---
    xCmdReset     : BOOL;   // Stopped -> Resetting -> Idle
    xCmdStart     : BOOL;   // Idle -> Starting -> Execute
    xCmdStop      : BOOL;   // Idle/Execute/Held/Suspended -> Stopping -> Stopped
    xCmdAbort     : BOOL;   // dowolny stan -> Aborting -> Aborted (wyłącznik awaryjny)
    xCmdClear     : BOOL;   // Aborted -> Clearing -> Stopped

    // --- Wstrzykiwanie awarii (poziom: TRUE = usterka trwa) ---
    xInjJam       : BOOL;   // zator                 -> Held,      iStopReason 101
    xInjNoProduct : BOOL;   // brak produktu         -> Suspended, iStopReason 201
    xInjFault     : BOOL;   // awaria (np. napęd)    -> Aborted,   iStopReason 301
    xInjSlow      : BOOL;   // degradacja: czas cyklu +40 % (dane do wykrywania anomalii, etap 4)
    xInjWear      : BOOL;   // E4-06: zużycie napędu (łożysko) narasta przez tWearRamp; FALSE = naprawa

    // --- Nastawy ---
    tCycleNominal : TIME := T#1500MS;   // nominalny czas cyklu (1 sztuka)
    tWearRamp     : TIME := T#20M;      // E4-06: czas narastania zużycia napędu do 100 %

    // --- Status (tylko do odczytu dla świata) ---
    iStateCurrent    : INT;     // Status.StateCurrent (numer stanu PackML)
    iStopReason      : INT;     // Admin.StopReason.ID: 0 brak, 1 stop operatora, 101 zator,
                                // 201 brak produktu, 301 awaria, 302 abort operatora
    udiProdProcessed : UDINT;   // Admin.ProdProcessedCount (licznik narastający, nie kasujemy)
    udiCycleTime_ms  : UDINT;   // czas ostatniego cyklu [ms] (symulowany)
    rMachSpeed       : REAL;    // Status.CurMachSpeed [szt./min], 0 poza Execute

    // --- E4-06: napęd taśmy (FB_DriveSim), wartości na sztukę ---
    rTorqueMean_Nm   : REAL;    // średni moment w cyklu
    rTorquePeak_Nm   : REAL;    // szczytowy moment w cyklu
    rCurrent_A       : REAL;    // prąd silnika
    rMotorTemp_C     : REAL;    // temperatura silnika (0,1 °C)
    rSimWear         : REAL;    // zużycie 0..1 – prawda symulacji, tylko do oceny modelu (zaokr. 0,01)
END_VAR
