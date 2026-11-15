#!/usr/bin/env python3
"""E4-04: serwer klipów HTTP na Jetsonie (Python 3.6), wielowątkowy.

`python3 -m http.server` w Pythonie 3.6 obsługuje jedno połączenie naraz (ThreadingHTTPServer jest dopiero
w 3.7): przeglądarka, która trzyma otwarte połączenie z odtwarzanym klipem, blokuje wszystkie kolejne zapytania.
Tu każde zapytanie dostaje własny wątek. Dalej tylko odczyt plików z jednego katalogu.

Uruchomienie: python3 ~/linesight/jetson/serve_clips.py   (port 8080, katalog ~/linesight_clips)
"""
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True   # wątki nie blokują zamknięcia serwera (Ctrl+C)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    os.chdir(os.path.expanduser(sys.argv[2] if len(sys.argv) > 2 else "~/linesight_clips"))
    print("Klipy z {} na http://0.0.0.0:{}/".format(os.getcwd(), port), flush=True)
    ThreadingHTTPServer(("", port), SimpleHTTPRequestHandler).serve_forever()


if __name__ == "__main__":
    main()
