#!/usr/bin/env python3
"""E3-02: o ile zegar tego urządzenia różni się od serwera czasu (SNTP, sama biblioteka standardowa).

Ten sam skrypt na laptopie (Windows) i Jetsonie (Python 3.6), ten sam serwer:
    python tools/clock_offset.py            (laptop)
    python3 tools/clock_offset.py           (Jetson)
Różnica zegarów Jetson - laptop = offset Jetsona - offset laptopa.

Jak działa pomiar: wysyłamy pakiet o czasie t1 (nasz zegar), serwer odbiera go o t2 i odsyła o t3
(jego zegar), my odbieramy o t4. Zakładając jednakowy czas w obie strony:
    offset = ((t2 - t1) + (t3 - t4)) / 2      opóźnienie sieci = (t4 - t1) - (t3 - t2)
Bierzemy próbkę o najmniejszym opóźnieniu – ma najmniejszy błąd od asymetrii sieci (błąd <= opóźnienie / 2).
"""
import argparse
import socket
import struct
import time

NTP_EPOCH = 2208988800  # sekundy między 1900-01-01 (NTP) a 1970-01-01 (Unix)


def query(server, port=123, timeout=2.0):
    """Jedno zapytanie SNTP. Zwraca (offset_s, opóźnienie_s); offset > 0: nasz zegar się spóźnia."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        t1 = time.time()
        s.sendto(b"\x23" + 47 * b"\0", (server, port))  # LI=0, wersja 4, tryb 3 (klient)
        data, _ = s.recvfrom(512)
        t4 = time.time()
    finally:
        s.close()
    sec2, frac2, sec3, frac3 = struct.unpack("!4I", data[32:48])  # znaczniki odbioru i nadania serwera
    t2 = sec2 - NTP_EPOCH + frac2 / 2.0 ** 32
    t3 = sec3 - NTP_EPOCH + frac3 / 2.0 ** 32
    return ((t2 - t1) + (t3 - t4)) / 2.0, (t4 - t1) - (t3 - t2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="time.google.com")
    ap.add_argument("--port", type=int, default=123)
    ap.add_argument("-n", type=int, default=8, help="liczba próbek (domyślnie 8)")
    args = ap.parse_args()
    samples = []
    for _ in range(args.n):
        try:
            samples.append(query(args.server, args.port))
        except (socket.timeout, OSError) as e:
            print("brak odpowiedzi:", e)
        time.sleep(0.2)
    if not samples:
        raise SystemExit("Serwer {} nie odpowiada (UDP {} zablokowany?)".format(args.server, args.port))
    offset, delay = min(samples, key=lambda x: x[1])
    print("serwer {}  próbek {}/{}".format(args.server, len(samples), args.n))
    print("offset {:+.1f} ms  (opóźnienie sieci {:.1f} ms, błąd <= {:.1f} ms)".format(
        offset * 1e3, delay * 1e3, delay * 1e3 / 2))
    print("offset > 0: zegar tego urządzenia się spóźnia")


if __name__ == "__main__":
    main()
