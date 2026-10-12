"""
How-to-Anleitungen für Laien – EIN Text für alle drei Oberflächen.

Web, Desktop und App zeigen genau diese Inhalte an. Wer einen Text ändern
will, ändert ihn nur hier. Menübezeichnungen der Apps können sich je nach
Version leicht unterscheiden – deshalb steht das in den Tipps.
"""

from dataclasses import dataclass, field


@dataclass
class Anleitung:
    id: str
    titel: str
    kurz: str                                   # ein Satz: wofür ist das?
    schritte: list[str]
    tipps: list[str] = field(default_factory=list)
    kategorie: str = "Loslegen"


ANLEITUNGEN: list[Anleitung] = [
    Anleitung(
        id="instagram-export",
        titel="Instagram: Daten herunterladen",
        kurz="So bekommst du die Datei mit deinen Followern, Kommentaren und Likes von Instagram. "
             "Das dauert 2 Minuten, danach schickt dir Instagram eine E-Mail.",
        schritte=[
            "Öffne die Instagram-App und tippe unten rechts auf dein Profilbild.",
            "Tippe oben rechts auf die drei Striche (Menü).",
            "Tippe auf „Kontenübersicht“ (Accounts Center).",
            "Tippe auf „Deine Informationen und Berechtigungen“ und dann auf „Deine Informationen herunterladen“.",
            "Tippe auf „Informationen herunterladen“ bzw. „Herunterladen oder übertragen“ und wähle dein Instagram-Konto.",
            "Wähle „Einige deiner Informationen“. Setze den Haken bei „Follower und gefolgte Personen“. "
            "Für den Kommentar- und Like-Modus zusätzlich „Kommentare“ und „Likes“ (unter „Deine Instagram-Aktivität“).",
            "Wähle „Auf Gerät herunterladen“.",
            "Stelle ein: Zeitraum „Gesamter Zeitraum“, Format „JSON“ (empfohlen; HTML geht auch), Medienqualität egal.",
            "Tippe auf „Dateien anfordern“. Instagram bereitet die Datei vor und schickt dir eine E-Mail.",
            "Öffne die E-Mail, tippe auf den Link und lade die ZIP-Datei herunter. Nicht entpacken!",
        ],
        tipps=[
            "Meist ist die Datei nach wenigen Minuten fertig, manchmal dauert es bis zu einigen Tagen.",
            "Der Download-Link gilt nur ein paar Tage – danach einfach neu anfordern.",
            "Die Namen der Menüpunkte können je nach App-Version leicht anders heißen.",
            "HTML funktioniert auch. JSON ist aber genauer (vor allem bei Datum und Links) und deshalb empfohlen.",
            "Das Programm erkennt selbst, was in der ZIP-Datei steckt: Follower, Kommentare, Likes oder alles zusammen.",
        ],
    ),
    Anleitung(
        id="tiktok-export",
        titel="TikTok: Daten herunterladen",
        kurz="So bekommst du die Datei mit deinen Followern von TikTok.",
        schritte=[
            "Öffne die TikTok-App und tippe unten rechts auf „Profil“.",
            "Tippe oben rechts auf die drei Striche (Menü) und dann auf „Einstellungen und Datenschutz“.",
            "Tippe auf „Konto“ und dann auf „Deine Daten herunterladen“.",
            "Wähle als Format „JSON“ (TXT funktioniert auch) und bei den Daten „Alle auswählen“ oder mindestens die Profil-/Aktivitätsdaten.",
            "Tippe auf „Daten anfordern“.",
            "Wechsle später in den Reiter „Daten herunterladen“. Sobald die Datei fertig ist, tippe auf „Herunterladen“.",
            "Du bekommst eine ZIP-Datei (oder eine JSON-Datei). Diese Datei lädst du hier hoch – das Programm erkennt TikTok automatisch.",
        ],
        tipps=[
            "Die Vorbereitung dauert meist ein paar Stunden, bei großen Konten bis zu einigen Tagen.",
            "Die fertige Datei steht nur begrenzte Zeit zum Download bereit.",
            "Die automatische Prüfung „Scheint deaktiviert“ ist bei TikTok oft gesperrt – dann einfach manuell entscheiden.",
        ],
    ),
    Anleitung(
        id="hochladen",
        titel="Datei laden und auswerten",
        kurz="So kommt deine Datei ins Programm.",
        schritte=[
            "Wähle oben die Plattform (Instagram oder TikTok). Bei ZIP-Dateien erkennt das Programm sie auch selbst.",
            "Tippe auf „Export-Datei wählen“ bzw. „ZIP hochladen“ und wähle die heruntergeladene Datei.",
            "Tippe auf „Laden & auswerten“. Jede Auswertung wird mit Datum gespeichert.",
            "Das Programm zeigt dir, was es gefunden hat (Follower, Kommentare, Likes) und wohin du weiter kannst.",
            "Du siehst nun: wem du folgst, wer dir folgt, und rot markiert, wer dir NICHT zurückfolgt.",
        ],
        tipps=[
            "Die ZIP-Datei nicht entpacken – das Programm liest sie direkt.",
            "Die Datei ist zu groß? Beim Export keine Fotos/Videos auswählen, nur Follower, Kommentare und Likes.",
            "Einzelne Dateien gehen auch: z. B. nur followers_1.json, post_comments_1.html oder liked_posts.json.",
            "Auf dem Handy liegt die Datei meist im Ordner „Downloads“.",
        ],
    ),
    Anleitung(
        id="ergebnis",
        titel="Das Ergebnis verstehen",
        kurz="Was die Zahlen und Farben bedeuten.",
        schritte=[
            "„Ich folge“ = Accounts, denen du folgst. „Folgen mir“ = deine Follower.",
            "Rot = kein gegenseitiges Folgen: Du folgst jemandem, der dir nicht folgt – oder umgekehrt.",
            "„Freunde“ = ihr folgt euch gegenseitig. In der Freunde-Liste kannst du zusätzlich Leute von Hand eintragen.",
            "Mit „Als CSV“ bekommst du die Freunde als Tabelle für Excel.",
        ],
        kategorie="Auswerten",
    ),
    Anleitung(
        id="entfolgen",
        titel="Entfolgen-Modus: Schritt für Schritt aufräumen",
        kurz="Das Programm zeigt dir jeden Account, der dir nicht zurückfolgt – du entscheidest per Knopfdruck.",
        schritte=[
            "Starte den „Entfolgen-Modus“.",
            "Beim zweiten Mal fragt das Programm: Welche schon beurteilten Gruppen sollen erneut abgefragt werden? "
            "Haken setzen = erneut abfragen, kein Haken = überspringen.",
            "Optional: „Automatisch prüfen“. Das Programm testet zuerst, ob eine zuverlässige Prüfung gerade möglich ist, "
            "und schlägt dann Accounts vor, die gelöscht oder deaktiviert wirken.",
            "Die Vorschläge prüfst du kurz (Profil öffnen) und bestätigst sie mit Häkchen. Nichts wird ohne dich übernommen.",
            "Danach pro Account: „Behalten“ (ist ok), „Entfolgen“ oder „Scheint deaktiviert“.",
            "Verklickt? „Zurück“ macht die letzte Entscheidung rückgängig.",
            "Am Ende bekommst du eine Liste zum Abarbeiten. Das Entfolgen selbst machst du in der Instagram- bzw. TikTok-App.",
        ],
        tipps=[
            "Das Programm entfolgt niemandem automatisch – dein Konto bleibt sicher.",
            "Meldet die automatische Prüfung eine Sperre, ist das normal: Instagram/TikTok bremsen solche Abrufe. "
            "Später erneut versuchen oder manuell entscheiden.",
            "Deine Entscheidungen werden gespeichert. Beim nächsten Export musst du nicht von vorne anfangen.",
        ],
        kategorie="Auswerten",
    ),
    Anleitung(
        id="editor",
        titel="Eigene Listen: Editor und TXT-Dateien",
        kurz="Du hast keinen Export? Dann trag die Namen einfach selbst ein oder lade eine Textdatei.",
        schritte=[
            "Öffne den „Listen-Editor“.",
            "Schreibe links alle Follower, rechts alle, denen du folgst – einen Namen pro Zeile. "
            "Du kannst auch Profil-Links oder @namen einfügen.",
            "Optional mit Datum: name;TT.MM.JJJJ (zum Beispiel: anna;14.11.2023).",
            "Oder: „TXT laden“ und eine vorhandene Textdatei wählen (z. B. eine Liste aus einem anderen Programm).",
            "„Als TXT speichern“ sichert deine Listen als Datei, damit du sie später weiterbearbeiten kannst.",
            "Tippe auf „Auswerten & speichern“ – danach funktioniert alles wie mit einem echten Export.",
        ],
        tipps=[
            "Zeilen, die mit # beginnen, sind Kommentare und werden ignoriert.",
            "Doppelte Namen und Großschreibung sind egal – das Programm räumt das auf.",
            "Mit „Aus letzter Auswertung übernehmen“ bearbeitest du einen vorhandenen Stand weiter.",
        ],
        kategorie="Eigene Listen",
    ),
    Anleitung(
        id="listen",
        titel="Meine Listen: Blockiert, Freunde, Markierungen",
        kurz="Führe Listen über Leute, die du blockiert hast oder die dich blockiert haben – und verwalte deine Entscheidungen.",
        schritte=[
            "Öffne „Meine Listen“ und wähle oben die Liste.",
            "Namen eintragen und „Hinzufügen“ tippen. Mehrere Namen mit Komma trennen.",
            "Mehrere auf einmal bearbeiten: Häkchen setzen (oder „Alle“), dann „Entfernen“, „Verschieben“ oder „Kopieren“.",
            "Unter „Markierte Accounts“ änderst du frühere Entscheidungen aus dem Entfolgen-Modus.",
            "„Zurücksetzen“ bedeutet: Der Account wird beim nächsten Mal wieder abgefragt.",
        ],
        tipps=["Blockierte Profile und „Enge Freunde“ aus dem Instagram-Export werden automatisch übernommen."],
        kategorie="Eigene Listen",
    ),
    Anleitung(
        id="kommentare-likes",
        titel="Kommentare & Likes aufräumen",
        kurz="Geh deine alten Kommentare und Likes durch. Heikle Kommentare zeigt das Programm zuerst.",
        schritte=[
            "Lade einen Instagram-Export, in dem „Kommentare“ und/oder „Likes“ ausgewählt waren.",
            "Öffne „Kommentare“ bzw. „Likes“.",
            "Kommentare: Wähle, was du sehen willst – „Nur kritische“, „Kritisch + prüfen“ (empfohlen) oder „Alle“.",
            "Jeder Kommentar bekommt eine Einschätzung: Grün = harmlos, Gelb = ansehen, Rot = Löschen empfohlen. "
            "Darunter steht, warum (z. B. „lang“, „Beleidigung“, „Politik“).",
            "Entscheide pro Eintrag: „Löschen“ oder „Behalten“. „Zurück“ macht die letzte Entscheidung rückgängig.",
            "Likes: Wähle einen Account (z. B. deinen Ex), um nur Likes bei diesem Account durchzugehen – oder alle.",
            "Am Ende bekommst du eine Liste mit Datum und Link. Über den Link findest du den Beitrag schnell.",
            "Gelöscht wird in Instagram: Profil > Menü > „Deine Aktivität“ > „Interaktionen“ > „Kommentare“ bzw. „Likes“. "
            "Dort kannst du auch mehrere auf einmal auswählen und löschen.",
        ],
        tipps=[
            "Das Programm löscht nichts selbst auf Instagram. Dein Konto bleibt sicher.",
            "Die Einschätzung macht ein kleines neuronales Netz, das direkt im Programm läuft (nichts geht ins "
            "Internet). Es lernt aus deinen Entscheidungen: Nach ein paar Mal „Entfernen“/„Behalten“ sortiert es "
            "ähnliche Kommentare so ein, wie du es tun würdest.",
            "Ironie, Insider und Zusammenhang erkennt das Programm nicht. Die Entscheidung triffst immer du.",
            "Fehlt der direkte Link zum Beitrag, führt der Link zum Profil des Accounts. Das Datum hilft beim Suchen.",
            "Schon entschiedene Einträge werden beim nächsten Mal übersprungen – außer du wählst „erneut“.",
        ],
        kategorie="Auswerten",
    ),
    Anleitung(
        id="verlauf",
        titel="Verlauf: Wer ist neu, wer ist weg?",
        kurz="Vergleiche zwei Exporte und sieh, wer dir neu folgt oder entfolgt hat.",
        schritte=[
            "Lade in regelmäßigen Abständen (z. B. monatlich) einen neuen Export.",
            "Öffne „Verlauf“, wähle einen älteren und einen neueren Zeitpunkt, tippe auf „Vergleichen“.",
            "Grün = neu dazugekommen, Rot = weggefallen.",
            "„Möglicherweise blockiert“: Ihr wart gegenseitig verbunden, jetzt sind beide Verbindungen weg. "
            "Mit einem Tipp kommt der Account in die Liste „Hat mich blockiert“.",
        ],
        tipps=["Ein Blockier-Verdacht kann auch bedeuten: Account gelöscht oder Name geändert."],
        kategorie="Auswerten",
    ),
    Anleitung(
        id="probleme",
        titel="Hilfe, es klappt nicht!",
        kurz="Die häufigsten Probleme und ihre Lösung.",
        schritte=[
            "„Keine Daten gefunden“: Im Export fehlen die gewählten Bereiche. Neu anfordern und die Haken bei "
            "„Follower und gefolgte Personen“, „Kommentare“ bzw. „Likes“ setzen.",
            "„Keine Kommentare/Likes“: Diese Bereiche waren beim Export nicht ausgewählt. Neu anfordern.",
            "„Nur EINE Liste“: Du hast eine einzelne Instagram-JSON-Datei gewählt. Lade lieber die ganze ZIP-Datei.",
            "„Datei zu groß“: Beim Export nur „Follower und gefolgte Personen“ auswählen, keine Fotos/Videos.",
            "„Automatische Prüfung nicht möglich“: Die Plattform sperrt gerade. Später erneut versuchen oder manuell entscheiden.",
            "Namen fehlen oder stimmen nicht: Der Export zeigt den Stand zum Zeitpunkt der Anforderung. Einfach einen neuen Export anfordern.",
        ],
        kategorie="Hilfe",
    ),
]


def anleitung(id: str) -> Anleitung | None:
    return next((a for a in ANLEITUNGEN if a.id == id), None)


def kategorien() -> dict[str, list[Anleitung]]:
    """Anleitungen nach Kategorie gruppiert, Reihenfolge wie oben."""
    ergebnis: dict[str, list[Anleitung]] = {}
    for a in ANLEITUNGEN:
        ergebnis.setdefault(a.kategorie, []).append(a)
    return ergebnis
