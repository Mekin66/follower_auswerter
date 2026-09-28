"""
Fenster "Meine Listen" (Desktop): Freunde (manuell), Von mir blockiert,
Hat mich blockiert, sowie alle dauerhaften Markierungen aus dem
Entfolgen-Modus (ändern/entfernen).
"""

import sqlite3
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from core import history_store
from core.export import namensliste_text
from core.models import ENTSCHEIDUNG_TEXTE, LISTEN_TEXTE, Entscheidung, PersonenListe
from core.parser import usernames_aus_text
from core.plattform import PLATTFORM_TEXTE, Plattform, profil_url
from gui import theme

BESITZER = history_store.LOKAL


class ListenFenster(tk.Toplevel):
    def __init__(self, parent: tk.Tk, db_verbindung: sqlite3.Connection, start_liste: str | None = None,
                 vorschlaege: list[str] | None = None, besitzer: str = BESITZER,
                 plattform: Plattform = Plattform.INSTAGRAM):
        super().__init__(parent)
        self.besitzer, self.plattform = besitzer, plattform
        self.title(f"Meine Listen ({PLATTFORM_TEXTE[plattform]})")
        self.geometry("900x620")
        self.minsize(560, 460)
        self.configure(bg=theme.HINTERGRUND)
        self.db = db_verbindung

        theme.kopfzeile(self, "Meine Listen").pack(fill=tk.X, side=tk.TOP)
        aussen = ttk.Frame(self, padding=16)
        aussen.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(aussen)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._listboxen: dict[PersonenListe, tk.Listbox] = {}
        self._eingaben: dict[PersonenListe, ttk.Entry] = {}
        self._filter: dict[str, tk.StringVar] = {}
        self._tabs: dict[str, ttk.Frame] = {}
        for liste in PersonenListe:
            self._tabs[liste.value] = self._listen_tab(liste)
        self._tabs["markierungen"] = self._markierungen_tab()

        if start_liste in self._tabs:
            self.notebook.select(self._tabs[start_liste])
        if vorschlaege and start_liste in {pl.value for pl in PersonenListe}:
            self._eingaben[PersonenListe(start_liste)].insert(0, ", ".join(vorschlaege))
        self._alles_neu_laden()

    # ------------------------------------------------------------ Personen-Listen
    def _listen_tab(self, liste: PersonenListe) -> ttk.Frame:
        tab = ttk.Frame(self.notebook, style="Karte.TFrame", padding=16)
        self.notebook.add(tab, text=LISTEN_TEXTE[liste])

        ttk.Label(tab, text="Nutzernamen oder Profil-Links (mehrere mit Komma trennen):",
                  style="SchwachKarte.TLabel").pack(anchor="w")
        zeile = ttk.Frame(tab, style="Karte.TFrame")
        zeile.pack(fill=tk.X, pady=(4, 12))
        eingabe = ttk.Entry(zeile, font=(theme.SCHRIFT, 10))
        eingabe.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        eingabe.bind("<Return>", lambda _e: self._hinzufuegen(liste))
        ttk.Button(zeile, text="Hinzufügen", style="Primaer.TButton",
                   command=lambda: self._hinzufuegen(liste)).pack(side=tk.LEFT)
        self._eingaben[liste] = eingabe

        self._filter[liste.value] = self._filterzeile(tab, liste.value)

        rahmen = tk.Frame(tab, bg=theme.RAND, bd=1)
        rahmen.pack(fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(rahmen)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(rahmen, font=(theme.SCHRIFT, 10), yscrollcommand=scroll.set, selectmode=tk.EXTENDED,
                        bg=theme.KARTE, fg=theme.TEXT, borderwidth=0, highlightthickness=0,
                        selectbackground=theme.PRIMAER, activestyle="none")
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 1), pady=1)
        scroll.config(command=lb.yview)
        lb.bind("<Double-Button-1>", lambda _e: self._profil(lb))
        self._listboxen[liste] = lb

        knoepfe = ttk.Frame(tab, style="Karte.TFrame")
        knoepfe.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(knoepfe, text="Alle", style="Dezent.TButton",
                   command=lambda: lb.selection_set(0, tk.END)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(knoepfe, text="Keine", style="Dezent.TButton",
                   command=lambda: lb.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(knoepfe, text="Ausgewählte entfernen", style="Gefahr.TButton",
                   command=lambda: self._entfernen(liste)).pack(side=tk.LEFT, padx=(0, 6))

        # "Verschieben/Kopieren nach …" als Aufklapp-Menü für die Auswahl
        ziel_knopf = ttk.Menubutton(knoepfe, text="Verschieben / Kopieren …", style="Dezent.TButton")
        menue = tk.Menu(ziel_knopf, tearoff=False)
        for ziel in PersonenListe:
            if ziel != liste:
                menue.add_command(label=f"Verschieben nach „{LISTEN_TEXTE[ziel]}“",
                                  command=lambda z=ziel: self._uebertragen(liste, z, verschieben=True))
                menue.add_command(label=f"Kopieren nach „{LISTEN_TEXTE[ziel]}“",
                                  command=lambda z=ziel: self._uebertragen(liste, z, verschieben=False))
        ziel_knopf["menu"] = menue
        ziel_knopf.pack(side=tk.LEFT)

        ttk.Button(knoepfe, text="⬇ Exportieren", style="Dezent.TButton",
                   command=lambda: self._exportieren(liste)).pack(side=tk.RIGHT)
        return tab

    def _filterzeile(self, tab: ttk.Frame, schluessel: str) -> tk.StringVar:
        """Suchfeld + Hinweis zur Mehrfachauswahl. Tippen filtert die Liste sofort."""
        zeile = ttk.Frame(tab, style="Karte.TFrame")
        zeile.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(zeile, text="Filter:", style="SchwachKarte.TLabel").pack(side=tk.LEFT)
        var = tk.StringVar()
        ttk.Entry(zeile, textvariable=var, width=22).pack(side=tk.LEFT, padx=(6, 12))
        var.trace_add("write", lambda *_: self._alles_neu_laden())
        ttk.Label(zeile, text="Mehrfach: Strg/Cmd+Klick einzeln, Umschalt+Klick Bereich",
                  style="SchwachKarte.TLabel").pack(side=tk.LEFT)
        return var

    def _gefiltert(self, schluessel: str, namen):
        text = self._filter[schluessel].get().strip().lower() if schluessel in self._filter else ""
        return [n for n in namen if text in (n if isinstance(n, str) else n[0])]

    @staticmethod
    def _ausgewaehlt(lb: tk.Listbox) -> list[str]:
        return [lb.get(i).split("  ·")[0].strip() for i in lb.curselection()]

    def _uebertragen(self, quelle: PersonenListe, ziel: PersonenListe, verschieben: bool):
        namen = self._ausgewaehlt(self._listboxen[quelle])
        if not namen:
            messagebox.showinfo("Hinweis", "Bitte zuerst Einträge auswählen.", parent=self)
            return
        history_store.liste_hinzufuegen(self.db, self.besitzer, ziel, namen)
        if verschieben:
            history_store.liste_mehrere_entfernen(self.db, self.besitzer, quelle, namen)
        self._alles_neu_laden()

    def _hinzufuegen(self, liste: PersonenListe):
        eingabe = self._eingaben[liste]
        namen = usernames_aus_text(eingabe.get())
        if not namen:
            return
        neu = history_store.liste_hinzufuegen(self.db, self.besitzer, liste, namen)
        eingabe.delete(0, tk.END)
        self._alles_neu_laden()
        if neu < len(namen):
            messagebox.showinfo("Hinweis", f"{neu} neu hinzugefügt, {len(namen) - neu} waren schon in der Liste.",
                                parent=self)

    def _entfernen(self, liste: PersonenListe):
        auswahl = self._ausgewaehlt(self._listboxen[liste])
        if not auswahl:
            return
        if len(auswahl) > 1 and not messagebox.askyesno(
                "Entfernen", f"{len(auswahl)} Einträge entfernen?", parent=self):
            return
        history_store.liste_mehrere_entfernen(self.db, self.besitzer, liste, auswahl)
        self._alles_neu_laden()

    def _exportieren(self, liste: PersonenListe):
        namen = history_store.liste_laden(self.db, self.besitzer, liste)
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", filetypes=[("Textdatei", "*.txt")],
                                            initialfile=f"{liste.value}.txt")
        if pfad:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(namensliste_text(LISTEN_TEXTE[liste], namen))

    def _profil(self, lb: tk.Listbox):
        auswahl = lb.curselection()
        if auswahl:
            webbrowser.open(profil_url(self.plattform, lb.get(auswahl[0]).split('  ·')[0].strip()))

    # ------------------------------------------------------------ Markierungen
    def _markierungen_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self.notebook, style="Karte.TFrame", padding=16)
        self.notebook.add(tab, text="Markierte Accounts")
        ttk.Label(tab, wraplength=600, justify="left", style="SchwachKarte.TLabel",
                  text="Dauerhafte Markierungen aus dem Entfolgen-Modus. Entfernst du eine Markierung, "
                       "gilt der Account beim nächsten Mal wieder als „neu“ und wird abgefragt.").pack(anchor="w", pady=(0, 8))

        self._filter["markierungen"] = self._filterzeile(tab, "markierungen")
        rahmen = ttk.Frame(tab, style="Karte.TFrame")
        rahmen.pack(fill=tk.BOTH, expand=True)
        self.baum = ttk.Treeview(rahmen, columns=("markierung", "seit"), show="tree headings", selectmode="extended")
        self.baum.heading("#0", text="Account")
        self.baum.heading("markierung", text="Markierung")
        self.baum.heading("seit", text="gesetzt am")
        self.baum.column("#0", width=220)
        self.baum.column("markierung", width=260)
        self.baum.column("seit", width=100, anchor="center")
        scroll = ttk.Scrollbar(rahmen, command=self.baum.yview)
        self.baum.configure(yscrollcommand=scroll.set)
        self.baum.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        knoepfe = ttk.Frame(tab, style="Karte.TFrame")
        knoepfe.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(knoepfe, text="Alle", style="Dezent.TButton",
                   command=lambda: self.baum.selection_set(self.baum.get_children())).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(knoepfe, text="Keine", style="Dezent.TButton",
                   command=lambda: self.baum.selection_set(())).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(knoepfe, text="→ Behalten", style="Erfolg.TButton",
                   command=lambda: self._markierung_setzen(Entscheidung.BEHALTEN)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(knoepfe, text="→ Deaktiviert", style="Warnung.TButton",
                   command=lambda: self._markierung_setzen(Entscheidung.DEAKTIVIERT)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(knoepfe, text="→ Entfolgen", style="Gefahr.TButton",
                   command=lambda: self._markierung_setzen(Entscheidung.ENTFERNT)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(knoepfe, text="Markierung entfernen", style="Dezent.TButton",
                   command=lambda: self._markierung_setzen(None)).pack(side=tk.RIGHT)
        return tab

    def _markierung_setzen(self, markierung: Entscheidung | None):
        namen = list(self.baum.selection())
        if not namen:
            return
        if len(namen) > 1 and not messagebox.askyesno(
                "Massenbearbeitung", f"{len(namen)} Accounts ändern?", parent=self):
            return
        history_store.markierungen_mehrere_setzen(self.db, self.besitzer, namen, markierung)
        self._alles_neu_laden()

    # ------------------------------------------------------------ Laden
    def _alles_neu_laden(self):
        for liste, lb in self._listboxen.items():
            lb.delete(0, tk.END)
            eintraege = history_store.liste_laden(self.db, self.besitzer, liste)
            for name, am in self._gefiltert(liste.value, eintraege.items()):
                lb.insert(tk.END, f"  {name}  ·  seit {am[:10]}")
            self.notebook.tab(self._tabs[liste.value], text=f"{LISTEN_TEXTE[liste]} ({len(eintraege)})")

        self.baum.delete(*self.baum.get_children())
        markierungen = history_store.markierungen_mit_datum(self.db, self.besitzer)
        for name, markierung, am in self._gefiltert("markierungen", markierungen):
            self.baum.insert("", tk.END, iid=name, text=name, values=(ENTSCHEIDUNG_TEXTE[markierung], am[:10]))
        self.notebook.tab(self._tabs["markierungen"], text=f"Markierte Accounts ({len(markierungen)})")
