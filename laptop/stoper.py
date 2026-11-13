"""E2-05: stoper do pomiaru opóźnienia "od szkła do szkła" (laptop, Windows, Python 3.12, tylko biblioteka standardowa).

Uruchom:  python laptop\\stoper.py
Ustaw kamerę Jetsona na to okno, obok otwórz VLC ze strumieniem RTSP i zrób zrzut całego ekranu (Win+Shift+S).
Opóźnienie = czas w oknie stopera - czas widoczny w obrazie z VLC.
Dokładność: odświeżanie ekranu (~16 ms przy 60 Hz) i czas naświetlania kamery (~33 ms przy 30 FPS).
"""
import time
import tkinter as tk

t0 = time.perf_counter()
root = tk.Tk()
root.title("LineSight - stoper")
label = tk.Label(root, font=("Consolas", 72, "bold"), fg="black", bg="white", padx=20, pady=10)
label.pack()


def tick():
    label.config(text="{:8.3f}".format(time.perf_counter() - t0))
    root.after(1, tick)  # odświeżanie tak często, jak pozwala Tk (i tak ogranicza je ekran)


tick()
root.mainloop()
