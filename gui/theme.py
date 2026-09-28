"""
Gemeinsames visuelles Theme für die Desktop-Oberfläche.

Ziel: ein einheitliches, modernes Erscheinungsbild statt Standard-Tk-Grau,
ohne eine zusätzliche Abhängigkeit (z. B. ttkthemes) ins Projekt zu holen.
Basiert auf ttk mit dem plattformunabhängigen "clam"-Theme, weil sich
darüber (anders als bei den nativen Themes) Farben zuverlässig anpassen
lassen.
"""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

# Farbpalette (angelehnt an das Web-Design, siehe web/static/style.css)
HINTERGRUND = "#f0f2f5"
KARTE = "#ffffff"
RAND = "#e4e6eb"
TEXT = "#1c1e21"
TEXT_SCHWACH = "#65676b"

PRIMAER = "#3897f0"
PRIMAER_DUNKEL = "#1877c9"
GRUEN = "#22c55e"
GRUEN_DUNKEL = "#16a34a"
ROT = "#ef4444"
ROT_DUNKEL = "#dc2626"
GELB = "#f59e0b"
GELB_DUNKEL = "#d97706"
DUNKEL = "#1c1e21"

SCHRIFT = "Segoe UI"  # unter Mac/Linux fällt Tk automatisch auf eine Systemschrift zurück


def anwenden(root: tk.Tk) -> ttk.Style:
    """Wendet das Theme auf das übergebene Tk-Fenster an und gibt das Style-Objekt zurück."""
    root.configure(bg=HINTERGRUND)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure("TFrame", background=HINTERGRUND)
    style.configure("Karte.TFrame", background=KARTE, relief="flat")
    style.configure("Kopfzeile.TFrame", background=DUNKEL)

    style.configure("TLabel", background=HINTERGRUND, foreground=TEXT, font=(SCHRIFT, 10))
    style.configure("Karte.TLabel", background=KARTE, foreground=TEXT, font=(SCHRIFT, 10))
    style.configure("Titel.TLabel", background=HINTERGRUND, foreground=TEXT, font=(SCHRIFT, 16, "bold"))
    style.configure("Marke.TLabel", background=DUNKEL, foreground="#e6683c", font=(SCHRIFT, 13, "bold"))
    style.configure("Schwach.TLabel", background=HINTERGRUND, foreground=TEXT_SCHWACH, font=(SCHRIFT, 9))
    style.configure("SchwachKarte.TLabel", background=KARTE, foreground=TEXT_SCHWACH, font=(SCHRIFT, 9))
    style.configure("Erfolg.TLabel", background=HINTERGRUND, foreground=GRUEN_DUNKEL, font=(SCHRIFT, 10, "bold"))

    def knopf_stil(name: str, bg: str, bg_aktiv: str, fg: str = "white"):
        style.configure(
            name, background=bg, foreground=fg, borderwidth=0,
            focusthickness=0, padding=(14, 8), font=(SCHRIFT, 10, "bold"),
        )
        style.map(name, background=[("active", bg_aktiv), ("disabled", RAND)],
                  foreground=[("disabled", TEXT_SCHWACH)])

    knopf_stil("Primaer.TButton", PRIMAER, PRIMAER_DUNKEL)
    knopf_stil("Erfolg.TButton", GRUEN, GRUEN_DUNKEL)
    knopf_stil("Gefahr.TButton", ROT, ROT_DUNKEL)
    knopf_stil("Warnung.TButton", GELB, GELB_DUNKEL, fg="#3a2a00")
    knopf_stil("Dezent.TButton", RAND, "#d5d8dc", fg=TEXT)

    style.configure("Hinweis.TLabel", background=KARTE, foreground=PRIMAER_DUNKEL, font=(SCHRIFT, 9, "bold"))
    style.configure("Karte.TCheckbutton", background=KARTE, foreground=TEXT, font=(SCHRIFT, 10))
    style.map("Karte.TCheckbutton", background=[("active", KARTE)])
    style.configure("Karte.TRadiobutton", background=KARTE, foreground=TEXT, font=(SCHRIFT, 10))
    style.map("Karte.TRadiobutton", background=[("active", KARTE)])

    style.configure("TNotebook", background=HINTERGRUND, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 6), font=(SCHRIFT, 10, "bold"), background=RAND, foreground=TEXT)
    style.map("TNotebook.Tab", background=[("selected", KARTE)])
    style.configure("Treeview", rowheight=26, font=(SCHRIFT, 10), background=KARTE, fieldbackground=KARTE,
                    foreground=TEXT, borderwidth=0)
    style.configure("Treeview.Heading", font=(SCHRIFT, 9, "bold"), background=RAND, foreground=TEXT)
    style.map("Treeview", background=[("selected", PRIMAER)], foreground=[("selected", "white")])
    style.configure("TEntry", padding=6)

    style.configure("Stufe.kritisch.TLabel", background=KARTE, foreground=ROT_DUNKEL, font=(SCHRIFT, 11, "bold"))
    style.configure("Stufe.prüfen.TLabel", background=KARTE, foreground=GELB_DUNKEL, font=(SCHRIFT, 11, "bold"))
    style.configure("Stufe.harmlos.TLabel", background=KARTE, foreground=GRUEN_DUNKEL, font=(SCHRIFT, 11, "bold"))
    style.configure("Kopf.TRadiobutton", background=DUNKEL, foreground="#e4e6eb", font=(SCHRIFT, 10, "bold"))
    style.map("Kopf.TRadiobutton", background=[("active", DUNKEL)], foreground=[("selected", "#ffffff")])

    style.configure("TScrollbar", background=RAND, troughcolor=HINTERGRUND, borderwidth=0)

    return style


LOGO_DATEI = Path(__file__).resolve().parent / "logo.png"
_logo_cache: dict[int, tk.PhotoImage] = {}


def logo(groesse: int = 28) -> tk.PhotoImage | None:
    """Das App-Logo als Tk-Bild (256 px, verkleinert per subsample). None, wenn die Datei fehlt."""
    if groesse not in _logo_cache:
        try:
            bild = tk.PhotoImage(file=str(LOGO_DATEI))
            faktor = max(1, bild.width() // groesse)
            _logo_cache[groesse] = bild.subsample(faktor, faktor) if faktor > 1 else bild
        except (tk.TclError, RuntimeError):
            return None
    return _logo_cache[groesse]


def fenster_icon(fenster: tk.Misc) -> None:
    """Setzt das Logo als Fenster-/Taskleisten-Symbol."""
    bild = logo(64)
    if bild is not None:
        try:
            fenster.iconphoto(True, bild)
        except tk.TclError:
            pass


def kopfzeile(parent: tk.Widget, titel: str = "Follower-Auswertung") -> ttk.Frame:
    """Erzeugt die dunkle Titelleiste mit Logo und 'Marken'-Schriftzug, wie im Web-Design."""
    leiste = ttk.Frame(parent, style="Kopfzeile.TFrame")
    bild = logo(28)
    ttk.Label(leiste, text=" " + titel, image=bild, compound="left" if bild else "none",
              style="Marke.TLabel").pack(side=tk.LEFT, padx=16, pady=8)
    return leiste


def mausrad_aktivieren(root: tk.Tk) -> None:
    """
    Mausrad scrollt immer die Liste UNTER dem Mauszeiger.

    Hintergrund des Fehlers "bei den Followern kann man nicht scrollen":
    Unter Windows schickt Tk Mausrad-Ereignisse je nach Version an das
    Widget mit dem Tastatur-Fokus – nicht an das, über dem die Maus steht.
    War zuletzt die linke Liste angeklickt, bewegte sich die rechte nicht.
    """
    def scrollen(event):
        ziel = root.winfo_containing(event.x_root, event.y_root)
        if ziel is None or ziel is event.widget:
            return                                   # Tk hat es schon richtig zugestellt
        while ziel is not None and not hasattr(ziel, "yview_scroll"):
            ziel = ziel.master                       # nach oben suchen: Listbox, Text, Treeview, Canvas
        if ziel is None:
            return
        if getattr(event, "num", None) in (4, 5):    # Linux
            schritte = -3 if event.num == 4 else 3
        else:
            schritte = -1 * (event.delta // 120 or (1 if event.delta > 0 else -1)) * 3
        try:
            ziel.yview_scroll(schritte, "units")
        except tk.TclError:
            pass

    root.bind_all("<MouseWheel>", scrollen, add="+")
    root.bind_all("<Button-4>", scrollen, add="+")
    root.bind_all("<Button-5>", scrollen, add="+")


def scrollbarer_bereich(parent: tk.Widget, breite: int = 380) -> ttk.Frame:
    """Ein senkrecht scrollbarer Bereich (Canvas + Innen-Frame), z. B. für die linke Knopf-Spalte."""
    rahmen = ttk.Frame(parent)
    leinwand = tk.Canvas(rahmen, width=breite, highlightthickness=0, bg=HINTERGRUND, borderwidth=0)
    balken = ttk.Scrollbar(rahmen, orient="vertical", command=leinwand.yview)
    innen = ttk.Frame(leinwand)
    innen.bind("<Configure>", lambda _e: leinwand.configure(scrollregion=leinwand.bbox("all")))
    fenster_id = leinwand.create_window((0, 0), window=innen, anchor="nw")
    leinwand.bind("<Configure>", lambda e: leinwand.itemconfigure(fenster_id, width=e.width))
    leinwand.configure(yscrollcommand=balken.set)
    leinwand.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    balken.pack(side=tk.RIGHT, fill=tk.Y)
    innen.rahmen = rahmen                            # damit der Aufrufer den äußeren Rahmen packen kann
    return innen
