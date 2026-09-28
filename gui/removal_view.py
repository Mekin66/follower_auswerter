"""
GUI für den Entfolgen-Modus (Desktop).

Ablauf:
1. Auswahl: Welche bereits markierten Gruppen sollen erneut abgefragt
   werden? (erscheint nur, wenn es markierte Accounts gibt)
2. Optional: automatische Vorprüfung auf deaktivierte Accounts
3. Wizard: pro Account Behalten / Entfolgen / Scheint deaktiviert
4. Zusammenfassung + Export

Die komplette Logik steckt in core/removal_session.py (EntfolgenAblauf).
"""

import queue
import sqlite3
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from core import history_store
from core.export import entfolgen_bericht
from core.konto_pruefer import PruefungNichtMoeglich, pruefe_mehrere
from core.plattform import PLATTFORM_TEXTE, Plattform, profil_url
from core.models import ENTSCHEIDUNG_TEXTE, Entscheidung, PersonenListe
from core.removal_session import KATEGORIEN, EntfolgenAblauf, kategorien_ermitteln
from gui import theme

BESITZER = history_store.LOKAL


class RemovalFenster(tk.Toplevel):
    def __init__(self, parent: tk.Tk, db_verbindung: sqlite3.Connection, snapshot_id: int,
                 besitzer: str = BESITZER, plattform: Plattform = Plattform.INSTAGRAM):
        super().__init__(parent)
        self.besitzer, self.plattform = besitzer, plattform
        self.title(f"Entfolgen-Modus ({PLATTFORM_TEXTE[plattform]})")
        self.geometry("640x560")
        self.minsize(560, 500)
        self.configure(bg=theme.HINTERGRUND)

        self.db = db_verbindung
        self.snapshot = history_store.snapshot_laden(self.db, snapshot_id, self.besitzer)
        self.markierungen = history_store.markierungen_laden(self.db, self.besitzer)
        self.freunde = set(history_store.liste_laden(self.db, self.besitzer, PersonenListe.FREUNDE))
        self.ablauf: EntfolgenAblauf | None = None
        self._pruefung_abbrechen = False

        theme.kopfzeile(self, "Entfolgen-Modus").pack(fill=tk.X, side=tk.TOP)
        self.aussen = ttk.Frame(self, padding=20)
        self.aussen.pack(fill=tk.BOTH, expand=True)
        self.protocol("WM_DELETE_WINDOW", self._schliessen)

        uebersicht = kategorien_ermitteln(self.snapshot, self.markierungen, self.freunde)
        if not uebersicht.alle:
            karte = self._karte()
            ttk.Label(karte, text="Es gibt aktuell niemanden, der dir nicht zurückfolgt. 🎉",
                      style="Karte.TLabel", font=(theme.SCHRIFT, 12)).pack(expand=True)
            return

        if any(uebersicht.anzahl(k) for k, _ in KATEGORIEN):
            self._auswahl_anzeigen(uebersicht)
        else:
            self._starten(set())

    # ------------------------------------------------------------ Helfer
    def _schliessen(self):
        self._pruefung_abbrechen = True
        self.destroy()

    def _leeren(self):
        for widget in self.aussen.winfo_children():
            widget.destroy()

    def _karte(self) -> ttk.Frame:
        karte = ttk.Frame(self.aussen, style="Karte.TFrame", padding=24)
        karte.pack(fill=tk.BOTH, expand=True)
        return karte

    def _titel(self, karte, text):
        ttk.Label(karte, text=text, style="Karte.TLabel",
                  font=(theme.SCHRIFT, 13, "bold")).pack(pady=(0, 10), anchor="w")

    # ------------------------------------------------------------ 1. Auswahl
    def _auswahl_anzeigen(self, uebersicht):
        self._leeren()
        karte = self._karte()
        self._titel(karte, "Welche Gruppen sollen erneut abgefragt werden?")
        ttk.Label(
            karte, wraplength=520, justify="left", style="SchwachKarte.TLabel",
            text=(f"{len(uebersicht.alle)} Accounts folgen dir nicht zurück, {len(uebersicht.neu)} davon sind neu "
                  "und werden immer abgefragt. Bereits markierte Gruppen werden übersprungen, außer du "
                  "hakst sie hier an (dann werden sie auch bei der automatischen Prüfung berücksichtigt)."),
        ).pack(anchor="w", pady=(0, 10))
        ttk.Label(karte, text="Haken = Gruppe erneut abfragen", style="Hinweis.TLabel").pack(anchor="w", pady=(0, 8))

        self._auswahl_vars: dict[str, tk.BooleanVar] = {}
        for schluessel, text in KATEGORIEN:
            anzahl = uebersicht.anzahl(schluessel)
            var = tk.BooleanVar(value=False)
            self._auswahl_vars[schluessel] = var
            zeile = ttk.Frame(karte, style="Karte.TFrame")
            zeile.pack(fill=tk.X, pady=3)
            cb = ttk.Checkbutton(zeile, text=text, variable=var, style="Karte.TCheckbutton")
            cb.pack(side=tk.LEFT)
            if not anzahl:
                cb.state(["disabled"])
            ttk.Label(zeile, text=str(anzahl), style="Karte.TLabel",
                      font=(theme.SCHRIFT, 11, "bold")).pack(side=tk.RIGHT)

        ttk.Button(karte, text="Weiter", style="Primaer.TButton",
                   command=lambda: self._starten({k for k, v in self._auswahl_vars.items() if v.get()})
                   ).pack(anchor="w", pady=(18, 0))

    def _starten(self, erneut: set[str]):
        self.ablauf = EntfolgenAblauf(self.besitzer, self.snapshot, self.markierungen, self.freunde, erneut)
        if not self.ablauf.session.kandidaten:
            self._leeren()
            karte = self._karte()
            self._titel(karte, "Nichts offen 🎉")
            ttk.Label(karte, style="SchwachKarte.TLabel", wraplength=520, justify="left",
                      text="Alle, die dir nicht zurückfolgen, sind bereits markiert und wurden übersprungen."
                      ).pack(anchor="w")
            self._uebersprungen_label(karte)
            if self.ablauf.noch_zu_entfolgen():
                self._zusammenfassung_anzeigen()
            return
        self._vorab_anzeigen()

    def _uebersprungen_label(self, parent):
        if not self.ablauf or not self.ablauf.uebersprungen:
            return
        texte = dict(KATEGORIEN)
        teile = [f"{texte[k].split(' (')[0]}: {len(v)}" for k, v in self.ablauf.uebersprungen.items()]
        ttk.Label(parent, text="Übersprungen – " + " · ".join(teile), style="SchwachKarte.TLabel",
                  wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))

    # ------------------------------------------------------------ 2. Vorprüfung
    def _vorab_anzeigen(self):
        offen = self.ablauf.offene()
        self._leeren()
        karte = self._karte()
        self._titel(karte, "🔍 Automatische Vorprüfung")
        ttk.Label(
            karte, wraplength=520, justify="left", style="SchwachKarte.TLabel",
            text=(f"{len(offen)} Accounts sind offen. Ich kann vorab prüfen, ob einzelne davon gelöscht oder "
                  "deaktiviert wirken (öffentliche Profilseite, kein Login). Dauer ca. "
                  f"{max(1, round(len(offen) * 4 / 60))} Minute(n). Vorher teste ich, ob "
                  f"{PLATTFORM_TEXTE[self.plattform]} gerade eine zuverlässige Prüfung zulässt. "
                  "Alle Treffer bekommst du als Vorschlag zum Bestätigen – nichts wird ungefragt übernommen."),
        ).pack(pady=(0, 20), anchor="w")
        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w")
        ttk.Button(zeile, text="Automatisch prüfen", style="Primaer.TButton",
                   command=lambda: self._pruefung_starten(offen)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(zeile, text="Überspringen (nur manuell)", style="Dezent.TButton",
                   command=self._wizard_aufbauen).pack(side=tk.LEFT)

    def _pruefung_starten(self, offen: list[str]):
        self._leeren()
        karte = self._karte()
        self._titel(karte, "⏳ Prüfe Accounts …")
        self.pruef_balken = ttk.Progressbar(karte, mode="determinate", length=460, maximum=max(len(offen), 1))
        self.pruef_balken.pack(pady=(4, 10), anchor="w")
        self.lbl_pruef = ttk.Label(karte, text="", style="SchwachKarte.TLabel")
        self.lbl_pruef.pack(anchor="w")
        ttk.Button(karte, text="Abbrechen", style="Dezent.TButton",
                   command=lambda: setattr(self, "_pruefung_abbrechen", True)).pack(anchor="w", pady=(16, 0))

        self._queue: queue.Queue = queue.Queue()
        self._pruefung_abbrechen = False
        self._pruef_gesamt, self._pruef_erledigt = len(offen), 0

        def hintergrund():
            # Nur prüfen, NICHT in die DB schreiben: SQLite-Verbindungen gehören
            # dem Hauptthread. Ergebnisse gehen über die Queue zurück.
            try:
                for ergebnis in pruefe_mehrere(offen, 3.0, abbrechen=lambda: self._pruefung_abbrechen,
                                               plattform=self.plattform):
                    self._queue.put(ergebnis)
            except PruefungNichtMoeglich as e:
                self._queue.put(("fehler", str(e)))
            except Exception as e:  # noqa: BLE001
                self._queue.put(("fehler", f"Unerwarteter Fehler: {e}"))
            self._queue.put(None)

        threading.Thread(target=hintergrund, daemon=True).start()
        self.after(100, self._queue_abfragen)

    def _queue_abfragen(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                ergebnis = self._queue.get_nowait()
                if ergebnis is None:
                    if self.ablauf.vorschlaege_offen:
                        self._vorschlaege_anzeigen()
                    else:
                        messagebox.showinfo("Prüfung beendet", "Keine gelöschten/deaktivierten Accounts gefunden.",
                                            parent=self)
                        self._wizard_aufbauen()
                    return
                if isinstance(ergebnis, tuple):              # ("fehler", Meldung)
                    messagebox.showwarning("Automatische Prüfung gestoppt", ergebnis[1], parent=self)
                    continue
                self._pruef_erledigt += 1
                self.ablauf.auto_ergebnis_uebernehmen(self.db, ergebnis)
                self.pruef_balken.config(value=self._pruef_erledigt)
                self.lbl_pruef.config(text=f"{self._pruef_erledigt} von {self._pruef_gesamt} geprüft – "
                                           f"zuletzt: {ergebnis.username} ({ergebnis.status.value})")
        except queue.Empty:
            self.after(150, self._queue_abfragen)

    def _vorschlaege_anzeigen(self):
        """Treffer der Prüfung zur Bestätigung – nur Angehakte werden als 'Scheint deaktiviert' übernommen."""
        self._leeren()
        karte = self._karte()
        self._titel(karte, f"🔎 {len(self.ablauf.vorschlaege)} Account(s) scheinen nicht mehr zu existieren")
        ttk.Label(karte, style="SchwachKarte.TLabel", wraplength=560, justify="left",
                  text="Bitte kurz prüfen (Doppelklick öffnet das Profil). Nur markierte Einträge werden übernommen; "
                       "alle anderen fragt das Programm danach ganz normal ab.").pack(anchor="w", pady=(0, 8))
        rahmen = ttk.Frame(karte, style="Karte.TFrame")
        rahmen.pack(fill=tk.BOTH, expand=True)
        baum = ttk.Treeview(rahmen, columns=("grund",), show="tree headings", selectmode="extended", height=8)
        baum.heading("#0", text="Account")
        baum.heading("grund", text="Warum?")
        baum.column("#0", width=180)
        baum.column("grund", width=340)
        for name, grund in self.ablauf.vorschlaege.items():
            baum.insert("", tk.END, iid=name, text=name, values=(grund,))
        baum.selection_set(baum.get_children())                  # standardmäßig alle markiert
        scroll = ttk.Scrollbar(rahmen, command=baum.yview)
        baum.configure(yscrollcommand=scroll.set)
        baum.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        baum.bind("<Double-Button-1>", lambda _e: [webbrowser.open(profil_url(self.plattform, n)) for n in baum.selection()[:1]])

        def uebernehmen():
            self.ablauf.vorschlaege_bestaetigen(self.db, baum.selection())
            self._wizard_aufbauen()

        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w", pady=(12, 0))
        ttk.Button(zeile, text="Markierte übernehmen", style="Primaer.TButton", command=uebernehmen).pack(side=tk.LEFT)
        ttk.Button(zeile, text="Keine übernehmen", style="Dezent.TButton",
                   command=lambda: (baum.selection_set(()), uebernehmen())).pack(side=tk.LEFT, padx=8)
        ttk.Label(zeile, text="Strg/Umschalt+Klick = Mehrfachauswahl", style="SchwachKarte.TLabel").pack(side=tk.LEFT)

    # ------------------------------------------------------------ 3. Wizard
    def _wizard_aufbauen(self):
        self._leeren()
        karte = self._karte()

        self.lbl_fortschritt = ttk.Label(karte, text="", style="SchwachKarte.TLabel")
        self.lbl_fortschritt.pack(pady=(4, 0))
        self.fortschrittsbalken = ttk.Progressbar(karte, mode="determinate", length=440)
        self.fortschrittsbalken.pack(pady=(6, 18))

        self.lbl_username = ttk.Label(karte, text="", style="Karte.TLabel", font=(theme.SCHRIFT, 22, "bold"),
                                      cursor="hand2")
        self.lbl_username.pack(pady=4)
        self.lbl_username.bind("<Button-1>", lambda _e: self._profil_oeffnen())
        self.lbl_seit = ttk.Label(karte, text="", style="SchwachKarte.TLabel")
        self.lbl_seit.pack()
        self.lbl_bisher = ttk.Label(karte, text="", style="Hinweis.TLabel")
        self.lbl_bisher.pack(pady=(4, 18))

        knoepfe = ttk.Frame(karte, style="Karte.TFrame")
        knoepfe.pack(pady=(0, 10))
        ttk.Button(knoepfe, text="✓ Behalten", style="Erfolg.TButton",
                   command=lambda: self._entscheiden(Entscheidung.BEHALTEN)).grid(row=0, column=0, padx=5)
        ttk.Button(knoepfe, text="✗ Entfolgen", style="Gefahr.TButton",
                   command=lambda: self._entscheiden(Entscheidung.ENTFERNT)).grid(row=0, column=1, padx=5)
        ttk.Button(knoepfe, text="? Scheint deaktiviert", style="Warnung.TButton",
                   command=lambda: self._entscheiden(Entscheidung.DEAKTIVIERT)).grid(row=0, column=2, padx=5)

        unten = ttk.Frame(karte, style="Karte.TFrame")
        unten.pack()
        self.btn_zurueck = ttk.Button(unten, text="← Zurück", style="Dezent.TButton", command=self._zurueck)
        self.btn_zurueck.pack(side=tk.LEFT, padx=4)
        ttk.Button(unten, text="Profil im Browser öffnen", style="Dezent.TButton",
                   command=self._profil_oeffnen).pack(side=tk.LEFT, padx=4)
        self._uebersprungen_label(karte)

        # Tastatur: B / E / D, Rücktaste = zurück
        self.bind("<b>", lambda _e: self._entscheiden(Entscheidung.BEHALTEN))
        self.bind("<e>", lambda _e: self._entscheiden(Entscheidung.ENTFERNT))
        self.bind("<d>", lambda _e: self._entscheiden(Entscheidung.DEAKTIVIERT))
        self.bind("<BackSpace>", lambda _e: self._zurueck())
        self._anzeigen()

    def _anzeigen(self):
        if self.ablauf.ist_fertig():
            self._zusammenfassung_anzeigen()
            return
        kandidat = self.ablauf.aktueller_kandidat()
        entschieden, gesamt = self.ablauf.fortschritt()
        self.lbl_fortschritt.config(text=f"{entschieden} von {gesamt} bearbeitet  ·  Tasten: B / E / D")
        self.fortschrittsbalken.config(maximum=max(gesamt, 1), value=entschieden)
        self.lbl_username.config(text=kandidat)
        self.lbl_seit.config(text=f"Du folgst seit {self.ablauf.seit(kandidat)}")
        bisher = self.ablauf.bisherige_markierung(kandidat)
        self.lbl_bisher.config(text=f"bisher: {ENTSCHEIDUNG_TEXTE[bisher]}" if bisher else "")
        self.btn_zurueck.state(["!disabled"] if self.ablauf.kann_zurueck() else ["disabled"])

    def _profil_oeffnen(self):
        kandidat = self.ablauf.aktueller_kandidat() if self.ablauf else None
        if kandidat:
            webbrowser.open(profil_url(self.plattform, kandidat))

    def _entscheiden(self, entscheidung: Entscheidung):
        if self.ablauf is None or self.ablauf.ist_fertig():
            return
        self.ablauf.entscheide(self.db, entscheidung)
        self._anzeigen()

    def _zurueck(self):
        if self.ablauf and self.ablauf.zurueck(self.db):
            if not hasattr(self, "lbl_username") or not self.lbl_username.winfo_exists():
                self._wizard_aufbauen()
            else:
                self._anzeigen()

    # ------------------------------------------------------------ 4. Zusammenfassung
    def _zusammenfassung_anzeigen(self):
        for taste in ("<b>", "<e>", "<d>"):
            self.unbind(taste)
        self._leeren()
        karte = self._karte()
        self._titel(karte, "✅ Fertig! Zusammenfassung")

        rahmen = tk.Frame(karte, bg=theme.RAND, bd=1)
        rahmen.pack(fill=tk.BOTH, expand=True, pady=(0, 14))
        text = tk.Text(rahmen, wrap="word", height=12, borderwidth=0, highlightthickness=0,
                       bg=theme.KARTE, fg=theme.TEXT, font=(theme.SCHRIFT, 10), padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        bericht = entfolgen_bericht(self.ablauf.zusammenfassung(), self.ablauf.noch_zu_entfolgen())
        text.insert("1.0", bericht)
        text.config(state=tk.DISABLED)

        zeile = ttk.Frame(karte, style="Karte.TFrame")
        zeile.pack(anchor="w")
        ttk.Button(zeile, text="⬇ Als Textdatei exportieren", style="Primaer.TButton",
                   command=lambda: self._exportieren(bericht)).pack(side=tk.LEFT, padx=(0, 8))
        if self.ablauf.kann_zurueck():
            ttk.Button(zeile, text="← Letzte Entscheidung korrigieren", style="Dezent.TButton",
                       command=self._zurueck).pack(side=tk.LEFT)

    def _exportieren(self, bericht: str):
        pfad = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", filetypes=[("Textdatei", "*.txt")],
                                            initialfile="entfolgen_ergebnis.txt")
        if not pfad:
            return
        try:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(bericht)
            messagebox.showinfo("Gespeichert", f"Ergebnis gespeichert unter:\n{pfad}", parent=self)
        except OSError as e:
            messagebox.showerror("Fehler", f"Konnte Datei nicht speichern:\n{e}", parent=self)
