"""
Listen-Editor (Desktop): Follower/Following selbst eintippen, TXT-Dateien
laden und speichern, danach wie einen echten Export auswerten.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.plattform import PLATTFORM_TEXTE, Plattform
from core.txt_format import lese_txt, schreibe_txt
from gui import theme


class EditorFenster(tk.Toplevel):
    def __init__(self, parent: tk.Tk, plattform: Plattform, beim_auswerten,
                 follower: dict[str, str] | None = None, following: dict[str, str] | None = None):
        """
        beim_auswerten: Funktion (follower, following, label) -> None, die das
        Hauptfenster übergibt. So bleibt das Speichern an EINER Stelle.
        """
        super().__init__(parent)
        self.title(f"Listen-Editor ({PLATTFORM_TEXTE[plattform]})")
        self.geometry("940x660")
        self.configure(bg=theme.HINTERGRUND)
        self.plattform = plattform
        self._beim_auswerten = beim_auswerten

        theme.kopfzeile(self, "Listen-Editor").pack(fill=tk.X, side=tk.TOP)
        karte = ttk.Frame(self, style="Karte.TFrame", padding=16)
        karte.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        ttk.Label(karte, style="SchwachKarte.TLabel", wraplength=840, justify="left",
                  text="Ein Name pro Zeile. Erlaubt sind auch @namen, Profil-Links und „name;TT.MM.JJJJ“. "
                       "Zeilen mit # sind Kommentare. Mehrere Namen pro Zeile mit Komma trennen.").pack(anchor="w")

        spalten = ttk.Frame(karte, style="Karte.TFrame")
        spalten.pack(fill=tk.BOTH, expand=True, pady=(10, 10))
        self.felder: dict[str, tk.Text] = {}
        self.zaehler: dict[str, ttk.Label] = {}
        for i, (schluessel, titel, daten) in enumerate([("follower", "Follower – wer mir folgt", follower),
                                                        ("following", "Following – wem ich folge", following)]):
            spalte = ttk.Frame(spalten, style="Karte.TFrame")
            spalte.grid(row=0, column=i, sticky="nsew", padx=(0, 8) if i == 0 else (8, 0))
            kopf = ttk.Frame(spalte, style="Karte.TFrame")
            kopf.pack(fill=tk.X)
            ttk.Label(kopf, text=titel, style="Karte.TLabel", font=(theme.SCHRIFT, 10, "bold")).pack(side=tk.LEFT)
            self.zaehler[schluessel] = ttk.Label(kopf, text="", style="SchwachKarte.TLabel")
            self.zaehler[schluessel].pack(side=tk.LEFT, padx=8)
            knoepfe = ttk.Frame(spalte, style="Karte.TFrame")
            knoepfe.pack(fill=tk.X, pady=(4, 0))
            ttk.Button(knoepfe, text="📂 TXT laden", style="Dezent.TButton",
                       command=lambda s=schluessel: self._laden(s)).pack(side=tk.LEFT)
            ttk.Button(knoepfe, text="💾 Als TXT speichern", style="Dezent.TButton",
                       command=lambda s=schluessel, t=titel: self._speichern(s, t)).pack(side=tk.LEFT, padx=6)
            rahmen = tk.Frame(spalte, bg=theme.RAND, bd=1)
            rahmen.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
            text = tk.Text(rahmen, wrap="none", undo=True, height=16, font=("Consolas", 10), bg=theme.KARTE, fg=theme.TEXT,
                           borderwidth=0, highlightthickness=0, padx=8, pady=8)
            scroll = ttk.Scrollbar(rahmen, command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
            if daten:
                text.insert("1.0", schreibe_txt(daten, titel))
            text.bind("<<Modified>>", lambda _e, s=schluessel: self._zaehlen(s))
            self.felder[schluessel] = text
            self._zaehlen(schluessel)
        spalten.columnconfigure(0, weight=1)
        spalten.columnconfigure(1, weight=1)
        spalten.rowconfigure(0, weight=1)

        unten = ttk.Frame(karte, style="Karte.TFrame")
        unten.pack(fill=tk.X)
        ttk.Label(unten, text="Name der Auswertung:", style="Karte.TLabel").pack(side=tk.LEFT)
        self.label_var = tk.StringVar()
        ttk.Entry(unten, textvariable=self.label_var, width=30).pack(side=tk.LEFT, padx=8)
        ttk.Button(unten, text="Auswerten & speichern", style="Primaer.TButton",
                   command=self._auswerten).pack(side=tk.RIGHT)

    def _daten(self, schluessel: str) -> dict[str, str]:
        return lese_txt(self.felder[schluessel].get("1.0", tk.END))

    def _zaehlen(self, schluessel: str):
        feld = self.felder[schluessel]
        feld.edit_modified(False)            # sonst feuert <<Modified>> nur ein einziges Mal
        self.zaehler[schluessel].config(text=f"{len(self._daten(schluessel))} Namen")

    def _laden(self, schluessel: str):
        pfad = filedialog.askopenfilename(parent=self, title="Textdatei laden",
                                          filetypes=[("Textdateien", "*.txt *.csv"), ("Alle Dateien", "*.*")])
        if not pfad:
            return
        with open(pfad, "r", encoding="utf-8-sig", errors="ignore") as f:
            inhalt = f.read()
        feld = self.felder[schluessel]
        if feld.get("1.0", tk.END).strip():
            feld.insert(tk.END, "\n")
        feld.insert(tk.END, inhalt)
        self._zaehlen(schluessel)

    def _speichern(self, schluessel: str, titel: str):
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", initialfile=f"{schluessel}.txt",
                                            filetypes=[("Textdatei", "*.txt")])
        if pfad:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(schreibe_txt(self._daten(schluessel), f"{PLATTFORM_TEXTE[self.plattform]} {titel}"))

    def _auswerten(self):
        follower, following = self._daten("follower"), self._daten("following")
        if not follower and not following:
            messagebox.showinfo("Hinweis", "Bitte mindestens eine Liste ausfüllen.", parent=self)
            return
        self._beim_auswerten(follower, following, self.label_var.get().strip() or None)
        self.destroy()
