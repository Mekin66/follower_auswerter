"""
Hauptfenster der Desktop-App.

Enthält nur Darstellung; Laden, Speichern und Auswerten passieren in core/.
Neu in Version 3: Plattform-Wahl (Instagram/TikTok), TXT-Listen, Listen-Editor
und ein Hilfe-Fenster mit Schritt-für-Schritt-Anleitungen.
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core import history_store
from core.archive_reader import ExportFormatFehler, lade_export, lade_liste
from core.models import PersonenListe
from core.plattform import PLATTFORM_TEXTE, Plattform, bereich
from gui import theme
from gui.aktivitaet_view import KommentareFenster, LikesFenster
from gui.editor_view import EditorFenster
from gui.freunde_view import FreundeFenster
from gui.hilfe_view import HilfeFenster
from gui.history_view import HistoryFenster
from gui.listen_view import ListenFenster
from gui.removal_view import RemovalFenster


class InstagramAuswerter:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Follower-Auswertung")
        self.root.geometry("1180x760")
        self.root.minsize(900, 560)

        self.follower_daten: dict[str, str] = {}
        self.following_daten: dict[str, str] = {}
        self.blockiert_aus_zip: dict[str, str] = {}
        self.enge_freunde_aus_zip: dict[str, str] = {}
        self.letzter_snapshot_id: int | None = None

        self.style = theme.anwenden(self.root)
        self.db_verbindung = history_store.init_db()   # eine Verbindung für die ganze Laufzeit
        self.plattform_var = tk.StringVar(value=Plattform.INSTAGRAM.value)

        self.setup_ui()
        self._plattform_gewechselt()

    # ------------------------------------------------------------ Plattform
    @property
    def plattform(self) -> Plattform:
        return Plattform(self.plattform_var.get())

    @property
    def besitzer(self) -> str:
        """Instagram-Daten unter "lokal", TikTok-Daten unter "lokal#tiktok"."""
        return bereich(history_store.LOKAL, self.plattform)

    def _plattform_gewechselt(self):
        """Geladene (noch nicht ausgewertete) Daten verwerfen und die letzte Auswertung dieser Plattform zeigen."""
        self.follower_daten, self.following_daten = {}, {}
        self.blockiert_aus_zip, self.enge_freunde_aus_zip = {}, {}
        self.btn_follower.config(text="Follower-Liste laden (JSON/HTML/TXT)")
        self.btn_following.config(text="Following-Liste laden (JSON/HTML/TXT)")
        self.btn_auswerten.config(state=tk.DISABLED)
        name = PLATTFORM_TEXTE[self.plattform]
        self.lbl_titel.config(text=f"1. {name}-Daten laden")
        self._aktivitaet_knoepfe()

        self.letzter_snapshot_id = history_store.letzten_snapshot_id(self.db_verbindung, self.besitzer)
        zustand = tk.NORMAL if self.letzter_snapshot_id else tk.DISABLED
        self.btn_entfolgen.config(state=zustand)
        self.btn_freunde.config(state=zustand)
        if self.letzter_snapshot_id:
            snapshot = history_store.snapshot_laden(self.db_verbindung, self.letzter_snapshot_id, self.besitzer)
            self.lbl_status.config(text=f"Letzte {name}-Auswertung: {snapshot.label}. Für einen neuen Stand Daten laden.",
                                   style="Schwach.TLabel")
            self._listen_anzeigen(snapshot.follower, snapshot.following)
        else:
            self.lbl_status.config(text=f"Noch keine {name}-Auswertung. Neu hier? Klick auf „❓ Anleitung“.",
                                   style="Schwach.TLabel")
            self._listen_anzeigen({}, {})

    # ------------------------------------------------------------ Aufbau
    def setup_ui(self):
        theme.fenster_icon(self.root)
        theme.mausrad_aktivieren(self.root)
        kopf = theme.kopfzeile(self.root)
        kopf.pack(fill=tk.X, side=tk.TOP)
        ttk.Button(kopf, text="❓ Anleitung", style="Dezent.TButton",
                   command=lambda: HilfeFenster(self.root)).pack(side=tk.RIGHT, padx=12)
        wahl = ttk.Frame(kopf, style="Kopfzeile.TFrame")
        wahl.pack(side=tk.RIGHT, padx=8)
        for p in Plattform:
            ttk.Radiobutton(wahl, text=PLATTFORM_TEXTE[p], value=p.value, variable=self.plattform_var,
                            style="Kopf.TRadiobutton", command=self._plattform_gewechselt).pack(side=tk.LEFT, padx=4)

        # Zwei Spalten: links Knöpfe (scrollbar, falls das Fenster klein ist), rechts die Listen in voller Höhe.
        # Vorher lag alles untereinander – auf kleineren Bildschirmen blieb für die Listen kaum Platz,
        # und die Follower-Liste ließ sich nicht sinnvoll scrollen.
        koerper = ttk.Frame(self.root, padding=(16, 14))
        koerper.pack(fill=tk.BOTH, expand=True)
        links = theme.scrollbarer_bereich(koerper, breite=390)
        links.rahmen.pack(side=tk.LEFT, fill=tk.Y)
        rechts = ttk.Frame(koerper)
        rechts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))

        # --- Karte 1: Daten laden ---
        karte_laden = ttk.Frame(links, style="Karte.TFrame", padding=16)
        karte_laden.pack(fill=tk.X, pady=(0, 12), padx=(0, 6))
        self.lbl_titel = ttk.Label(karte_laden, text="", style="Karte.TLabel", font=(theme.SCHRIFT, 11, "bold"))
        self.lbl_titel.pack(anchor="w")
        ttk.Button(karte_laden, text="Wie bekomme ich die Datei?", style="Dezent.TButton",
                   command=lambda: HilfeFenster(self.root, f"{self.plattform.value}-export")).pack(fill=tk.X, pady=(8, 4))
        ttk.Button(karte_laden, text="📦 Export laden (ZIP / JSON / HTML)",
                   command=self.lade_export_datei, style="Primaer.TButton").pack(fill=tk.X, pady=4)
        self.btn_follower = ttk.Button(karte_laden, text="", command=self.lade_follower, style="Dezent.TButton")
        self.btn_follower.pack(fill=tk.X, pady=4)
        self.btn_following = ttk.Button(karte_laden, text="", command=self.lade_following, style="Dezent.TButton")
        self.btn_following.pack(fill=tk.X, pady=4)
        ttk.Button(karte_laden, text="✏️ Listen-Editor (eintippen / TXT)", command=self.oeffne_editor,
                   style="Dezent.TButton").pack(fill=tk.X, pady=(4, 0))

        # --- Karte 2: Follower auswerten ---
        karte_aktionen = ttk.Frame(links, style="Karte.TFrame", padding=16)
        karte_aktionen.pack(fill=tk.X, pady=(0, 12), padx=(0, 6))
        ttk.Label(karte_aktionen, text="2. Follower auswerten", style="Karte.TLabel",
                  font=(theme.SCHRIFT, 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.btn_auswerten = ttk.Button(karte_aktionen, text="Auswerten & im Verlauf speichern",
                                        command=self.auswerten, style="Primaer.TButton", state=tk.DISABLED)
        self.btn_auswerten.pack(fill=tk.X, pady=4)
        self.btn_entfolgen = ttk.Button(karte_aktionen, text="🧹 Entfolgen-Modus", command=self.oeffne_entfolgen_modus,
                                        style="Warnung.TButton", state=tk.DISABLED)
        self.btn_entfolgen.pack(fill=tk.X, pady=4)
        self.btn_freunde = ttk.Button(karte_aktionen, text="👥 Freunde-Liste", command=self.oeffne_freunde,
                                      style="Erfolg.TButton", state=tk.DISABLED)
        self.btn_freunde.pack(fill=tk.X, pady=4)
        ttk.Button(karte_aktionen, text="🕒 Verlauf / Zeitraum vergleichen", command=self.oeffne_verlauf,
                   style="Dezent.TButton").pack(fill=tk.X, pady=4)
        ttk.Button(karte_aktionen, text="📋 Meine Listen (blockiert, Freunde …)", command=self.oeffne_listen,
                   style="Dezent.TButton").pack(fill=tk.X, pady=4)

        # --- Karte 3: Kommentare & Likes ---
        karte_aktiv = ttk.Frame(links, style="Karte.TFrame", padding=16)
        karte_aktiv.pack(fill=tk.X, pady=(0, 12), padx=(0, 6))
        ttk.Label(karte_aktiv, text="3. Kommentare & Likes", style="Karte.TLabel",
                  font=(theme.SCHRIFT, 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.btn_kommentare = ttk.Button(karte_aktiv, text="", command=self.oeffne_kommentare, style="Primaer.TButton")
        self.btn_kommentare.pack(fill=tk.X, pady=4)
        self.btn_likes = ttk.Button(karte_aktiv, text="", command=self.oeffne_likes, style="Dezent.TButton")
        self.btn_likes.pack(fill=tk.X, pady=4)

        self.lbl_status = ttk.Label(links, text="", style="Schwach.TLabel", wraplength=360, justify="left")
        self.lbl_status.pack(anchor="w", pady=(0, 10))

        # --- Rechts: Ergebnis (zwei Listen, volle Höhe, mit Filter) ---
        karte_ergebnis = ttk.Frame(rechts, style="Karte.TFrame", padding=16)
        karte_ergebnis.pack(fill=tk.BOTH, expand=True)
        kopfzeile = ttk.Frame(karte_ergebnis, style="Karte.TFrame")
        kopfzeile.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(kopfzeile, text="🔴 Rot = kein gegenseitiges Folgen", style="SchwachKarte.TLabel").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        ttk.Entry(kopfzeile, textvariable=self.filter_var, width=18).pack(side=tk.RIGHT)
        ttk.Label(kopfzeile, text="Suchen:", style="SchwachKarte.TLabel").pack(side=tk.RIGHT, padx=6)
        self.filter_var.trace_add("write", lambda *_: self._listen_anzeigen(*self._angezeigt))
        self._angezeigt: tuple[dict, dict] = ({}, {})

        listen_bereich = ttk.Frame(karte_ergebnis, style="Karte.TFrame")
        listen_bereich.pack(fill=tk.BOTH, expand=True)
        listen_bereich.columnconfigure(0, weight=1)
        listen_bereich.columnconfigure(1, weight=1)
        listen_bereich.rowconfigure(1, weight=1)
        self.lbl_following_count = ttk.Label(listen_bereich, text="Ich folge (0)", style="Karte.TLabel",
                                             font=(theme.SCHRIFT, 10, "bold"))
        self.lbl_following_count.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.lbl_follower_count = ttk.Label(listen_bereich, text="Folgen mir (0)", style="Karte.TLabel",
                                            font=(theme.SCHRIFT, 10, "bold"))
        self.lbl_follower_count.grid(row=0, column=1, sticky="w", pady=(0, 4), padx=(12, 0))
        self.listbox_following = self._erzeuge_liste(listen_bereich, 0)
        self.listbox_followers = self._erzeuge_liste(listen_bereich, 1)

    @staticmethod
    def _erzeuge_liste(parent: ttk.Frame, spalte: int) -> tk.Listbox:
        rahmen = tk.Frame(parent, bg=theme.RAND, bd=1)
        rahmen.grid(row=1, column=spalte, sticky="nsew", padx=(12, 0) if spalte else (0, 0))
        scrollbar = ttk.Scrollbar(rahmen)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox = tk.Listbox(rahmen, font=(theme.SCHRIFT, 10), yscrollcommand=scrollbar.set,
                             bg=theme.KARTE, fg=theme.TEXT, borderwidth=0, highlightthickness=0,
                             selectbackground=theme.PRIMAER, activestyle="none", exportselection=False)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 1), pady=1)
        scrollbar.config(command=listbox.yview)
        return listbox

    def _aktivitaet_knoepfe(self):
        k = len(history_store.kommentare_laden(self.db_verbindung, self.besitzer))
        l = len(history_store.likes_laden(self.db_verbindung, self.besitzer))
        self.btn_kommentare.config(text=f"💬 Kommentare prüfen ({k})" if k else "💬 Kommentare (noch keine geladen)")
        self.btn_likes.config(text=f"❤️ Likes ansehen ({l})" if l else "❤️ Likes (noch keine geladen)")

    # ------------------------------------------------------------ Laden
    def _liste_waehlen(self) -> dict[str, str] | None:
        pfad = filedialog.askopenfilename(
            title="Liste auswählen (JSON aus dem Export oder eigene TXT)",
            filetypes=[("Listen", "*.json *.txt *.html"), ("Alle Dateien", "*.*")])
        if not pfad:
            return None
        try:
            return lade_liste(Path(pfad).read_bytes(), pfad)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Fehler", f"Die Datei konnte nicht gelesen werden:\n{e}")
            return None

    def lade_follower(self):
        daten = self._liste_waehlen()
        if daten is not None:
            self.follower_daten = daten
            self.btn_follower.config(text=f"✓ Follower geladen ({len(daten)})")
            self.check_ready()

    def lade_following(self):
        daten = self._liste_waehlen()
        if daten is not None:
            self.following_daten = daten
            self.btn_following.config(text=f"✓ Following geladen ({len(daten)})")
            self.check_ready()

    def lade_export_datei(self):
        """ZIP (Instagram/TikTok) oder TikTok-JSON laden; die Plattform wird automatisch erkannt."""
        pfad = filedialog.askopenfilename(title="Export-Datei auswählen",
                                          filetypes=[("Export", "*.zip *.json *.html"), ("Alle Dateien", "*.*")])
        if not pfad:
            return
        try:
            inhalt = lade_export(pfad)
        except ExportFormatFehler as e:
            messagebox.showerror("Datei passt nicht", str(e))
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Fehler", f"Die Datei konnte nicht gelesen werden:\n{e}")
            return
        if inhalt.plattform != self.plattform:
            self.plattform_var.set(inhalt.plattform.value)
            self._plattform_gewechselt()
            messagebox.showinfo("Plattform erkannt", f"{PLATTFORM_TEXTE[inhalt.plattform]}-Export erkannt – "
                                                     "die App ist jetzt darauf umgestellt.")
        # Kommentare und Likes sofort speichern (Duplikate werden übersprungen)
        neu_k = history_store.kommentare_speichern(self.db_verbindung, self.besitzer, inhalt.kommentare)
        neu_l = history_store.likes_speichern(self.db_verbindung, self.besitzer, inhalt.likes)
        self._aktivitaet_knoepfe()
        gefunden = ", ".join(f"{name}: {anzahl}" for name, anzahl in inhalt.enthaelt().items())
        if inhalt.hat_follower_daten():
            self.blockiert_aus_zip, self.enge_freunde_aus_zip = inhalt.blockiert, inhalt.enge_freunde
            self.follower_daten, self.following_daten = inhalt.follower, inhalt.following
            self.btn_follower.config(text=f"✓ Follower aus Export ({len(inhalt.follower)})")
            self.btn_following.config(text=f"✓ Following aus Export ({len(inhalt.following)})")
            self.check_ready()
        messagebox.showinfo("Export erkannt", f"Gefunden: {gefunden}.\n\n"
                            + ("Follower: jetzt auf „Auswerten“ klicken.\n" if inhalt.hat_follower_daten() else "")
                            + (f"Kommentare: {neu_k} neu → „Kommentare prüfen“.\n" if inhalt.kommentare else "")
                            + (f"Likes: {neu_l} neu → „Likes ansehen“." if inhalt.likes else ""))

    def check_ready(self):
        if self.follower_daten or self.following_daten:
            self.btn_auswerten.config(state=tk.NORMAL)
            self.lbl_status.config(text="Bereit – jetzt auf „Auswerten“ klicken.", style="Erfolg.TLabel")

    # ------------------------------------------------------------ Auswerten
    def _listen_anzeigen(self, follower: dict[str, str], following: dict[str, str]):
        self._angezeigt = (follower, following)
        suche = self.filter_var.get().strip().lower()
        self.listbox_following.delete(0, tk.END)
        self.listbox_followers.delete(0, tk.END)
        self.lbl_following_count.config(text=f"Ich folge ({len(following)})")
        self.lbl_follower_count.config(text=f"Folgen mir ({len(follower)})")
        for liste, daten, gegen in ((self.listbox_following, following, follower),
                                    (self.listbox_followers, follower, following)):
            for user, datum in sorted(daten.items()):
                if suche and suche not in user:
                    continue
                liste.insert(tk.END, f"  {user}  ·  seit {datum}")
                if user not in gegen:
                    liste.itemconfig(liste.size() - 1, {'fg': theme.ROT_DUNKEL})

    def auswerten(self, label: str | None = None):
        self._listen_anzeigen(self.follower_daten, self.following_daten)
        snapshot_id = history_store.snapshot_speichern(self.db_verbindung, self.follower_daten,
                                                       self.following_daten, label=label, besitzer=self.besitzer)
        self.letzter_snapshot_id = snapshot_id

        # Blockierte Profile und enge Freunde aus dem Export in die Listen übernehmen
        zusatz = ""
        neu_b = history_store.liste_hinzufuegen(self.db_verbindung, self.besitzer,
                                                PersonenListe.BLOCKIERT_VON_MIR, self.blockiert_aus_zip)
        neu_f = history_store.liste_hinzufuegen(self.db_verbindung, self.besitzer,
                                                PersonenListe.FREUNDE, self.enge_freunde_aus_zip)
        self.blockiert_aus_zip, self.enge_freunde_aus_zip = {}, {}
        if neu_b or neu_f:
            zusatz = f" Übernommen: {neu_b} blockierte Profile, {neu_f} enge Freunde."

        self.btn_entfolgen.config(state=tk.NORMAL)
        self.btn_freunde.config(state=tk.NORMAL)
        self.btn_auswerten.config(state=tk.DISABLED)  # verhindert doppelte Snapshots durch Doppelklick
        self.lbl_status.config(text=f"Ausgewertet und gespeichert.{zusatz}", style="Erfolg.TLabel")

    # ------------------------------------------------------------ Fenster öffnen
    def _snapshot_noetig(self) -> bool:
        if self.letzter_snapshot_id is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst Daten laden und auf „Auswerten“ klicken.")
            return False
        return True

    def oeffne_editor(self):
        vorher = (history_store.snapshot_laden(self.db_verbindung, self.letzter_snapshot_id, self.besitzer)
                  if self.letzter_snapshot_id else None)

        def uebernehmen(follower, following, label):
            self.follower_daten, self.following_daten = follower, following
            self.auswerten(label or "Eigene Liste")

        EditorFenster(self.root, self.plattform, uebernehmen,
                      vorher.follower if vorher else None, vorher.following if vorher else None)

    def oeffne_verlauf(self):
        HistoryFenster(self.root, self.db_verbindung, besitzer=self.besitzer, plattform=self.plattform)

    def oeffne_entfolgen_modus(self):
        if self._snapshot_noetig():
            RemovalFenster(self.root, self.db_verbindung, self.letzter_snapshot_id,
                           besitzer=self.besitzer, plattform=self.plattform)

    def oeffne_freunde(self):
        if self._snapshot_noetig():
            FreundeFenster(self.root, self.db_verbindung, self.letzter_snapshot_id,
                           besitzer=self.besitzer, plattform=self.plattform)

    def oeffne_kommentare(self):
        KommentareFenster(self.root, self.db_verbindung, self.besitzer)

    def oeffne_likes(self):
        LikesFenster(self.root, self.db_verbindung, self.besitzer)

    def oeffne_listen(self):
        ListenFenster(self.root, self.db_verbindung, besitzer=self.besitzer, plattform=self.plattform)
