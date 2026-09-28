"""
Fenster zum Ansehen des Verlaufs und Vergleichen zweier Zeitpunkte (Punkt a).

Beispiel-Nutzung: Du wählst links den Snapshot von vor 20 Tagen und rechts
den heutigen Snapshot aus, klickst auf "Vergleichen" und siehst, wer dir in
diesem Zeitraum neu gefolgt bzw. entfolgt ist.
"""

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox

from core import history_store
from core.diff_engine import moegliche_blockierungen, vergleiche_snapshots
from core.models import ListTyp
from gui import theme
from gui.listen_view import ListenFenster
from core.plattform import PLATTFORM_TEXTE, Plattform


class HistoryFenster(tk.Toplevel):
    def __init__(self, parent: tk.Tk, db_verbindung: sqlite3.Connection, besitzer: str = history_store.LOKAL,
                 plattform: Plattform = Plattform.INSTAGRAM):
        super().__init__(parent)
        self.besitzer, self.plattform = besitzer, plattform
        self.title(f"Verlauf & Zeitraum-Vergleich ({PLATTFORM_TEXTE[plattform]})")
        self.geometry("780x640")
        self.configure(bg=theme.HINTERGRUND)
        self.db_verbindung = db_verbindung

        self.snapshots = history_store.snapshots_auflisten(self.db_verbindung, self.besitzer)
        self._anzeige_werte = [f"#{sid} – {label} ({erstellt_am})"
                                for sid, erstellt_am, label in self.snapshots]

        theme.kopfzeile(self, "Verlauf").pack(fill=tk.X, side=tk.TOP)
        self._aufbauen()

    def _aufbauen(self):
        aussen = ttk.Frame(self, padding=20)
        aussen.pack(fill=tk.BOTH, expand=True)

        if not self.snapshots:
            karte = ttk.Frame(aussen, style="Karte.TFrame", padding=30)
            karte.pack(fill=tk.X)
            ttk.Label(karte, text="Noch keine gespeicherten Auswertungen vorhanden.\n"
                                   "Lade zuerst Daten im Hauptfenster und klicke auf 'Auswerten'.",
                      style="SchwachKarte.TLabel", justify="center").pack()
            return

        karte_auswahl = ttk.Frame(aussen, style="Karte.TFrame", padding=18)
        karte_auswahl.pack(fill=tk.X, pady=(0, 14))

        ttk.Label(karte_auswahl, text="Zwei Zeitpunkte vergleichen", style="Karte.TLabel",
                  font=(theme.SCHRIFT, 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(karte_auswahl, text="Älterer Zeitpunkt", style="SchwachKarte.TLabel").grid(row=1, column=0, sticky="w")
        self.combo_alt = ttk.Combobox(karte_auswahl, values=self._anzeige_werte, width=42, state="readonly")
        self.combo_alt.grid(row=2, column=0, padx=(0, 10), pady=(2, 10), sticky="ew")
        self.combo_alt.current(min(1, len(self.snapshots) - 1))

        ttk.Label(karte_auswahl, text="Neuerer Zeitpunkt", style="SchwachKarte.TLabel").grid(row=1, column=1, sticky="w")
        self.combo_neu = ttk.Combobox(karte_auswahl, values=self._anzeige_werte, width=42, state="readonly")
        self.combo_neu.grid(row=2, column=1, padx=(10, 0), pady=(2, 10), sticky="ew")
        self.combo_neu.current(0)

        karte_auswahl.columnconfigure(0, weight=1)
        karte_auswahl.columnconfigure(1, weight=1)

        ttk.Button(karte_auswahl, text="Vergleichen", command=self._vergleichen,
                   style="Primaer.TButton").grid(row=3, column=0, columnspan=2, sticky="ew")

        karte_ergebnis = ttk.Frame(aussen, style="Karte.TFrame", padding=18)
        karte_ergebnis.pack(fill=tk.BOTH, expand=True)

        rahmen = tk.Frame(karte_ergebnis, bg=theme.RAND, bd=1)
        rahmen.pack(fill=tk.BOTH, expand=True)
        self.ergebnis_text = tk.Text(rahmen, wrap="word", state=tk.DISABLED, borderwidth=0, height=12,
                                      highlightthickness=0, bg=theme.KARTE, fg=theme.TEXT,
                                      font=(theme.SCHRIFT, 10), padx=10, pady=10)
        self.ergebnis_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self.ergebnis_text.tag_config("neu", foreground=theme.GRUEN_DUNKEL)
        self.ergebnis_text.tag_config("entfernt", foreground=theme.ROT_DUNKEL)
        self.ergebnis_text.tag_config("ueberschrift", font=(theme.SCHRIFT, 10, "bold"))
        self.ergebnis_text.tag_config("verdacht", foreground=theme.GELB_DUNKEL)

        knoepfe = ttk.Frame(karte_ergebnis, style="Karte.TFrame")
        knoepfe.pack(fill=tk.X, pady=(10, 0))
        self.btn_blockiert = ttk.Button(knoepfe, text="Verdächtige → „Hat mich blockiert“ …", style="Warnung.TButton",
                                        command=self._verdacht_uebernehmen, state=tk.DISABLED)
        self.btn_blockiert.pack(side=tk.LEFT)
        ttk.Button(knoepfe, text="Rechts gewählten Zeitpunkt löschen", style="Dezent.TButton",
                   command=self._snapshot_loeschen).pack(side=tk.RIGHT)
        self._verdacht: list[str] = []

    def _vergleichen(self):
        idx_alt = self.combo_alt.current()
        idx_neu = self.combo_neu.current()

        if idx_alt == idx_neu:
            messagebox.showwarning("Hinweis", "Bitte zwei unterschiedliche Zeitpunkte auswählen.")
            return

        id_alt = self.snapshots[idx_alt][0]
        id_neu = self.snapshots[idx_neu][0]

        snap_alt = history_store.snapshot_laden(self.db_verbindung, id_alt, self.besitzer)
        snap_neu = history_store.snapshot_laden(self.db_verbindung, id_neu, self.besitzer)

        aenderungen = vergleiche_snapshots(snap_alt, snap_neu)
        self._verdacht = moegliche_blockierungen(snap_alt, snap_neu)
        self.btn_blockiert.config(state=tk.NORMAL if self._verdacht else tk.DISABLED)

        self.ergebnis_text.config(state=tk.NORMAL)
        self.ergebnis_text.delete("1.0", tk.END)

        if not aenderungen:
            self.ergebnis_text.insert(tk.END, "Keine Änderungen zwischen diesen beiden Zeitpunkten gefunden.\n")
        else:
            for liste, ueberschrift in [(ListTyp.FOLLOWER, "Follower (folgen mir)"),
                                          (ListTyp.FOLLOWING, "Following (ich folge)")]:
                relevante = [a for a in aenderungen if a.liste == liste]
                if not relevante:
                    continue
                self.ergebnis_text.insert(tk.END, f"\n{ueberschrift}\n", "ueberschrift")
                for aenderung in relevante:
                    if aenderung.art == "neu":
                        self.ergebnis_text.insert(tk.END, f"  ➕ neu: {aenderung.username}\n", "neu")
                    else:
                        self.ergebnis_text.insert(tk.END, f"  ➖ entfernt: {aenderung.username}\n", "entfernt")

        if self._verdacht:
            self.ergebnis_text.insert(tk.END, "\n⚠ Möglicherweise blockiert (vorher gegenseitig, jetzt beide Verbindungen weg)\n",
                                      "ueberschrift")
            for name in self._verdacht:
                self.ergebnis_text.insert(tk.END, f"  ? {name}\n", "verdacht")

        self.ergebnis_text.config(state=tk.DISABLED)

    def _verdacht_uebernehmen(self):
        ListenFenster(self.master, self.db_verbindung, start_liste="blockiert_mich", vorschlaege=self._verdacht,
                      besitzer=self.besitzer, plattform=self.plattform)

    def _snapshot_loeschen(self):
        idx = self.combo_neu.current()
        if idx < 0:
            return
        sid, _, label = self.snapshots[idx]
        if not messagebox.askyesno("Löschen", f"Auswertung „{label}“ wirklich löschen?", parent=self):
            return
        history_store.snapshot_loeschen(self.db_verbindung, sid, self.besitzer)
        for widget in self.winfo_children():
            widget.destroy()
        self.snapshots = history_store.snapshots_auflisten(self.db_verbindung, self.besitzer)
        self._anzeige_werte = [f"#{s} – {l} ({e})" for s, e, l in self.snapshots]
        theme.kopfzeile(self, "Verlauf").pack(fill=tk.X, side=tk.TOP)
        self._aufbauen()
