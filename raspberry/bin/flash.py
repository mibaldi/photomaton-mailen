#!/usr/bin/env python3
"""Destello blanco a pantalla completa (~0,25 s) al hacer la foto."""
import tkinter as tk
r = tk.Tk()
r.overrideredirect(True)
r.attributes("-topmost", True)
w, h = r.winfo_screenwidth(), r.winfo_screenheight()
r.geometry(f"{w}x{h}+0+0")
r.configure(bg="white", cursor="none")
r.after(250, r.destroy)
r.mainloop()
