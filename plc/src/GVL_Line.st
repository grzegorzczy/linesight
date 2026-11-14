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

    // --- Nastawy ---
    tCycleNominal : TIME := T#1500MS;   // nominalny czas cyklu (1 sztuka)

    // --- Status (tylko do odczytu dla świata) ---
    iStateCurrent    : INT;     // Status.StateCurrent (numer stanu PackML)
    iStopReason      : INT;     // Admin.StopReason.ID: 0 brak, 1 stop operatora, 101 zator,
                                // 201 brak produktu, 301 awaria, 302 abort operatora
    udiProdProcessed : UDINT;   // Admin.ProdProcessedCount (licznik narastający, nie kasujemy)
    udiCycleTime_ms  : UDINT;   // czas ostatniego cyklu [ms] (symulowany)
    rMachSpeed       : REAL;    // Status.CurMachSpeed [szt./min], 0 poza Execute
END_VAR
