// DUT (Enumeration). Numery stanów zgodne z PackML (ISA-TR88.00.02, PackTag Status.StateCurrent).
// Podzbiór: bez stanów przejściowych Holding/Unholding/Suspending/Unsuspending i bez Completing/Complete.
{attribute 'qualified_only'}
TYPE E_PackML :
(
    Clearing  := 1,
    Stopped   := 2,
    Starting  := 3,
    Idle      := 4,
    Suspended := 5,   // przyczyna zewnętrzna: brak produktu na wejściu
    Execute   := 6,
    Stopping  := 7,
    Aborting  := 8,
    Aborted   := 9,
    Held      := 11,  // przyczyna wewnętrzna: zator w maszynie
    Resetting := 15
) INT;
END_TYPE
