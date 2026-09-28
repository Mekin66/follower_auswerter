"""
Web-Variante der Follower-Auswertung (Flask).

Nutzt dieselben core/-Module wie Desktop- und Mobile-App.

Lokal starten:
    pip install -r web/requirements.txt
    python web/app.py
    -> http://localhost:5000

Auf einem Server (siehe docs/VEROEFFENTLICHEN.md):
    gunicorn --workers 1 --threads 8 --bind 0.0.0.0:8000 web.app:app
    (WICHTIG: genau 1 Worker – laufende Entfolgen-Abläufe und
    Hintergrund-Prüfungen liegen im Arbeitsspeicher dieses Prozesses.)

Konto-Funktion an/aus: web/einstellungen.py -> ACCOUNTS_AKTIVIERT
"""

import datetime
import json
import secrets
import sqlite3
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core import history_store
from core.aktivitaet import (AKTIVITAET_URL, BEHALTEN, ENTFERNEN, FILTER_ALLE, FILTER_KRITISCH, FILTER_RISKANT,
                             KOMMENTAR, LIKE, AktivitaetAblauf, alle_zum_entfernen, kommentar_statistik,
                             like_statistik, such_link)
from core.anleitungen import ANLEITUNGEN, anleitung as anleitung_finden, kategorien as anleitungs_kategorien
from core.archive_reader import ExportFormatFehler, lade_export, lade_liste
from core.diff_engine import moegliche_blockierungen, vergleiche_snapshots
from core.export import aktivitaet_bericht, entfolgen_bericht, freunde_csv, namensliste_text
from core.freunde import freunde_ermitteln
from core.konto_pruefer import PruefungNichtMoeglich, pruefe_mehrere
from core.models import ENTSCHEIDUNG_TEXTE, LISTEN_TEXTE, Entscheidung, ListTyp, PersonenListe
from core.parser import normalisiere_username, usernames_aus_text
from core.plattform import PLATTFORM_TEXTE, Plattform, bereich, plattform_aus_text, profil_url
from core.txt_format import lese_txt, schreibe_txt
from core.removal_session import KATEGORIEN, EntfolgenAblauf, kategorien_ermitteln

try:  # funktioniert sowohl als "python web/app.py" als auch als Paket "web.app"
    from web import einstellungen as standard_einstellungen, konten, mail
except ImportError:  # pragma: no cover
    import einstellungen as standard_einstellungen  # type: ignore
    import konten  # type: ignore
    import mail  # type: ignore


# --------------------------------------------------------------------------
# Hintergrund-Prüfung (automatische "Scheint deaktiviert"-Erkennung)
# --------------------------------------------------------------------------

@dataclass
class PruefJob:
    gesamt: int
    erledigt: int = 0
    erkannt: int = 0
    letzter: str = ""
    fertig: bool = False
    abbrechen: bool = False
    fehler: str = ""                  # Grund, falls die Prüfung abgebrochen wurde
    gestartet: float = field(default_factory=time.time)


MAX_ABLAEUFE_IM_SPEICHER = 500


def create_app(**ueberschreiben) -> Flask:
    """App-Factory. `ueberschreiben` erlaubt Tests, Einstellungen zu ändern (z. B. ACCOUNTS_AKTIVIERT=True)."""
    cfg = {name: getattr(standard_einstellungen, name) for name in dir(standard_einstellungen) if name.isupper()}
    cfg.update(ueberschreiben)

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=cfg.get("SECRET_KEY") or standard_einstellungen.secret_key(),
        MAX_CONTENT_LENGTH=cfg["MAX_UPLOAD_MB"] * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cfg["COOKIES_NUR_HTTPS"],
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=30),
    )
    app.config["APP_EINSTELLUNGEN"] = cfg
    app.config["MAIL_POSTAUSGANG"] = []          # Testmodus: hier landen die "verschickten" Mails
    db_pfad = Path(cfg["DATENBANK_PFAD"])

    # Schema einmalig beim Start anlegen/migrieren
    _conn = history_store.init_db(db_pfad)
    konten.init_konten(_conn)
    _conn.close()

    lock = threading.RLock()
    ablaeufe: "OrderedDict[tuple[str, int], EntfolgenAblauf]" = OrderedDict()
    pruefjobs: dict[tuple[str, int], PruefJob] = {}
    fehlversuche: dict[str, list[float]] = {}
    letztes_aufraeumen = [0.0]

    def db_oeffnen() -> sqlite3.Connection:
        conn = sqlite3.connect(db_pfad, timeout=15)
        conn.execute("PRAGMA busy_timeout = 15000")
        return conn

    # ------------------------------------------------------------ Helfer
    def db() -> sqlite3.Connection:
        # Eine Verbindung PRO REQUEST. (Früher gab es eine globale Verbindung –
        # die hat im echten Flask-Server bei jedem Upload einen Fehler 500
        # ausgelöst, weil SQLite-Verbindungen nicht zwischen Threads geteilt
        # werden dürfen.)
        if "db" not in g:
            g.db = db_oeffnen()
        return g.db

    @app.teardown_appcontext
    def _db_schliessen(_fehler):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def konto_id() -> int | None:
        if not cfg["ACCOUNTS_AKTIVIERT"]:
            return None
        return session.get("konto_id")

    def volle_funktionen() -> bool:
        """Dauerhafte Markierungen, Kategorie-Auswahl, Listen: nur mit Konto."""
        return konto_id() is not None

    def anon_besitzer() -> str:
        if "anon_id" not in session:
            session["anon_id"] = secrets.token_urlsafe(18)
        return f"anon:{session['anon_id']}"

    def basis_besitzer() -> str:
        """Besitzer OHNE Plattform (für Konto-Funktionen)."""
        kid = konto_id()
        return konten.besitzer_id(kid) if kid is not None else anon_besitzer()

    def plattform() -> Plattform:
        return plattform_aus_text(session.get("plattform"))

    def besitzer() -> str:
        """Besitzer + Plattform: Instagram- und TikTok-Daten bleiben getrennt."""
        return bereich(basis_besitzer(), plattform())

    def snapshot_oder_404(snapshot_id: int):
        try:
            return history_store.snapshot_laden(db(), snapshot_id, besitzer())
        except ValueError:
            abort(404)

    def nur_mit_konto():
        if not volle_funktionen():
            abort(404)

    def konten_aktiv_oder_404():
        if not cfg["ACCOUNTS_AKTIVIERT"]:
            abort(404)

    def cookie_modus() -> str:
        modus = cfg.get("COOKIE_BANNER", "aus")
        return modus if modus in ("aus", "hinweis", "einwilligung") else "aus"

    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(24)
        return session["_csrf"]

    @app.context_processor
    def _vorlagen_variablen():
        kid = konto_id()
        benutzer = None
        if kid is not None:
            zeile = konten.konto_laden(db(), kid)
            benutzer = zeile[1] if zeile else None
        return {
            "csrf_token": csrf_token,
            "accounts_aktiviert": cfg["ACCOUNTS_AKTIVIERT"],
            "registrierung_offen": cfg["REGISTRIERUNG_OFFEN"],
            "volle_funktionen": kid is not None,
            "benutzername": benutzer,
            "auto_check_aktiviert": cfg["AUTO_CHECK_AKTIVIERT"],
            "aufbewahrung_stunden": cfg["ANONYM_AUFBEWAHRUNG_STUNDEN"],
            "cfg": cfg,
            "plattform": plattform(),
            "plattform_name": PLATTFORM_TEXTE[plattform()],
            "plattformen": PLATTFORM_TEXTE,
            "profil_url": lambda name: profil_url(plattform(), name),
            "cookie_modus": cookie_modus(),
            "cookie_banner_zeigen": cookie_modus() != "aus" and "cookie_wahl" not in session,
            "optionale_dienste_erlaubt": cookie_modus() == "einwilligung" and session.get("cookie_wahl") == "alle",
        }

    @app.before_request
    def _vor_jedem_request():
        # Konto gelöscht oder Konten-Funktion abgeschaltet -> Sitzung bereinigen
        if session.get("konto_id") is not None and cfg["ACCOUNTS_AKTIVIERT"]:
            if konten.konto_laden(db(), session["konto_id"]) is None:
                session.pop("konto_id", None)

        if request.method == "POST":
            gesendet = request.form.get("_csrf", "")
            if not gesendet or not secrets.compare_digest(gesendet, session.get("_csrf", "")):
                abort(400, description="Sicherheits-Token fehlt oder ist abgelaufen. Bitte Seite neu laden.")

        # Anonyme Altdaten und lange inaktive Konten höchstens alle 10 Minuten aufräumen
        if time.time() - letztes_aufraeumen[0] > 600:
            letztes_aufraeumen[0] = time.time()
            history_store.anonyme_daten_aufraeumen(db(), cfg["ANONYM_AUFBEWAHRUNG_STUNDEN"])
            konten.inaktive_konten_loeschen(db(), cfg.get("KONTO_LOESCHEN_NACH_TAGEN", 0))
            konten.unbestaetigte_konten_loeschen(db(), cfg.get("BESTAETIGUNG_GUELTIG_STUNDEN", 48))

    @app.errorhandler(413)
    def _zu_gross(_e):
        flash(f"Die Datei ist zu groß (max. {cfg['MAX_UPLOAD_MB']} MB). Tipp: Bei Instagram nur "
              "„Follower und gefolgte Personen“ im JSON-Format exportieren.")
        return redirect(url_for("start"))

    # ------------------------------------------------------------ Start & Laden
    @app.route("/")
    def start():
        return render_template("index.html")

    @app.route("/plattform", methods=["POST"])
    def plattform_wechseln():
        session["plattform"] = plattform_aus_text(request.form.get("plattform")).value
        ziel = request.form.get("zurueck", "")
        return redirect(ziel if ziel.startswith("/") and not ziel.startswith("//") else url_for("start"))

    def _auswertung_speichern(follower, following, blockiert=None, enge_freunde=None, label=None):
        conn = db()
        snapshot_id = history_store.snapshot_speichern(conn, follower, following, label=label, besitzer=besitzer())
        if volle_funktionen() and (blockiert or enge_freunde):
            neu_b = history_store.liste_hinzufuegen(conn, besitzer(), PersonenListe.BLOCKIERT_VON_MIR, blockiert or {})
            neu_f = history_store.liste_hinzufuegen(conn, besitzer(), PersonenListe.FREUNDE, enge_freunde or {})
            if neu_b or neu_f:
                flash(f"Aus dem Export übernommen: {neu_b} blockierte Profile, {neu_f} enge Freunde.")
        return redirect(url_for("ergebnis", snapshot_id=snapshot_id))

    @app.route("/laden", methods=["POST"])
    def laden():
        """Nimmt eine Export-Datei (ZIP/JSON, Instagram oder TikTok) ODER zwei einzelne Listen (JSON/TXT) an."""
        export_datei = request.files.get("zip_datei")
        follower_datei = request.files.get("follower_datei")
        following_datei = request.files.get("following_datei")
        follower: dict[str, str] = {}
        following: dict[str, str] = {}
        blockiert: dict[str, str] = {}
        enge_freunde: dict[str, str] = {}
        try:
            if export_datei and export_datei.filename:
                inhalt = lade_export(export_datei.stream, export_datei.filename)
                follower, following = inhalt.follower, inhalt.following
                blockiert, enge_freunde = inhalt.blockiert, inhalt.enge_freunde
                if inhalt.plattform != plattform():
                    session["plattform"] = inhalt.plattform.value
                    flash(f"{PLATTFORM_TEXTE[inhalt.plattform]}-Export erkannt – "
                          f"die Seite ist jetzt auf {PLATTFORM_TEXTE[inhalt.plattform]} umgestellt.")
            else:
                if follower_datei and follower_datei.filename:
                    follower = lade_liste(follower_datei.read(), follower_datei.filename)
                if following_datei and following_datei.filename:
                    following = lade_liste(following_datei.read(), following_datei.filename)
        except ExportFormatFehler as e:
            flash(str(e))
            return redirect(url_for("start"))
        except Exception as e:  # noqa: BLE001 – Nutzer soll eine verständliche Meldung sehen
            flash(f"Die Datei konnte nicht gelesen werden ({e}). Siehe Anleitung „Hilfe, es klappt nicht!“.")
            return redirect(url_for("start"))

        kommentare = inhalt.kommentare if export_datei and export_datei.filename else []
        likes = inhalt.likes if export_datei and export_datei.filename else []
        if not follower and not following and not kommentare and not likes:
            flash("Es konnten keine Daten gelesen werden. Enthält der Export Follower, Kommentare oder Likes?")
            return redirect(url_for("start"))
        if not kommentare and not likes:
            return _auswertung_speichern(follower, following, blockiert, enge_freunde)

        # Export mit Kommentaren/Likes: alles speichern und eine Übersicht zeigen, was gefunden wurde
        conn = db()
        neu_k = history_store.kommentare_speichern(conn, besitzer(), kommentare)
        neu_l = history_store.likes_speichern(conn, besitzer(), likes)
        snapshot_id = None
        if follower or following:
            snapshot_id = history_store.snapshot_speichern(conn, follower, following, besitzer=besitzer())
            if volle_funktionen():
                history_store.liste_hinzufuegen(conn, besitzer(), PersonenListe.BLOCKIERT_VON_MIR, blockiert)
                history_store.liste_hinzufuegen(conn, besitzer(), PersonenListe.FREUNDE, enge_freunde)
        session["letzter_import"] = {"enthaelt": inhalt.enthaelt(), "snapshot": snapshot_id,
                                     "neu_kommentare": neu_k, "neu_likes": neu_l}
        return redirect(url_for("import_uebersicht"))

    # ------------------------------------------------------------ Kommentare & Likes
    ARTEN = {"kommentare": KOMMENTAR, "likes": LIKE}
    aktivitaets_ablaeufe: dict[tuple[str, str], AktivitaetAblauf] = {}

    def _art(name: str) -> str:
        if name not in ARTEN:
            abort(404)
        return ARTEN[name]

    def _eintraege(art: str):
        return history_store.kommentare_laden(db(), besitzer()) if art == KOMMENTAR else history_store.likes_laden(db(), besitzer())

    @app.context_processor
    def _aktivitaet_helfer():
        return {"such_link": such_link, "aktivitaet_url": AKTIVITAET_URL}

    @app.route("/import")
    def import_uebersicht():
        info = session.get("letzter_import")
        if not info:
            return redirect(url_for("start"))
        return render_template("import.html", info=info)

    @app.route("/aktivitaet/<name>")
    def aktivitaet(name: str):
        """Startseite des Kommentar- bzw. Like-Modus: Übersicht, Filter, Start."""
        art = _art(name)
        eintraege = _eintraege(art)
        vorher = history_store.aktivitaet_entscheidungen_laden(db(), besitzer(), art)
        with lock:
            ablauf = aktivitaets_ablaeufe.get((besitzer(), art))
        return render_template("aktivitaet.html", modus="start", name=name, art=art, anzahl=len(eintraege),
                               entschieden=len(vorher), laufend=ablauf is not None and not ablauf.ist_fertig(),
                               statistik=kommentar_statistik(eintraege) if art == KOMMENTAR else None,
                               top=like_statistik(eintraege)[:50] if art == LIKE else None,
                               zu_entfernen=len(alle_zum_entfernen(db(), besitzer(), art)))

    @app.route("/aktivitaet/<name>/start", methods=["POST"])
    def aktivitaet_start(name: str):
        art = _art(name)
        vorher = history_store.aktivitaet_entscheidungen_laden(db(), besitzer(), art)
        erneut = bool(request.form.get("erneut"))
        if art == KOMMENTAR:
            filter_wert = request.form.get("filter", FILTER_RISKANT)
            if filter_wert not in (FILTER_KRITISCH, FILTER_RISKANT, FILTER_ALLE):
                filter_wert = FILTER_RISKANT
            ablauf = AktivitaetAblauf.fuer_kommentare(besitzer(), _eintraege(art), vorher, filter_wert, erneut)
        else:
            konto = normalisiere_username(request.form.get("account", "")) or None
            ablauf = AktivitaetAblauf.fuer_likes(besitzer(), _eintraege(art), vorher, konto, erneut)
        if not ablauf.reihenfolge:
            flash("Mit dieser Auswahl gibt es keine offenen Einträge.")
            return redirect(url_for("aktivitaet", name=name))
        with lock:
            aktivitaets_ablaeufe[(besitzer(), art)] = ablauf
        return redirect(url_for("aktivitaet_durchgang", name=name))

    @app.route("/aktivitaet/<name>/durchgang")
    def aktivitaet_durchgang(name: str):
        art = _art(name)
        with lock:
            ablauf = aktivitaets_ablaeufe.get((besitzer(), art))
        if ablauf is None:
            return redirect(url_for("aktivitaet", name=name))
        if ablauf.ist_fertig():
            return redirect(url_for("aktivitaet_liste", name=name))
        eintrag = ablauf.aktueller()
        erledigt, gesamt = ablauf.fortschritt()
        return render_template("aktivitaet.html", modus="durchgang", name=name, art=art, eintrag=eintrag,
                               bewertung=ablauf.bewertung(eintrag), erledigt=erledigt, gesamt=gesamt,
                               kann_zurueck=ablauf.kann_zurueck())

    @app.route("/aktivitaet/<name>/entscheiden", methods=["POST"])
    def aktivitaet_entscheiden(name: str):
        art = _art(name)
        with lock:
            ablauf = aktivitaets_ablaeufe.get((besitzer(), art))
            if ablauf is not None:
                aktuell = ablauf.aktueller()
                wert = request.form.get("entscheidung")
                if request.form.get("zurueck"):
                    ablauf.zurueck(db())
                elif aktuell is not None and request.form.get("id") == aktuell.id and wert in (ENTFERNEN, BEHALTEN):
                    ablauf.entscheide(db(), wert)
        return redirect(url_for("aktivitaet_durchgang", name=name))

    @app.route("/aktivitaet/<name>/liste")
    def aktivitaet_liste(name: str):
        """Alles, was zum Entfernen markiert ist – mit Links, zum Abarbeiten auf Instagram."""
        art = _art(name)
        return render_template("aktivitaet.html", modus="liste", name=name, art=art,
                               eintraege=alle_zum_entfernen(db(), besitzer(), art))

    @app.route("/aktivitaet/<name>/export")
    def aktivitaet_export(name: str):
        art = _art(name)
        return Response(aktivitaet_bericht(art, alle_zum_entfernen(db(), besitzer(), art)),
                        mimetype="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={name}_zum_entfernen.txt"})

    @app.route("/aktivitaet/<name>/leeren", methods=["POST"])
    def aktivitaet_leeren(name: str):
        art = _art(name)
        history_store.aktivitaet_leeren(db(), besitzer(), art)
        with lock:
            aktivitaets_ablaeufe.pop((besitzer(), art), None)
        flash("Importierte Daten und Entscheidungen gelöscht.")
        return redirect(url_for("aktivitaet", name=name))

    # ------------------------------------------------------------ Listen-Editor
    @app.route("/editor", methods=["GET", "POST"])
    def editor():
        """Listen selbst eintippen oder TXT-Dateien laden/speichern, dann auswerten."""
        if request.method == "POST":
            follower = lese_txt(request.form.get("follower", ""))
            following = lese_txt(request.form.get("following", ""))
            aktion = request.form.get("aktion", "auswerten")
            if aktion in ("txt_follower", "txt_following"):
                daten, titel = (follower, "Follower") if aktion == "txt_follower" else (following, "Following")
                return Response(schreibe_txt(daten, f"{PLATTFORM_TEXTE[plattform()]} {titel}"),
                                mimetype="text/plain; charset=utf-8",
                                headers={"Content-Disposition": f"attachment; filename={titel.lower()}.txt"})
            if not follower and not following:
                flash("Bitte mindestens eine Liste ausfüllen.")
                return render_template("editor.html", follower_text=request.form.get("follower", ""),
                                       following_text=request.form.get("following", ""))
            label = (request.form.get("label") or "").strip()[:80] or None
            return _auswertung_speichern(follower, following, label=label or f"Eigene Liste vom {datetime.datetime.now():%d.%m.%Y %H:%M}")
        follower_text = following_text = ""
        von = request.args.get("von", type=int)
        if von:
            snap = snapshot_oder_404(von)
            follower_text = schreibe_txt(snap.follower, "Follower")
            following_text = schreibe_txt(snap.following, "Following")
        return render_template("editor.html", follower_text=follower_text, following_text=following_text,
                               letzter=history_store.letzten_snapshot_id(db(), besitzer()))

    # ------------------------------------------------------------ Anleitungen
    @app.route("/anleitung")
    @app.route("/anleitung/<id>")
    def anleitung(id: str | None = None):
        gewaehlt = anleitung_finden(id) if id else None
        if id and gewaehlt is None:
            abort(404)
        return render_template("anleitung.html", gruppen=anleitungs_kategorien(), gewaehlt=gewaehlt)

    # ------------------------------------------------------------ Ergebnis
    @app.route("/ergebnis/<int:snapshot_id>")
    def ergebnis(snapshot_id: int):
        snapshot = snapshot_oder_404(snapshot_id)
        markierungen = history_store.markierungen_laden(db(), besitzer()) if volle_funktionen() else {}
        following_liste = [
            {"username": u, "seit": d, "folgt_zurueck": u in snapshot.follower,
             "markierung": markierungen.get(u)}
            for u, d in sorted(snapshot.following.items())
        ]
        follower_liste = [
            {"username": u, "seit": d, "wird_zurueckgefolgt": u in snapshot.following}
            for u, d in sorted(snapshot.follower.items())
        ]
        gegenseitig = len(set(snapshot.follower) & set(snapshot.following))
        return render_template("ergebnis.html", snapshot=snapshot, following_liste=following_liste,
                               follower_liste=follower_liste, gegenseitig=gegenseitig,
                               nicht_zurueck=sum(1 for e in following_liste if not e["folgt_zurueck"]),
                               entscheidung_texte=ENTSCHEIDUNG_TEXTE)

    # ------------------------------------------------------------ Freunde
    def _freunde(snapshot):
        manuell = history_store.liste_laden(db(), besitzer(), PersonenListe.FREUNDE) if volle_funktionen() else {}
        return freunde_ermitteln(snapshot.follower, snapshot.following, manuell)

    @app.route("/freunde/<int:snapshot_id>")
    def freunde(snapshot_id: int):
        snapshot = snapshot_oder_404(snapshot_id)
        return render_template("freunde.html", snapshot=snapshot, freunde=_freunde(snapshot))

    @app.route("/freunde/<int:snapshot_id>/export.<format>")
    def freunde_export(snapshot_id: int, format: str):
        snapshot = snapshot_oder_404(snapshot_id)
        liste = _freunde(snapshot)
        if format == "csv":
            return Response("﻿" + freunde_csv(liste), mimetype="text/csv",
                            headers={"Content-Disposition": "attachment; filename=freunde.csv"})
        if format == "txt":
            return Response(namensliste_text("Freunde", [f.username for f in liste]), mimetype="text/plain",
                            headers={"Content-Disposition": "attachment; filename=freunde.txt"})
        abort(404)

    # ------------------------------------------------------------ Verlauf
    @app.route("/verlauf")
    def verlauf():
        return render_template("verlauf.html", snapshots=history_store.snapshots_auflisten(db(), besitzer()))

    @app.route("/verlauf/vergleichen", methods=["POST"])
    def verlauf_vergleichen():
        try:
            id_alt, id_neu = int(request.form["id_alt"]), int(request.form["id_neu"])
        except (KeyError, ValueError):
            abort(400)
        if id_alt == id_neu:
            flash("Bitte zwei unterschiedliche Zeitpunkte auswählen.")
            return redirect(url_for("verlauf"))

        snap_alt, snap_neu = snapshot_oder_404(id_alt), snapshot_oder_404(id_neu)
        aenderungen = vergleiche_snapshots(snap_alt, snap_neu)
        verdacht = moegliche_blockierungen(snap_alt, snap_neu)
        bekannt_blockiert = set()
        if volle_funktionen():
            bekannt_blockiert = set(history_store.liste_laden(db(), besitzer(), PersonenListe.BLOCKIERT_MICH)) | \
                set(history_store.liste_laden(db(), besitzer(), PersonenListe.BLOCKIERT_VON_MIR))
        return render_template(
            "vergleich.html", snap_alt=snap_alt, snap_neu=snap_neu,
            follower_aenderungen=[a for a in aenderungen if a.liste == ListTyp.FOLLOWER],
            following_aenderungen=[a for a in aenderungen if a.liste == ListTyp.FOLLOWING],
            verdacht=verdacht, bekannt_blockiert=bekannt_blockiert,
        )

    @app.route("/verlauf/<int:snapshot_id>/loeschen", methods=["POST"])
    def snapshot_loeschen(snapshot_id: int):
        if history_store.snapshot_loeschen(db(), snapshot_id, besitzer()):
            with lock:
                ablaeufe.pop((besitzer(), snapshot_id), None)
            flash("Auswertung gelöscht.")
        return redirect(url_for("verlauf"))

    # ------------------------------------------------------------ Entfolgen-Modus
    def _ablauf(snapshot_id: int) -> EntfolgenAblauf | None:
        with lock:
            return ablaeufe.get((besitzer(), snapshot_id))

    def _ablauf_speichern(snapshot_id: int, ablauf: EntfolgenAblauf) -> None:
        with lock:
            ablaeufe[(besitzer(), snapshot_id)] = ablauf
            ablaeufe.move_to_end((besitzer(), snapshot_id))
            while len(ablaeufe) > MAX_ABLAEUFE_IM_SPEICHER:
                ablaeufe.popitem(last=False)

    def _ablauf_erstellen(snapshot, erneut: set[str] | None) -> EntfolgenAblauf:
        conn = db()
        if volle_funktionen():
            markierungen = history_store.markierungen_laden(conn, besitzer())
            freunde_m = set(history_store.liste_laden(conn, besitzer(), PersonenListe.FREUNDE))
        else:
            markierungen, freunde_m, erneut = {}, set(), None
        ablauf = EntfolgenAblauf(besitzer(), snapshot, markierungen, freunde_m, erneut)
        if not cfg["AUTO_CHECK_AKTIVIERT"]:
            ablauf.automatisch_geprueft = True
        _ablauf_speichern(snapshot.id, ablauf)
        return ablauf

    @app.route("/entfolgen/<int:snapshot_id>")
    def entfolgen(snapshot_id: int):
        snapshot = snapshot_oder_404(snapshot_id)
        ablauf = _ablauf(snapshot_id)

        if ablauf is None:
            if volle_funktionen():
                uebersicht = kategorien_ermitteln(
                    snapshot, history_store.markierungen_laden(db(), besitzer()),
                    set(history_store.liste_laden(db(), besitzer(), PersonenListe.FREUNDE)))
                if any(uebersicht.anzahl(k) for k, _ in KATEGORIEN):
                    return render_template("entfolgen.html", modus="auswahl", snapshot_id=snapshot_id,
                                           uebersicht=uebersicht, kategorien=KATEGORIEN)
                ablauf = _ablauf_erstellen(snapshot, set())
            else:
                ablauf = _ablauf_erstellen(snapshot, None)

        with lock:
            job = pruefjobs.get((besitzer(), snapshot_id))
            if job and not job.fertig:
                return render_template("entfolgen.html", modus="pruefung", snapshot_id=snapshot_id, job=job)
            if job and job.fertig:
                pruefjobs.pop((besitzer(), snapshot_id), None)
                ablauf.automatisch_geprueft = True
                if job.fehler:
                    flash(f"Automatische Prüfung gestoppt: {job.fehler}")
                flash(f"Automatische Prüfung: {job.erledigt} geprüft, {job.erkannt} Vorschlag/Vorschläge.")

            basis = {"snapshot_id": snapshot_id, "ablauf": ablauf, "kategorien": dict(KATEGORIEN)}
            if not ablauf.session.kandidaten:
                return render_template("entfolgen.html", modus="leer", **basis)
            if ablauf.ist_fertig():
                return render_template("entfolgen.html", modus="fertig", zusammenfassung=ablauf.zusammenfassung(),
                                       texte=ENTSCHEIDUNG_TEXTE, **basis)
            if ablauf.vorschlaege_offen:
                return render_template("entfolgen.html", modus="vorschlaege", vorschlaege=ablauf.vorschlaege, **basis)
            offen = len(ablauf.offene())
            if not ablauf.automatisch_geprueft:
                anzahl = min(offen, cfg["AUTO_CHECK_MAX_ACCOUNTS"])
                return render_template("entfolgen.html", modus="angebot", anzahl_offen=offen, anzahl_pruefen=anzahl,
                                       geschaetzte_sekunden=int(anzahl * (cfg["AUTO_CHECK_PAUSE_SEKUNDEN"] + 1)),
                                       **basis)
            kandidat = ablauf.aktueller_kandidat()
            entschieden, gesamt = ablauf.fortschritt()
            return render_template("entfolgen.html", modus="wizard", kandidat=kandidat, seit=ablauf.seit(kandidat),
                                   bisher=ablauf.bisherige_markierung(kandidat) if volle_funktionen() else None,
                                   entschieden=entschieden, gesamt=gesamt, texte=ENTSCHEIDUNG_TEXTE, **basis)

    @app.route("/entfolgen/<int:snapshot_id>/start", methods=["POST"])
    def entfolgen_start(snapshot_id: int):
        nur_mit_konto()
        snapshot = snapshot_oder_404(snapshot_id)
        gueltig = {k for k, _ in KATEGORIEN}
        erneut = {k for k in request.form.getlist("erneut") if k in gueltig}
        _ablauf_erstellen(snapshot, erneut)
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/neu", methods=["POST"])
    def entfolgen_neu(snapshot_id: int):
        snapshot_oder_404(snapshot_id)
        with lock:
            job = pruefjobs.pop((besitzer(), snapshot_id), None)
            if job:
                job.abbrechen = True
            ablaeufe.pop((besitzer(), snapshot_id), None)
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/automatisch", methods=["POST"])
    def entfolgen_automatisch(snapshot_id: int):
        if not cfg["AUTO_CHECK_AKTIVIERT"]:
            abort(404)
        snapshot_oder_404(snapshot_id)
        ablauf = _ablauf(snapshot_id)
        if ablauf is None:
            return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

        schluessel = (besitzer(), snapshot_id)
        with lock:
            if schluessel in pruefjobs and not pruefjobs[schluessel].fertig:
                return redirect(url_for("entfolgen", snapshot_id=snapshot_id))
            offene = ablauf.offene()[: cfg["AUTO_CHECK_MAX_ACCOUNTS"]]
            job = PruefJob(gesamt=len(offene))
            pruefjobs[schluessel] = job
        plattform_des_jobs = plattform()   # im Thread gibt es keine Session mehr -> vorher merken

        def im_hintergrund():
            try:
                for erg in pruefe_mehrere(offene, cfg["AUTO_CHECK_PAUSE_SEKUNDEN"],
                                          abbrechen=lambda: job.abbrechen, plattform=plattform_des_jobs):
                    with lock:
                        if ablauf.auto_ergebnis_uebernehmen(None, erg):   # nur Vorschlag, schreibt nichts
                            job.erkannt += 1
                        job.erledigt += 1
                        job.letzter = f"{erg.username} ({erg.status.value})"
            except PruefungNichtMoeglich as e:
                job.fehler = str(e)
            except Exception as e:  # noqa: BLE001
                job.fehler = f"Unerwarteter Fehler bei der Prüfung: {e}"
            finally:
                job.fertig = True

        threading.Thread(target=im_hintergrund, daemon=True).start()
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/vorschlaege", methods=["POST"])
    def entfolgen_vorschlaege(snapshot_id: int):
        """Nur die angehakten Vorschläge werden als 'Scheint deaktiviert' übernommen."""
        ablauf = _ablauf(snapshot_id)
        if ablauf:
            with lock:
                anzahl = ablauf.vorschlaege_bestaetigen(db(), [normalisiere_username(n) for n in request.form.getlist("auswahl")])
            flash(f"{anzahl} Account(s) als „Scheint deaktiviert“ übernommen.")
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/abbrechen", methods=["POST"])
    def entfolgen_abbrechen(snapshot_id: int):
        with lock:
            job = pruefjobs.get((besitzer(), snapshot_id))
            if job:
                job.abbrechen = True
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/ueberspringen", methods=["POST"])
    def entfolgen_ueberspringen(snapshot_id: int):
        ablauf = _ablauf(snapshot_id)
        if ablauf:
            ablauf.automatisch_geprueft = True
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/entscheiden", methods=["POST"])
    def entfolgen_entscheiden(snapshot_id: int):
        ablauf = _ablauf(snapshot_id)
        if ablauf is None:
            return redirect(url_for("entfolgen", snapshot_id=snapshot_id))
        try:
            entscheidung = Entscheidung(request.form.get("entscheidung", ""))
        except ValueError:
            abort(400)
        # Schutz gegen Doppelklick/Zurück-Button im Browser: nur entscheiden,
        # wenn das Formular für den aktuell angezeigten Kandidaten abgeschickt wurde.
        with lock:
            if request.form.get("kandidat") == ablauf.aktueller_kandidat():
                ablauf.entscheide(db(), entscheidung)
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/zurueck", methods=["POST"])
    def entfolgen_zurueck(snapshot_id: int):
        ablauf = _ablauf(snapshot_id)
        if ablauf:
            with lock:
                ablauf.zurueck(db())
        return redirect(url_for("entfolgen", snapshot_id=snapshot_id))

    @app.route("/entfolgen/<int:snapshot_id>/export")
    def entfolgen_export(snapshot_id: int):
        snapshot_oder_404(snapshot_id)
        ablauf = _ablauf(snapshot_id)
        if ablauf is None:
            abort(404)
        return Response(entfolgen_bericht(ablauf.zusammenfassung(), ablauf.noch_zu_entfolgen()),
                        mimetype="text/plain",
                        headers={"Content-Disposition": "attachment; filename=entfolgen_ergebnis.txt"})

    # ------------------------------------------------------------ Listen (nur mit Konto)
    @app.route("/listen")
    def listen():
        nur_mit_konto()
        conn = db()
        aktiv = request.args.get("tab", PersonenListe.FREUNDE.value)
        if aktiv not in {pl.value for pl in PersonenListe} | {"markierungen"}:
            aktiv = PersonenListe.FREUNDE.value
        daten = {liste.value: history_store.liste_laden(conn, besitzer(), liste) for liste in PersonenListe}
        markierungen = history_store.markierungen_mit_datum(conn, besitzer())
        return render_template("listen.html", daten=daten, listen_texte={k.value: v for k, v in LISTEN_TEXTE.items()},
                               markierungen=markierungen, texte=ENTSCHEIDUNG_TEXTE, aktiv=aktiv)

    def _liste_aus_url(name: str) -> PersonenListe:
        try:
            return PersonenListe(name)
        except ValueError:
            abort(404)

    @app.route("/listen/<liste>/hinzufuegen", methods=["POST"])
    def liste_hinzufuegen(liste: str):
        nur_mit_konto()
        pl = _liste_aus_url(liste)
        namen = usernames_aus_text(request.form.get("namen", ""))
        neu = history_store.liste_hinzufuegen(db(), besitzer(), pl, namen)
        flash(f"{neu} Account(s) zu „{LISTEN_TEXTE[pl]}“ hinzugefügt." if neu else "Keine neuen Accounts hinzugefügt.")
        ziel = request.form.get("zurueck", "")
        if not (ziel.startswith("/") and not ziel.startswith("//")):  # nur interne Weiterleitungen
            ziel = url_for("listen", tab=pl.value)
        return redirect(ziel)

    @app.route("/listen/<liste>/entfernen", methods=["POST"])
    def liste_entfernen(liste: str):
        nur_mit_konto()
        pl = _liste_aus_url(liste)
        history_store.liste_entfernen(db(), besitzer(), pl, normalisiere_username(request.form.get("username", "")))
        return redirect(url_for("listen", tab=pl.value))

    def _auswahl_aus_formular() -> list[str]:
        """Massenauswahl: angehakte Nutzernamen – oder nur einer, wenn ein Zeilen-Knopf gedrückt wurde."""
        if request.form.get("nur"):
            return [normalisiere_username(request.form["nur"])]
        return [n for n in (normalisiere_username(u) for u in request.form.getlist("auswahl")) if n]

    @app.route("/listen/<liste>/sammel", methods=["POST"])
    def liste_sammelaktion(liste: str):
        nur_mit_konto()
        pl = _liste_aus_url(liste)
        namen = _auswahl_aus_formular()
        aktion = request.form.get("aktion", "entfernen")
        if not namen:
            flash("Keine Accounts ausgewählt.")
        elif aktion == "entfernen":
            anzahl = history_store.liste_mehrere_entfernen(db(), besitzer(), pl, namen)
            flash(f"{anzahl} Account(s) aus „{LISTEN_TEXTE[pl]}“ entfernt.")
        elif aktion.startswith("verschieben:") or aktion.startswith("kopieren:"):
            art, _, ziel_name = aktion.partition(":")
            ziel = _liste_aus_url(ziel_name)
            history_store.liste_hinzufuegen(db(), besitzer(), ziel, namen)
            if art == "verschieben" and ziel != pl:
                history_store.liste_mehrere_entfernen(db(), besitzer(), pl, namen)
            flash(f"{len(namen)} Account(s) nach „{LISTEN_TEXTE[ziel]}“ "
                  f"{'verschoben' if art == 'verschieben' else 'kopiert'}.")
        else:
            abort(400)
        return redirect(url_for("listen", tab=pl.value))

    @app.route("/markierungen/sammel", methods=["POST"])
    def markierungen_sammelaktion():
        nur_mit_konto()
        namen = _auswahl_aus_formular()
        wert = request.form.get("markierung", "")
        if not namen:
            flash("Keine Accounts ausgewählt.")
            return redirect(url_for("listen", tab="markierungen"))
        try:
            markierung = None if wert == "entfernen" else Entscheidung(wert)
        except ValueError:
            abort(400)
        anzahl = history_store.markierungen_mehrere_setzen(db(), besitzer(), namen, markierung)
        flash(f"{anzahl} Markierung(en) {'entfernt' if markierung is None else 'geändert'}.")
        return redirect(url_for("listen", tab="markierungen"))

    @app.route("/listen/<liste>/export")
    def liste_export(liste: str):
        nur_mit_konto()
        pl = _liste_aus_url(liste)
        namen = history_store.liste_laden(db(), besitzer(), pl)
        return Response(namensliste_text(LISTEN_TEXTE[pl], namen), mimetype="text/plain",
                        headers={"Content-Disposition": f"attachment; filename={pl.value}.txt"})

    @app.route("/markierungen/aendern", methods=["POST"])
    def markierung_aendern():
        nur_mit_konto()
        username = normalisiere_username(request.form.get("username", ""))
        neu = request.form.get("markierung", "")
        if neu == "entfernen":
            history_store.markierung_loeschen(db(), besitzer(), username)
        else:
            try:
                history_store.markierung_setzen(db(), besitzer(), username, Entscheidung(neu))
            except ValueError:
                abort(400)
        return redirect(url_for("listen", tab="markierungen"))

    # ------------------------------------------------------------ Konten
    def _zu_viele_fehlversuche() -> bool:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
        jetzt = time.time()
        with lock:
            versuche = [t for t in fehlversuche.get(ip, []) if jetzt - t < 900]
            fehlversuche[ip] = versuche
            return len(versuche) >= 10

    def _fehlversuch_merken():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()
        with lock:
            fehlversuche.setdefault(ip, []).append(time.time())

    def _einloggen(kid: int):
        konten.login_merken(db(), kid)
        anon = session.get("anon_id")
        uebernommen = konten.anonyme_daten_uebernehmen(db(), f"anon:{anon}", kid) if anon else 0
        csrf, gewaehlte_plattform, cookie_wahl = session.get("_csrf"), session.get("plattform"), session.get("cookie_wahl")
        session.clear()  # Schutz vor Session-Fixation
        session["konto_id"] = kid
        session["_csrf"] = csrf or secrets.token_urlsafe(24)
        if gewaehlte_plattform:
            session["plattform"] = gewaehlte_plattform
        if cookie_wahl:
            session["cookie_wahl"] = cookie_wahl
        session.permanent = True
        with lock:
            for schluessel in [k for k in ablaeufe if k[0].split("#")[0] == f"anon:{anon}"]:
                ablaeufe.pop(schluessel, None)
        if uebernommen:
            flash(f"{uebernommen} Auswertung(en) aus dieser Sitzung wurden in dein Konto übernommen.")

    # ---- E-Mail-Links (Bestätigung, Passwort vergessen)
    # Die Links enthalten ein signiertes "Token" (itsdangerous, gehört zu Flask).
    # Es kann nicht gefälscht werden, weil es mit dem SECRET_KEY unterschrieben ist,
    # und es läuft nach der eingestellten Zeit ab. Eine Datenbanktabelle ist nicht nötig.
    token_signierer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

    def _token(zweck: str, daten: dict) -> str:
        return token_signierer.dumps(daten, salt=zweck)

    def _token_lesen(zweck: str, token: str, max_sekunden: int) -> dict | None:
        try:
            return token_signierer.loads(token, salt=zweck, max_age=max_sekunden)
        except (BadSignature, SignatureExpired):
            return None

    def _link(endpunkt: str, **werte) -> str:
        """Absoluter Link für E-Mails. Nutzt OEFFENTLICHE_URL (sicher gegen gefälschte Host-Header)."""
        if cfg.get("OEFFENTLICHE_URL"):
            return cfg["OEFFENTLICHE_URL"] + url_for(endpunkt, **werte)
        return url_for(endpunkt, _external=True, **werte)

    def _mail(an: str, inhalt: tuple[str, str]) -> bool:
        try:
            mail.senden(cfg, an, inhalt[0], inhalt[1], app.config["MAIL_POSTAUSGANG"])
            return True
        except mail.MailFehler:
            flash("Die E-Mail konnte gerade nicht verschickt werden. Bitte später erneut versuchen.")
            return False

    def _bestaetigungs_mail(kid: int, email: str, neue_adresse: bool = False) -> bool:
        info = konten.konto_info(db(), kid)
        link = _link("email_bestaetigen", token=_token("email", {"id": kid, "email": email}))
        stunden = cfg["BESTAETIGUNG_GUELTIG_STUNDEN"]
        text = (mail.text_neue_adresse if neue_adresse else mail.text_bestaetigung)(info["benutzername"], link, stunden)
        return _mail(email, text)

    def _schon_registriert_mail(email: str):
        _mail(email, mail.text_schon_registriert(_link("anmelden"), _link("passwort_vergessen")))

    def _email_seite(email: str):
        """Einheitliche Antwort: 'Schau in dein Postfach' – verrät nicht, ob die Adresse schon existiert."""
        return render_template("konto_hinweis.html", modus="postfach", email=email,
                               testmodus=mail.ist_testmodus(cfg))

    @app.route("/registrieren", methods=["GET", "POST"])
    def registrieren():
        konten_aktiv_oder_404()
        if not cfg["REGISTRIERUNG_OFFEN"]:
            flash("Die Registrierung ist derzeit geschlossen.")
            return redirect(url_for("anmelden"))
        if request.method == "POST":
            if not request.form.get("zustimmung"):
                flash("Bitte bestätige, dass du die Datenschutzhinweise gelesen hast.")
                return render_template("konto_formular.html", modus="registrieren")
            if _zu_viele_fehlversuche():
                flash("Zu viele Versuche. Bitte in 15 Minuten erneut versuchen.")
                return render_template("konto_formular.html", modus="registrieren"), 429
            bestaetigen = cfg["E_MAIL_BESTAETIGUNG"]
            email_eingabe = request.form.get("email", "")
            try:
                kid = konten.registrieren(
                    db(), request.form.get("benutzername", ""), request.form.get("passwort", ""),
                    request.form.get("passwort2", ""), email=email_eingabe,
                    email_pflicht=cfg["E_MAIL_PFLICHT"] or bestaetigen, freigeschaltet=not bestaetigen,
                    newsletter=cfg["NEWSLETTER_ABFRAGEN"] and bool(request.form.get("newsletter")))
            except konten.EmailVergeben:
                _fehlversuch_merken()                                   # bremst massenhaftes Durchprobieren
                _schon_registriert_mail(konten.email_normalisieren(email_eingabe))
                return _email_seite(konten.email_normalisieren(email_eingabe))
            except konten.KontoFehler as e:
                flash(str(e))
                return render_template("konto_formular.html", modus="registrieren")
            if bestaetigen:
                email = konten.konto_info(db(), kid)["email"]
                _bestaetigungs_mail(kid, email)
                return _email_seite(email)
            _einloggen(kid)
            flash("Konto erstellt – willkommen!")
            return redirect(url_for("start"))
        return render_template("konto_formular.html", modus="registrieren")

    @app.route("/bestaetigen/<token>")
    def email_bestaetigen(token: str):
        konten_aktiv_oder_404()
        daten = _token_lesen("email", token, cfg["BESTAETIGUNG_GUELTIG_STUNDEN"] * 3600)
        ergebnis = konten.email_bestaetigen(db(), daten["id"], daten["email"]) if daten else "ungueltig"
        if ergebnis == "ungueltig":
            return render_template("konto_hinweis.html", modus="ungueltig"), 400
        if ergebnis == "schon":
            flash("Deine E-Mail-Adresse war bereits bestätigt. Bitte melde dich an.")
            return redirect(url_for("anmelden"))
        if ergebnis == "geaendert":
            flash("Deine neue E-Mail-Adresse ist bestätigt.")
            return redirect(url_for("konto") if konto_id() == daten["id"] else url_for("anmelden"))
        _einloggen(daten["id"])                     # erstes Bestätigen = direkt angemeldet
        flash("E-Mail bestätigt – dein Konto ist aktiv. Willkommen!")
        return redirect(url_for("start"))

    @app.route("/bestaetigung/erneut", methods=["GET", "POST"])
    def bestaetigung_erneut():
        konten_aktiv_oder_404()
        if request.method == "POST":
            if _zu_viele_fehlversuche():
                flash("Zu viele Versuche. Bitte in 15 Minuten erneut versuchen.")
                return render_template("konto_hinweis.html", modus="erneut"), 429
            _fehlversuch_merken()
            treffer = konten.konto_per_name_oder_email(db(), request.form.get("eingabe", ""))
            if treffer and treffer[2] and not konten.ist_freigeschaltet(db(), treffer[0]):
                _bestaetigungs_mail(treffer[0], treffer[2])
            return _email_seite("")
        return render_template("konto_hinweis.html", modus="erneut")

    @app.route("/anmelden", methods=["GET", "POST"])
    def anmelden():
        konten_aktiv_oder_404()
        if request.method == "POST":
            if _zu_viele_fehlversuche():
                flash("Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen.")
                return render_template("konto_formular.html", modus="anmelden"), 429
            kid = konten.anmelden(db(), request.form.get("benutzername", ""), request.form.get("passwort", ""))
            if kid is None:
                _fehlversuch_merken()
                flash("Benutzername/E-Mail oder Passwort falsch.")
                return render_template("konto_formular.html", modus="anmelden")
            if not konten.ist_freigeschaltet(db(), kid):
                # Passwort war richtig -> wir dürfen sagen, dass nur die Bestätigung fehlt
                return render_template("konto_hinweis.html", modus="unbestaetigt",
                                       email=konten.konto_info(db(), kid)["email"])
            _einloggen(kid)
            return redirect(url_for("start"))
        return render_template("konto_formular.html", modus="anmelden")

    @app.route("/passwort-vergessen", methods=["GET", "POST"])
    def passwort_vergessen():
        konten_aktiv_oder_404()
        if request.method == "POST":
            if _zu_viele_fehlversuche():
                flash("Zu viele Versuche. Bitte in 15 Minuten erneut versuchen.")
                return render_template("konto_hinweis.html", modus="passwort_vergessen"), 429
            _fehlversuch_merken()
            treffer = konten.konto_per_name_oder_email(db(), request.form.get("eingabe", ""))
            if treffer and treffer[2]:
                kid, name, email = treffer
                link = _link("passwort_neu", token=_token(
                    "passwort", {"id": kid, "fp": konten.passwort_fingerabdruck(db(), kid)}))
                _mail(email, mail.text_passwort(name, link, cfg["PASSWORT_LINK_GUELTIG_MINUTEN"]))
            return _email_seite("")
        return render_template("konto_hinweis.html", modus="passwort_vergessen")

    @app.route("/passwort-neu/<token>", methods=["GET", "POST"])
    def passwort_neu(token: str):
        konten_aktiv_oder_404()
        daten = _token_lesen("passwort", token, cfg["PASSWORT_LINK_GUELTIG_MINUTEN"] * 60)
        if not daten or daten.get("fp") != konten.passwort_fingerabdruck(db(), daten.get("id", -1)):
            return render_template("konto_hinweis.html", modus="ungueltig"), 400
        if request.method == "POST":
            try:
                konten.passwort_setzen(db(), daten["id"], request.form.get("neu", ""), request.form.get("neu2", ""))
            except konten.KontoFehler as e:
                flash(str(e))
                return render_template("konto_hinweis.html", modus="passwort_neu")
            # Wer den Link aus der Mail benutzt, hat Zugriff auf das Postfach -> Adresse gilt als bestätigt
            konten.email_bestaetigen(db(), daten["id"], konten.konto_info(db(), daten["id"])["email"])
            _einloggen(daten["id"])
            flash("Neues Passwort gespeichert. Du bist angemeldet.")
            return redirect(url_for("start"))
        return render_template("konto_hinweis.html", modus="passwort_neu")

    @app.route("/abmelden", methods=["POST"])
    def abmelden():
        cookie_wahl = session.get("cookie_wahl")
        session.clear()
        if cookie_wahl:
            session["cookie_wahl"] = cookie_wahl
        flash("Du bist abgemeldet.")
        return redirect(url_for("start"))

    @app.route("/konto", methods=["GET", "POST"])
    def konto():
        konten_aktiv_oder_404()
        kid = konto_id()
        if kid is None:
            return redirect(url_for("anmelden"))
        if request.method == "POST":
            aktion = request.form.get("aktion", "passwort")
            try:
                if aktion == "email":
                    neu = request.form.get("email", "")
                    try:
                        adresse = konten.email_aendern_anfordern(db(), kid, neu, request.form.get("passwort", ""))
                        _bestaetigungs_mail(kid, adresse, neue_adresse=True)
                    except konten.EmailVergeben:
                        _schon_registriert_mail(konten.email_normalisieren(neu))
                    flash("Wir haben einen Bestätigungs-Link an die neue Adresse geschickt. "
                          "Bis zur Bestätigung bleibt die bisherige Adresse aktiv.")
                elif aktion == "email_erneut":
                    info = konten.konto_info(db(), kid)
                    ziel = info["email_neu"] or info["email"]
                    if ziel and _bestaetigungs_mail(kid, ziel, neue_adresse=bool(info["email_neu"])):
                        flash("Bestätigungs-Link erneut gesendet.")
                elif aktion == "newsletter":
                    konten.newsletter_setzen(db(), kid, bool(request.form.get("newsletter")))
                    flash("Einstellung gespeichert.")
                else:
                    konten.passwort_aendern(db(), kid, request.form.get("alt", ""), request.form.get("neu", ""),
                                            request.form.get("neu2", ""))
                    flash("Passwort geändert.")
            except konten.KontoFehler as e:
                flash(str(e))
            return redirect(url_for("konto"))
        return render_template("konto.html", konto=konten.konto_info(db(), kid),
                               anzahl_snapshots=len(history_store.snapshots_auflisten(db(), besitzer())))

    @app.route("/konto/loeschen", methods=["POST"])
    def konto_loeschen():
        konten_aktiv_oder_404()
        kid = konto_id()
        if kid is None:
            return redirect(url_for("anmelden"))
        if not konten.passwort_pruefen(db(), kid, request.form.get("passwort", "")):
            flash("Passwort falsch – Konto wurde nicht gelöscht.")
            return redirect(url_for("konto"))
        with lock:
            for schluessel in [k for k in ablaeufe if k[0].split("#")[0] == konten.besitzer_id(kid)]:
                ablaeufe.pop(schluessel, None)
        konten.konto_loeschen(db(), kid)
        session.clear()
        flash("Dein Konto und alle zugehörigen Daten wurden gelöscht.")
        return redirect(url_for("start"))

    @app.route("/konto/export")
    def konto_export():
        """Alle eigenen Daten als JSON (Recht auf Datenübertragbarkeit)."""
        nur_mit_konto()
        conn = db()
        info = konten.konto_info(conn, konto_id())
        daten = {"konto": info}
        for pl in Plattform:
            wer = bereich(basis_besitzer(), pl)
            daten[pl.value] = {
                "snapshots": [
                    {"id": sid, "erstellt_am": am, "label": label,
                     "follower": history_store.snapshot_laden(conn, sid, wer).follower,
                     "following": history_store.snapshot_laden(conn, sid, wer).following}
                    for sid, am, label in history_store.snapshots_auflisten(conn, wer)
                ],
                "markierungen": [{"username": u, "markierung": m.value, "gesetzt_am": am}
                                 for u, m, am in history_store.markierungen_mit_datum(conn, wer)],
                "listen": {pl2.value: history_store.liste_laden(conn, wer, pl2) for pl2 in PersonenListe},
                "kommentare": [vars(k) for k in history_store.kommentare_laden(conn, wer)],
                "likes": [vars(l) for l in history_store.likes_laden(conn, wer)],
                "kommentar_entscheidungen": history_store.aktivitaet_entscheidungen_laden(conn, wer, KOMMENTAR),
                "like_entscheidungen": history_store.aktivitaet_entscheidungen_laden(conn, wer, LIKE),
            }
        return Response(json.dumps(daten, ensure_ascii=False, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=meine_daten.json"})

    # ------------------------------------------------------------ Cookies
    @app.route("/cookies", methods=["GET", "POST"])
    def cookies():
        """Cookie-Auswahl speichern (Banner) bzw. jederzeit ändern (Link in der Fußzeile)."""
        if request.method == "POST":
            wahl = request.form.get("wahl", "notwendig")
            session["cookie_wahl"] = "alle" if wahl == "alle" and cookie_modus() == "einwilligung" else "notwendig"
            ziel = request.form.get("zurueck", "")
            return redirect(ziel if ziel.startswith("/") and not ziel.startswith("//") else url_for("start"))
        return render_template("cookies.html", wahl=session.get("cookie_wahl"))

    # ------------------------------------------------------------ Rechtliches
    @app.route("/datenschutz")
    def datenschutz():
        return render_template("datenschutz.html")

    @app.route("/impressum")
    def impressum():
        return render_template("impressum.html")

    return app


app = create_app()


if __name__ == "__main__":
    # debug=False: Der Werkzeug-Debugger erlaubt Codeausführung im Browser und
    # darf niemals öffentlich erreichbar sein.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
