"""Freunde-Liste (Desktop): gegenseitige Follows + manuell eingetragene Freunde."""

import sqlite3
import tkinter as tk
import webbrowser
from tkinter import filedialog, simpledialog, ttk

from core import history_store
from core.export import freunde_csv, namensliste_text
from core.freunde import QUELLE_MANUELL, freunde_ermitteln
from core.models import PersonenListe
from core.plattform import PLATTFORM_TEXTE, Plattform, profil_url
from core.parser import usernames_aus_text
from gui import theme

BESITZER = history_store.LOKAL


class FreundeFenster(tk.Toplevel):
    def __init__(self, parent: tk.Tk, db_verbindung: sqlite3.Connection, snapshot_id: int,
                 besitzer: str = BESITZER, plattform: Plattform = Plattform.INSTAGRAM):
        super().__init__(parent)
        self.besitzer, self.plattform = besitzer, plattform
        self.title(f"Freunde-Liste ({PLATTFORM_TEXTE[plattform]})")
        self.geometry("840x580")
        self.configure(bg=theme.HINTERGRUND)
        self.db = db_verbindung
        self.snapshot = history_store.snapshot_laden(self.db, snapshot_id, self.besitzer)

        theme.kopfzeile(self, "Freunde-Liste").pack(fill=tk.X, side=tk.TOP)
        karte = ttk.Frame(self, style="Karte.TFrame", padding=16)
        karte.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        self.lbl_info = ttk.Label(karte, style="SchwachKarte.TLabel", wraplength=660, justify="left")
        self.lbl_info.pack(anchor="w", pady=(0, 8))

        rahmen = ttk.Frame(karte, style="Karte.TFrame")
        rahmen.pack(fill=tk.BOTH, expand=True)
        self.baum = ttk.Treeview(rahmen, columns=("quelle", "folgt", "folge"), show="tree headings")
        for spalte, text, breite in (("#0", "Account", 200), ("quelle", "Quelle", 170),
                                     ("folgt", "folgt mir seit", 120), ("folge", "ich folge seit", 120)):
            self.baum.heading(spalte, text=text)
            self.baum.column(spalte, width=breite)
        scroll = ttk.Scrollbar(rahmen, command=self.baum.yview)
        self.baum.configure(yscrollcommand=scroll.set)
        self.baum.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.baum.bind("<Double-Button-1>", lambda _e: self._profil())

        knoepfe = ttk.Frame(karte, style="Karte.TFrame")
        knoepfe.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(knoepfe, text="+ Freund hinzufügen", style="Erfolg.TButton",
                   command=self._hinzufuegen).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(knoepfe, text="Manuellen Eintrag entfernen", style="Dezent.TButton",
                   command=self._entfernen).pack(side=tk.LEFT)
        ttk.Button(knoepfe, text="⬇ CSV (Excel)", style="Primaer.TButton",
                   command=lambda: self._export("csv")).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(knoepfe, text="⬇ Text", style="Dezent.TButton",
                   command=lambda: self._export("txt")).pack(side=tk.RIGHT)
        self._laden()

    def _laden(self):
        manuell = history_store.liste_laden(self.db, self.besitzer, PersonenListe.FREUNDE)
        self.freunde = freunde_ermitteln(self.snapshot.follower, self.snapshot.following, manuell)
        self.baum.delete(*self.baum.get_children())
        for f in self.freunde:
            self.baum.insert("", tk.END, iid=f.username, text=f.username,
                             values=(f.quelle, f.folgt_mir_seit, f.ich_folge_seit))
        gegenseitig = sum(1 for f in self.freunde if f.quelle != QUELLE_MANUELL)
        self.lbl_info.config(text=f"{len(self.freunde)} Freunde – {gegenseitig} gegenseitige Follows, "
                                  f"{len(self.freunde) - gegenseitig} nur manuell eingetragen. "
                                  f"Basis: {self.snapshot.label}. Doppelklick öffnet das Profil.")

    def _hinzufuegen(self):
        text = simpledialog.askstring("Freund hinzufügen", "Nutzername(n), mit Komma getrennt:", parent=self)
        namen = usernames_aus_text(text or "")
        if namen:
            history_store.liste_hinzufuegen(self.db, self.besitzer, PersonenListe.FREUNDE, namen)
            self._laden()

    def _entfernen(self):
        for name in self.baum.selection():
            history_store.liste_entfernen(self.db, self.besitzer, PersonenListe.FREUNDE, name)
        self._laden()

    def _profil(self):
        auswahl = self.baum.selection()
        if auswahl:
            webbrowser.open(profil_url(self.plattform, auswahl[0]))

    def _export(self, format: str):
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=f".{format}", initialfile=f"freunde.{format}",
                                            filetypes=[("CSV", "*.csv")] if format == "csv" else [("Text", "*.txt")])
        if not pfad:
            return
        inhalt = freunde_csv(self.freunde) if format == "csv" else \
            namensliste_text("Freunde", [f.username for f in self.freunde])
        with open(pfad, "w", encoding="utf-8-sig" if format == "csv" else "utf-8", newline="") as f:
            f.write(inhalt)
