"""
Einstiegspunkt der Anwendung.

Enthält bewusst so gut wie keine Logik mehr – die eigentliche
Funktionalität steckt in core/ (Datenverarbeitung) und gui/ (Darstellung).
"""

import tkinter as tk

from gui.main_window import InstagramAuswerter


def main():
    root = tk.Tk()
    InstagramAuswerter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
