"""Hilfe-Fenster (Desktop): zeigt die gemeinsamen Anleitungen aus core/anleitungen.py."""

import tkinter as tk
from tkinter import ttk

from core.anleitungen import ANLEITUNGEN, anleitung
from gui import theme


class HilfeFenster(tk.Toplevel):
    def __init__(self, parent: tk.Tk, start_id: str | None = None):
        super().__init__(parent)
        self.title("Anleitungen")
        self.geometry("1000x640")
        self.configure(bg=theme.HINTERGRUND)
        theme.kopfzeile(self, "❓ Anleitungen").pack(fill=tk.X, side=tk.TOP)

        aussen = ttk.Frame(self, padding=16)
        aussen.pack(fill=tk.BOTH, expand=True)

        # links: Themenliste
        self.liste = ttk.Treeview(aussen, show="tree", selectmode="browse")
        self.liste.column("#0", width=320)
        kategorien: dict[str, str] = {}
        for a in ANLEITUNGEN:
            if a.kategorie not in kategorien:
                kategorien[a.kategorie] = self.liste.insert("", tk.END, text=a.kategorie, open=True)
            self.liste.insert(kategorien[a.kategorie], tk.END, iid=a.id, text=a.titel)
        self.liste.pack(side=tk.LEFT, fill=tk.Y)
        self.liste.bind("<<TreeviewSelect>>", lambda _e: self._zeigen())

        # rechts: Inhalt
        rahmen = tk.Frame(aussen, bg=theme.RAND, bd=1)
        rahmen.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        self.text = tk.Text(rahmen, wrap="word", borderwidth=0, highlightthickness=0, bg=theme.KARTE, fg=theme.TEXT,
                            font=(theme.SCHRIFT, 11), padx=18, pady=16, spacing1=4, spacing3=6)
        self.text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.text.tag_config("titel", font=(theme.SCHRIFT, 16, "bold"), spacing3=8)
        self.text.tag_config("kurz", foreground=theme.TEXT_SCHWACH, spacing3=12)
        self.text.tag_config("nr", foreground=theme.PRIMAER_DUNKEL, font=(theme.SCHRIFT, 11, "bold"))
        self.text.tag_config("schritt", lmargin1=0, lmargin2=34)
        self.text.tag_config("tippkopf", font=(theme.SCHRIFT, 11, "bold"), foreground=theme.GRUEN_DUNKEL, spacing1=14)
        self.text.tag_config("tipp", foreground=theme.GRUEN_DUNKEL, lmargin1=10, lmargin2=26)

        erste = start_id if anleitung(start_id or "") else ANLEITUNGEN[0].id
        self.liste.selection_set(erste)
        self.liste.see(erste)

    def _zeigen(self):
        auswahl = self.liste.selection()
        a = anleitung(auswahl[0]) if auswahl else None
        if a is None:
            return
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, a.titel + "\n", "titel")
        self.text.insert(tk.END, a.kurz + "\n", "kurz")
        for i, schritt in enumerate(a.schritte, start=1):
            self.text.insert(tk.END, f"{i:>2}.  ", ("nr", "schritt"))
            self.text.insert(tk.END, schritt + "\n", "schritt")
        if a.tipps:
            self.text.insert(tk.END, "Tipps\n", "tippkopf")
            for tipp in a.tipps:
                self.text.insert(tk.END, f"💡 {tipp}\n", "tipp")
        self.text.config(state=tk.DISABLED)
