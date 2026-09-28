"""
Kommentar- und Like-Modus (Desktop).

Beide Fenster funktionieren wie der Entfolgen-Modus: Startseite mit
Übersicht und Filter -> ein Eintrag pro Bildschirm -> Zusammenfassung mit
Export. Die Logik steckt in core/aktivitaet.py.
"""

import sqlite3
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from core import history_store
from core.aktivitaet import (AKTIVITAET_URL, BEHALTEN, ENTFERNEN, FILTER_ALLE, FILTER_KRITISCH, FILTER_RISKANT,
                             KOMMENTAR, LIKE, AktivitaetAblauf, alle_zum_entfernen, kommentar_statistik,
                             like_statistik, such_link)
from core.export import aktivitaet_bericht
from gui import theme


class _DurchgangFenster(tk.Toplevel):
    """Gemeinsamer Rahmen: Seitenwechsel, Wizard, Zurück, Zusammenfassung, Export."""
    ART = KOMMENTAR
    TITEL = ""
    KNOPF_ENTFERNEN = "🗑 Entfernen"

    def __init__(self, parent: tk.Tk, db: sqlite3.Connection, besitzer: str):
        super().__init__(parent)
        self.title(self.TITEL)
        self.geometry("820x660")
        self.minsize(640, 540)
        self.configure(bg=theme.HINTERGRUND)
        self.db, self.besitzer = db, besitzer
        self.ablauf: AktivitaetAblauf | None = None
        theme.kopfzeile(self, self.TITEL).pack(fill=tk.X, side=tk.TOP)
        self.aussen = ttk.Frame(self, padding=18)
        self.aussen.pack(fill=tk.BOTH, expand=True)
        self.startseite()

    # ---- Helfer
    def _leeren(self):
        for tastenkuerzel in ("<l>", "<b>", "<e>", "<BackSpace>"):
            self.unbind(tastenkuerzel)
        for w in self.aussen.winfo_children():
            w.destroy()

    def _karte(self) -> ttk.Frame:
        karte = ttk.Frame(self.aussen, style="Karte.TFrame", padding=20)
        karte.pack(fill=tk.BOTH, expand=True)
        return karte

    @staticmethod
    def _titel(karte, text):
        ttk.Label(karte, text=text, style="Karte.TLabel", font=(theme.SCHRIFT, 13, "bold")).pack(anchor="w", pady=(0, 8))

    @staticmethod
    def _hinweis(karte, text):
        ttk.Label(karte, text=text, style="SchwachKarte.TLabel", wraplength=680, justify="left").pack(anchor="w", pady=(0, 8))

    def _vorher(self) -> dict[str, str]:
        return history_store.aktivitaet_entscheidungen_laden(self.db, self.besitzer, self.ART)

    # ---- von Unterklassen
    def startseite(self):
        raise NotImplementedError

    def eintrag_zeigen(self, karte, eintrag):
        raise NotImplementedError

    # ---- Wizard
    def starten(self, ablauf: AktivitaetAblauf):
        self.ablauf = ablauf
        if not ablauf.reihenfolge:
            messagebox.showinfo("Nichts zu tun", "Mit dieser Auswahl gibt es keine offenen Einträge.", parent=self)
            return
        self.wizard()

    def wizard(self):
        if self.ablauf.ist_fertig():
            self.zusammenfassung()
            return
        self._leeren()
        karte = self._karte()
        erledigt, gesamt = self.ablauf.fortschritt()
        ttk.Label(karte, text=f"{erledigt} von {gesamt} bearbeitet  ·  Tasten: L = {self.KNOPF_ENTFERNEN.split()[-1]}, "
                              f"B = Behalten, Rücktaste = Zurück", style="SchwachKarte.TLabel").pack(anchor="w")
        ttk.Progressbar(karte, maximum=max(gesamt, 1), value=erledigt).pack(fill=tk.X, pady=(4, 14))
        eintrag = self.ablauf.aktueller()
        self.eintrag_zeigen(karte, eintrag)

        knoepfe = ttk.Frame(karte, style="Karte.TFrame")
        knoepfe.pack(pady=(14, 6))
        ttk.Button(knoepfe, text=self.KNOPF_ENTFERNEN, style="Gefahr.TButton",
                   command=lambda: self._entscheiden(ENTFERNEN)).grid(row=0, column=0, padx=5)
        ttk.Button(knoepfe, text="✓ Behalten", style="Erfolg.TButton",
                   command=lambda: self._entscheiden(BEHALTEN)).grid(row=0, column=1, padx=5)
        unten = ttk.Frame(karte, style="Karte.TFrame")
        unten.pack()
        zurueck = ttk.Button(unten, text="← Zurück", style="Dezent.TButton", command=self._zurueck)
        zurueck.pack(side=tk.LEFT, padx=4)
        if not self.ablauf.kann_zurueck():
            zurueck.state(["disabled"])
        link = such_link(eintrag)
        if link:
            ttk.Button(unten, text="🔗 Öffnen", style="Dezent.TButton",
                       command=lambda: webbrowser.open(link)).pack(side=tk.LEFT, padx=4)
        ttk.Button(unten, text="Aktivitätsseite", style="Dezent.TButton",
                   command=lambda: webbrowser.open(AKTIVITAET_URL[self.ART])).pack(side=tk.LEFT, padx=4)
        ttk.Button(unten, text="Beenden", style="Dezent.TButton", command=self.zusammenfassung).pack(side=tk.LEFT, padx=4)
        self.bind("<l>", lambda _e: self._entscheiden(ENTFERNEN))
        self.bind("<b>", lambda _e: self._entscheiden(BEHALTEN))
        self.bind("<BackSpace>", lambda _e: self._zurueck())

    def _entscheiden(self, wert: str):
        if self.ablauf and not self.ablauf.ist_fertig():
            self.ablauf.entscheide(self.db, wert)
            self.wizard()

    def _zurueck(self):
        if self.ablauf and self.ablauf.zurueck(self.db) is not None:
            self.wizard()

    def zusammenfassung(self):
        self._leeren()
        karte = self._karte()
        zu_entfernen = alle_zum_entfernen(self.db, self.besitzer, self.ART)
        self._titel(karte, f"✅ {len(zu_entfernen)} zum Entfernen markiert (alle Durchgänge)")
        self._hinweis(karte, "Das Programm löscht nichts selbst. Öffne die Einträge über die Links oder gesammelt auf der "
                             "Instagram-Aktivitätsseite (App: Profil → Menü → Deine Aktivität → Interaktionen) und "
                             "lösche sie dort – dort geht auch Mehrfachauswahl nach Datum.")
        rahmen = tk.Frame(karte, bg=theme.RAND, bd=1)
        rahmen.pack(fill=tk.BOTH, expand=True, pady=(4, 10))
        text = tk.Text(rahmen, wrap="word", height=14, borderwidth=0, highlightthickness=0, bg=theme.KARTE,
                       fg=theme.TEXT, font=(theme.SCHRIFT, 10), padx=10, pady=8)
        text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        bericht = aktivitaet_bericht(self.ART, zu_entfernen)
        text.insert("1.0", bericht)
        text.config(state=tk.DISABLED)
        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w")
        ttk.Button(zeile, text="⬇ Als Textdatei speichern", style="Primaer.TButton",
                   command=lambda: self._speichern(bericht)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zeile, text="Instagram-Aktivitätsseite öffnen", style="Dezent.TButton",
                   command=lambda: webbrowser.open(AKTIVITAET_URL[self.ART])).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zeile, text="Zur Übersicht", style="Dezent.TButton", command=self.startseite).pack(side=tk.LEFT)

    def _speichern(self, bericht: str):
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", filetypes=[("Textdatei", "*.txt")],
                                            initialfile=f"{self.ART}e_zum_entfernen.txt")
        if pfad:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(bericht)


class KommentareFenster(_DurchgangFenster):
    ART = KOMMENTAR
    TITEL = "Kommentar-Modus"
    KNOPF_ENTFERNEN = "🗑 Löschen"

    def startseite(self):
        self._leeren()
        karte = self._karte()
        kommentare = history_store.kommentare_laden(self.db, self.besitzer)
        if not kommentare:
            self._titel(karte, "Noch keine Kommentare importiert")
            self._hinweis(karte, "Lade einen Instagram-Export, in dem „Kommentare“ enthalten ist (Anleitung: "
                                 "„Kommentare & Likes“). Das Programm erkennt ihn automatisch.")
            return
        stat = kommentar_statistik(kommentare)
        vorher = self._vorher()
        self._titel(karte, f"💬 {len(kommentare)} eigene Kommentare")
        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w", pady=(0, 10))
        for stufe, text in (("kritisch", "kritisch"), ("prüfen", "prüfen"), ("harmlos", "harmlos")):
            ttk.Label(zeile, text=f"{stat[stufe]} {text}", style=f"Stufe.{stufe}.TLabel").pack(side=tk.LEFT, padx=(0, 18))
        ttk.Label(zeile, text=f"· {len(vorher)} schon entschieden", style="SchwachKarte.TLabel").pack(side=tk.LEFT)
        self._hinweis(karte, "Die Einstufung beruht auf Wortlisten (Beleidigungen, Politik, Gewalt …), Länge und "
                             "Schreibstil – keine KI. Emojis und kurze Kommentare gelten als harmlos, lange Texte werden "
                             "immer angezeigt. Du entscheidest bei jedem Kommentar selbst.")
        self.filter_var = tk.StringVar(value=FILTER_RISKANT)
        for wert, text in ((FILTER_KRITISCH, "Nur kritische (Löschen empfohlen)"),
                           (FILTER_RISKANT, "Kritische + zu prüfende (empfohlen)"),
                           (FILTER_ALLE, "Alle Kommentare nacheinander")):
            ttk.Radiobutton(karte, text=text, value=wert, variable=self.filter_var,
                            style="Karte.TRadiobutton").pack(anchor="w")
        self.erneut_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(karte, text="Schon entschiedene Kommentare erneut zeigen", variable=self.erneut_var,
                        style="Karte.TCheckbutton").pack(anchor="w", pady=(8, 0))
        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w", pady=(16, 0))
        ttk.Button(zeile, text="Start", style="Primaer.TButton", command=lambda: self.starten(
            AktivitaetAblauf.fuer_kommentare(self.besitzer, kommentare, self._vorher(), self.filter_var.get(),
                                             self.erneut_var.get()))).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zeile, text="Liste „Zum Löschen“ anzeigen", style="Dezent.TButton",
                   command=self.zusammenfassung).pack(side=tk.LEFT)

    def eintrag_zeigen(self, karte, k):
        b = self.ablauf.bewertung(k)
        kopf = ttk.Frame(karte, style="Karte.TFrame")
        kopf.pack(fill=tk.X)
        ttk.Label(kopf, text=f"{b.stufe.upper()} · {b.empfehlung}", style=f"Stufe.{b.stufe}.TLabel").pack(side=tk.LEFT)
        ttk.Label(kopf, text=f"{k.datum} · {k.quelle} von @{k.medien_owner or '?'}",
                  style="SchwachKarte.TLabel").pack(side=tk.RIGHT)
        ttk.Label(karte, text="Warum: " + "; ".join(b.gruende), style="SchwachKarte.TLabel",
                  wraplength=680, justify="left").pack(anchor="w", pady=(4, 8))
        rahmen = tk.Frame(karte, bg=theme.RAND, bd=1)
        rahmen.pack(fill=tk.BOTH, expand=True)
        text = tk.Text(rahmen, wrap="word", height=7, borderwidth=0, highlightthickness=0, bg=theme.KARTE,
                       fg=theme.TEXT, font=(theme.SCHRIFT, 12), padx=12, pady=10)
        text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        text.insert("1.0", k.text)
        text.tag_config("treffer", background="#fde68a")
        for wort in b.treffer:                                   # gefundene Wörter gelb markieren
            start = "1.0"
            while pos := text.search(wort, start, nocase=True, stopindex=tk.END):
                text.tag_add("treffer", pos, f"{pos}+{len(wort)}c")
                start = f"{pos}+{len(wort)}c"
        text.config(state=tk.DISABLED)
        link = ttk.Label(karte, text=such_link(k) or "kein Link im Export", style="Hinweis.TLabel", cursor="hand2")
        link.pack(anchor="w", pady=(6, 0))
        link.bind("<Button-1>", lambda _e: such_link(k) and webbrowser.open(such_link(k)))
        ttk.Button(karte, text="Kommentartext kopieren (zum Suchen)", style="Dezent.TButton",
                   command=lambda: (self.clipboard_clear(), self.clipboard_append(k.text))).pack(anchor="w", pady=(6, 0))


class LikesFenster(_DurchgangFenster):
    ART = LIKE
    TITEL = "Like-Modus"
    KNOPF_ENTFERNEN = "💔 Like entfernen"

    def startseite(self):
        self._leeren()
        karte = self._karte()
        likes = history_store.likes_laden(self.db, self.besitzer)
        if not likes:
            self._titel(karte, "Noch keine Likes importiert")
            self._hinweis(karte, "Lade einen Instagram-Export, in dem „Likes“ enthalten ist. Das Programm erkennt ihn automatisch.")
            return
        self._titel(karte, f"❤️ {len(likes)} Likes – wem du am meisten Likes gibst")
        self._hinweis(karte, "Wähle einen Account, um nur dessen Likes durchzugehen (z. B. bei einem Ex), oder gehe alle durch.")
        rahmen = ttk.Frame(karte, style="Karte.TFrame")
        rahmen.pack(fill=tk.BOTH, expand=True)
        baum = ttk.Treeview(rahmen, columns=("anzahl", "letzter"), show="tree headings", height=10, selectmode="browse")
        baum.heading("#0", text="Account")
        baum.heading("anzahl", text="Likes")
        baum.heading("letzter", text="letzter Like")
        baum.column("anzahl", width=80, anchor="e")
        baum.column("letzter", width=150, anchor="center")
        for name, anzahl, letzter in like_statistik(likes):
            baum.insert("", tk.END, iid=name, text=name, values=(anzahl, letzter))
        scroll = ttk.Scrollbar(rahmen, command=baum.yview)
        baum.configure(yscrollcommand=scroll.set)
        baum.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.erneut_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(karte, text="Schon entschiedene Likes erneut zeigen", variable=self.erneut_var,
                        style="Karte.TCheckbutton").pack(anchor="w", pady=(8, 0))
        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w", pady=(10, 0))

        def start(nur_auswahl: bool):
            account = baum.selection()[0] if nur_auswahl and baum.selection() else None
            if nur_auswahl and not account:
                messagebox.showinfo("Hinweis", "Bitte zuerst einen Account in der Liste wählen.", parent=self)
                return
            self.starten(AktivitaetAblauf.fuer_likes(self.besitzer, likes, self._vorher(), account, self.erneut_var.get()))

        ttk.Button(zeile, text="Likes bei gewähltem Account", style="Primaer.TButton",
                   command=lambda: start(True)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zeile, text="Alle Likes durchgehen", style="Dezent.TButton",
                   command=lambda: start(False)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zeile, text="Liste „Zum Entfernen“", style="Dezent.TButton",
                   command=self.zusammenfassung).pack(side=tk.LEFT)

    def eintrag_zeigen(self, karte, like):
        ttk.Label(karte, text=f"@{like.owner or '?'}", style="Karte.TLabel",
                  font=(theme.SCHRIFT, 22, "bold")).pack(pady=(10, 4))
        ttk.Label(karte, text=f"{like.art} geliked am {like.datum}", style="SchwachKarte.TLabel").pack()
        link = ttk.Label(karte, text=such_link(like) or "kein Link im Export", style="Hinweis.TLabel", cursor="hand2")
        link.pack(pady=(10, 0))
        link.bind("<Button-1>", lambda _e: such_link(like) and webbrowser.open(such_link(like)))
