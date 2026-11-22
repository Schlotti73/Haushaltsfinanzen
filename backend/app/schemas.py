from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ── Hilfsbasis ─────────────────────────────────────────────────────────────
class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Benutzer ────────────────────────────────────────────────────────────────
class BenutzerOut(OrmBase):
    id: int
    name: str
    rolle: str
    aktiv: bool


class BenutzerCreate(BaseModel):
    name: str
    passwort: str
    rolle: str = "bearbeiter"


class BenutzerUpdate(BaseModel):
    name: Optional[str] = None
    passwort: Optional[str] = None
    rolle: Optional[str] = None
    aktiv: Optional[bool] = None


class LoginRequest(BaseModel):
    name: str
    passwort: str
    # Zweiter Faktor: TOTP-Code oder Wiederherstellungscode
    code: Optional[str] = None


# ── Konten ──────────────────────────────────────────────────────────────────
# Muss mit dem CHECK-Constraint ck_konto_typ in models.py übereinstimmen.
KontoTyp = Literal["giro", "spar", "darlehen", "kredit", "depot"]
# Rechenart innerhalb typ='darlehen'. None wird wie "annuitaet" behandelt (Bestandsdaten).
DarlehenArt = Literal["annuitaet", "endfaellig"]


class KontoOut(OrmBase):
    id: int
    name: str
    typ: str
    bank: Optional[str]
    iban: Optional[str]
    bic: Optional[str]
    startsaldo: float
    startdatum: Optional[str]
    aktiv: bool
    sortierung: int
    darlehen_art: Optional[DarlehenArt] = None
    darlehen_betrag: Optional[float] = None
    zinssatz: Optional[float] = None
    effektiver_zinssatz: Optional[float] = None
    tilgungssatz: Optional[float] = None
    rate: Optional[float] = None
    tilgung_start: Optional[str] = None
    vollauszahlung_datum: Optional[str] = None
    zinsbindung_jahre: Optional[int] = None
    laufzeit_monate: Optional[int] = None
    isin: Optional[str] = None
    anteile: Optional[float] = None
    kurs: Optional[float] = None
    kurs_datum: Optional[str] = None


class KontoCreate(BaseModel):
    name: str
    typ: KontoTyp
    bank: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    startsaldo: float = 0
    startdatum: Optional[str] = None
    sortierung: int = 0
    darlehen_art: Optional[DarlehenArt] = None
    darlehen_betrag: Optional[float] = None
    zinssatz: Optional[float] = None
    effektiver_zinssatz: Optional[float] = None
    tilgungssatz: Optional[float] = None
    rate: Optional[float] = None
    tilgung_start: Optional[str] = None
    vollauszahlung_datum: Optional[str] = None
    zinsbindung_jahre: Optional[int] = None
    laufzeit_monate: Optional[int] = None
    # Depot (typ='depot'): manuell gepflegt, siehe Konto-Modell
    isin: Optional[str] = None
    anteile: Optional[float] = None
    kurs: Optional[float] = None
    kurs_datum: Optional[str] = None


class KontoUpdate(BaseModel):
    name: Optional[str] = None
    typ: Optional[KontoTyp] = None
    bank: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    startsaldo: Optional[float] = None
    startdatum: Optional[str] = None
    aktiv: Optional[bool] = None
    sortierung: Optional[int] = None
    darlehen_art: Optional[DarlehenArt] = None
    darlehen_betrag: Optional[float] = None
    zinssatz: Optional[float] = None
    effektiver_zinssatz: Optional[float] = None
    tilgungssatz: Optional[float] = None
    rate: Optional[float] = None
    tilgung_start: Optional[str] = None
    vollauszahlung_datum: Optional[str] = None
    zinsbindung_jahre: Optional[int] = None
    laufzeit_monate: Optional[int] = None
    isin: Optional[str] = None
    anteile: Optional[float] = None
    kurs: Optional[float] = None
    kurs_datum: Optional[str] = None


# ── Sondertilgungen (Darlehenskonto) ─────────────────────────────────────────
class SondertilgungOut(OrmBase):
    id: int
    konto_id: int
    datum: str
    betrag: float
    notiz: Optional[str]


class SondertilgungCreate(BaseModel):
    datum: str
    betrag: float
    notiz: Optional[str] = None


class SondertilgungUpdate(BaseModel):
    datum: Optional[str] = None
    betrag: Optional[float] = None
    notiz: Optional[str] = None


# ── Kategorien ──────────────────────────────────────────────────────────────
class KategorieOut(OrmBase):
    id: int
    name: str
    art: str
    uebergeordnet_id: Optional[int]
    aktiv: bool


class KategorieMitKindern(KategorieOut):
    kinder: List["KategorieMitKindern"] = []


class KategorieFlach(KategorieOut):
    """Flache Liste in Baum-Reihenfolge, fuer Dropdowns.

    ebene: 0 = oberste Ebene (fuer die Einrueckung im Dropdown).
    pfad:  voller Pfad "Nebenkosten / Musterweg 1 / Strom EG". Nur damit
           sind gleichnamige Kategorien in verschiedenen Zweigen
           unterscheidbar und suchbar.
    """

    ebene: int = 0
    pfad: str = ""


class KategorieCreate(BaseModel):
    name: str
    art: str = "ausgabe"
    uebergeordnet_id: Optional[int] = None


class KategorieUpdate(BaseModel):
    name: Optional[str] = None
    art: Optional[str] = None
    uebergeordnet_id: Optional[int] = None
    aktiv: Optional[bool] = None


# ── Projekte ────────────────────────────────────────────────────────────────
class ProjektOut(OrmBase):
    id: int
    name: str
    typ: str
    budget: Optional[float]
    start_datum: Optional[str]
    ende_datum: Optional[str]
    aktiv: bool
    darlehen_konto_id: Optional[int] = None


class ProjektCreate(BaseModel):
    name: str
    typ: str
    budget: Optional[float] = None
    start_datum: Optional[str] = None
    ende_datum: Optional[str] = None
    darlehen_konto_id: Optional[int] = None


class ProjektUpdate(BaseModel):
    name: Optional[str] = None
    typ: Optional[str] = None
    budget: Optional[float] = None
    start_datum: Optional[str] = None
    ende_datum: Optional[str] = None
    aktiv: Optional[bool] = None
    darlehen_konto_id: Optional[int] = None


# ── Geplante Ausgaben (Projekt-Posten) ───────────────────────────────────────
class GeplanteAusgabeOut(OrmBase):
    id: int
    projekt_id: int
    bezeichnung: str
    betrag: float
    notiz: Optional[str]
    kategorie_id: Optional[int]
    sortierung: int
    erledigt: bool
    darlehen_konto_id: Optional[int] = None


class GeplanteAusgabeCreate(BaseModel):
    bezeichnung: str
    betrag: float
    notiz: Optional[str] = None
    kategorie_id: Optional[int] = None
    sortierung: int = 0
    erledigt: bool = False
    darlehen_konto_id: Optional[int] = None


class GeplanteAusgabeUpdate(BaseModel):
    bezeichnung: Optional[str] = None
    betrag: Optional[float] = None
    notiz: Optional[str] = None
    kategorie_id: Optional[int] = None
    sortierung: Optional[int] = None
    erledigt: Optional[bool] = None
    darlehen_konto_id: Optional[int] = None


class BuchungVerknuepfung(BaseModel):
    """Verknüpft/löst Buchungen mit/von einem geplanten Ausgabenposten."""
    buchung_ids: list[int]


# ── Buchungen ───────────────────────────────────────────────────────────────
class BuchungPositionOut(OrmBase):
    id: int
    kategorie_id: Optional[int]
    betrag: float
    notiz: Optional[str]


class BuchungPositionCreate(BaseModel):
    kategorie_id: Optional[int] = None
    betrag: float
    notiz: Optional[str] = None


class BuchungOut(OrmBase):
    id: int
    konto_id: Optional[int]
    datum: str
    betrag: float
    empfaenger: Optional[str]
    empfaenger_id: Optional[int] = None
    kategorie_id: Optional[int]
    projekt_id: Optional[int]
    notiz: Optional[str]
    verwendungszweck: Optional[str] = None
    status: str
    quelle: str
    import_verwendungszweck: Optional[str] = None
    import_empfaenger: Optional[str] = None
    import_iban: Optional[str] = None
    erstellt_am: datetime
    ist_transfer: bool = False
    gegenbuchung_id: Optional[int] = None
    verknuepft_mit_id: Optional[int] = None
    verknuepfung_typ: Optional[str] = None
    geplante_ausgabe_id: Optional[int] = None
    hh_abgleich_status: Optional[str] = None
    positionen: List[BuchungPositionOut] = []


class BuchungCreate(BaseModel):
    konto_id: Optional[int] = None
    datum: str
    betrag: float
    empfaenger: Optional[str] = None
    kategorie_id: Optional[int] = None
    projekt_id: Optional[int] = None
    notiz: Optional[str] = None
    verwendungszweck: Optional[str] = None
    status: str = "gebucht"
    quelle: str = "manuell"
    positionen: List[BuchungPositionCreate] = []


class BuchungUpdate(BaseModel):
    konto_id: Optional[int] = None
    datum: Optional[str] = None
    betrag: Optional[float] = None
    empfaenger: Optional[str] = None
    empfaenger_id: Optional[int] = None
    kategorie_id: Optional[int] = None
    projekt_id: Optional[int] = None
    notiz: Optional[str] = None
    verwendungszweck: Optional[str] = None
    status: Optional[str] = None
    positionen: Optional[List[BuchungPositionCreate]] = None


class BuchungFilter(BaseModel):
    konto_id: Optional[int] = None
    kategorie_id: Optional[int] = None
    # Vorgabe: Unterkategorien zaehlen mit. An einem Knoten mit Kindern haengen
    # meist keine Buchungen direkt, der Filter liefe sonst ins Leere.
    nur_diese_kategorie: bool = False
    projekt_id: Optional[int] = None
    status: Optional[str] = None
    quelle: Optional[str] = None
    datum_von: Optional[str] = None
    datum_bis: Optional[str] = None
    suche: Optional[str] = None
    geplant_ab: Optional[str] = None
    seite: int = 1
    pro_seite: int = 50


class BuchungBulkUpdate(BaseModel):
    """Mehrfachaenderung: entweder ueber ids oder ueber die Filterkriterien.

    Mit alle_gefilterten faehrt der Server ueber dieselben Filter wie die Liste,
    statt eine ID-Liste zu erwarten - sonst muesste das Frontend bei tausenden
    Treffern erst alle Seiten laden, und die Auswahl koennte veralten.
    Gesetzt wird nur, was im Request tatsaechlich vorkommt (model_fields_set),
    damit null ein Feld bewusst leeren kann.
    """

    ids: Optional[List[int]] = None
    alle_gefilterten: bool = False
    filter: Optional[BuchungFilter] = None

    kategorie_id: Optional[int] = None
    empfaenger_id: Optional[int] = None
    empfaenger: Optional[str] = None
    status: Optional[str] = None


class BuchungListOut(BaseModel):
    gesamt: int
    summe: float
    seite: int
    pro_seite: int
    items: List[BuchungOut]


# ── Planung ─────────────────────────────────────────────────────────────────
class PlanungOut(OrmBase):
    id: int
    kategorie_id: int
    jahr: int
    betrag_geplant: float


class PlanungCreate(BaseModel):
    kategorie_id: int
    jahr: int
    betrag_geplant: float


# ── DarlehenRaten ────────────────────────────────────────────────────────────
class DarlehenRateOut(OrmBase):
    id: int
    projekt_id: int
    datum: str
    restschuld: Optional[float]
    tilgung: Optional[float]
    zinsen: Optional[float]
    einzahlung: Optional[float]
    zinssatz: Optional[float]


# ── Empfänger ────────────────────────────────────────────────────────────────
class EmpfaengerOut(OrmBase):
    id: int
    name: str
    iban: Optional[str]
    kategorie_id: Optional[int]
    notiz: Optional[str]


class EmpfaengerCreate(BaseModel):
    name: str
    iban: Optional[str] = None
    kategorie_id: Optional[int] = None
    notiz: Optional[str] = None


class EmpfaengerUpdate(BaseModel):
    name: Optional[str] = None
    iban: Optional[str] = None
    kategorie_id: Optional[int] = None
    notiz: Optional[str] = None


# ── Import-Regeln (Phase 16) ─────────────────────────────────────────────────
class ImportRegelOut(OrmBase):
    id: int
    name: str
    stufe: str
    schluesselwoerter: list[str]
    iban_muster: Optional[str]
    empfaenger_id: Optional[int]
    empfaenger_name: Optional[str] = None
    kategorie_id: Optional[int]
    notiz_text: Optional[str]
    aktiv: bool
    notiz: Optional[str]


class ImportRegelCreate(BaseModel):
    name: str
    stufe: str = "haendler"
    schluesselwoerter: list[str] = []
    iban_muster: Optional[str] = None
    empfaenger_id: Optional[int] = None
    kategorie_id: Optional[int] = None
    notiz_text: Optional[str] = None
    aktiv: bool = True
    notiz: Optional[str] = None


class ImportRegelUpdate(BaseModel):
    name: Optional[str] = None
    stufe: Optional[str] = None
    schluesselwoerter: Optional[list[str]] = None
    iban_muster: Optional[str] = None
    empfaenger_id: Optional[int] = None
    kategorie_id: Optional[int] = None
    notiz_text: Optional[str] = None
    aktiv: Optional[bool] = None
    notiz: Optional[str] = None


class BestandslaufAnfrage(BaseModel):
    """Regeln auf bereits importierte Buchungen anwenden."""
    ueberschreiben: bool = False
    anwenden: bool = False   # False = reine Vorschau


class BestandslaufZeile(BaseModel):
    buchung_id: int
    datum: str
    betrag: float
    bank_empfaenger: Optional[str]
    alt_empfaenger: Optional[str]
    neu_empfaenger: Optional[str]
    alt_kategorie_id: Optional[int]
    neu_kategorie_id: Optional[int]
    alt_notiz: Optional[str]
    neu_notiz: Optional[str]
    alt_empfaenger_id: Optional[int] = None
    neu_empfaenger_id: Optional[int] = None
    regel_hinweis: Optional[str]


class BestandslaufErgebnis(BaseModel):
    geprueft: int
    betroffen: int
    geaendert: int
    zeilen: list[BestandslaufZeile]


class RegelImportErgebnis(BaseModel):
    angelegt: int
    aktualisiert: int
    hinweise: list[str]


# ── Geschäfte (Phase 8, Phase 15) ─────────────────────────────────────────────
class MwstKatEintrag(BaseModel):
    """Eine MwSt-Schlüssel→Kategorie-Zuordnung (A/B/1/2 … → Kategorie-ID)."""
    schluessel: str
    kategorie_id: int


class GeschaeftOut(OrmBase):
    id: int
    name: str
    standard_kategorie_id: Optional[int]
    empfaenger_id: Optional[int]
    aktiv: bool
    # Phase 15: Verknüpftes Kassenzettel-Muster + dessen Artikel-Kategorisierung.
    # Wird beim Serialisieren aus ORM-Objekten (z. B. im Haushaltsbuch-Eintrag)
    # nicht befüllt (Defaults), im Geschäfte-Router aber explizit gesetzt.
    kassenzettel_muster_id: Optional[int] = None
    mwst_kategorie_map: List[MwstKatEintrag] = []


class GeschaeftCreate(BaseModel):
    name: str
    standard_kategorie_id: Optional[int] = None
    empfaenger_id: Optional[int] = None
    mwst_kategorie_map: Optional[List[MwstKatEintrag]] = None


class GeschaeftUpdate(BaseModel):
    name: Optional[str] = None
    standard_kategorie_id: Optional[int] = None
    empfaenger_id: Optional[int] = None
    aktiv: Optional[bool] = None
    mwst_kategorie_map: Optional[List[MwstKatEintrag]] = None


# ── Haushaltsbuch-Einträge (Phase 8) ─────────────────────────────────────────
class HaushaltsbuchPositionOut(OrmBase):
    id: int
    bezeichnung: str
    menge: float
    einzelpreis: Optional[float]
    gesamtpreis: float
    kategorie_id: Optional[int]


class HaushaltsbuchPositionCreate(BaseModel):
    bezeichnung: str
    menge: float = 1
    einzelpreis: Optional[float] = None
    gesamtpreis: float
    kategorie_id: Optional[int] = None
    # Roh-Text der OCR-Erkennung vor evtl. automatischer Korrektur (nur bei
    # aus der Texterkennung stammenden Positionen gesetzt). Wird beim Speichern
    # mit der endgültigen Bezeichnung verglichen, um Korrekturen zu lernen.
    ocr_bezeichnung: Optional[str] = None


class HaushaltsbuchEintragOut(OrmBase):
    id: int
    datum: str
    geschaeft_id: Optional[int]
    geschaeft: Optional[GeschaeftOut] = None
    betrag_gesamt: float
    bezahlart: str
    konto_id: Optional[int]
    buchung_id: int
    abgleich_status: str
    ocr_status: str
    notiz: Optional[str]
    erstellt_am: datetime
    positionen: List[HaushaltsbuchPositionOut] = []


class HaushaltsbuchEintragCreate(BaseModel):
    datum: str
    geschaeft_id: Optional[int] = None
    geschaeft_name: Optional[str] = None
    betrag_gesamt: float
    bezahlart: str = "bar"
    konto_id: Optional[int] = None
    notiz: Optional[str] = None
    positionen: List[HaushaltsbuchPositionCreate] = []

    @field_validator("bezahlart")
    @classmethod
    def _bezahlart_gueltig(cls, v: str) -> str:
        if v not in ("bar", "karte", "konto"):
            raise ValueError("bezahlart muss 'bar', 'karte' oder 'konto' sein")
        return v


class HaushaltsbuchOcrVorschau(BaseModel):
    rohtext: str
    positionen: List[HaushaltsbuchPositionCreate] = []
    konfidenz: Optional[float] = None
    hinweis: Optional[str] = None
    foto_wiederholen_empfohlen: bool = False
    ocr_variante: Optional[str] = None
    ocr_segmentiert: Optional[bool] = None
    ocr_preiszeilen: Optional[int] = None
    hat_vorschau: bool = False
    # Bereits erfasste Artikel-Bezeichnungen desselben Geschäfts, für die
    # Kombobox-Auswahl beim Korrigieren erkannter Artikel.
    bekannte_artikel: List[str] = []


class HaushaltsbuchEintragUpdate(BaseModel):
    datum: Optional[str] = None
    geschaeft_id: Optional[int] = None
    geschaeft_name: Optional[str] = None
    betrag_gesamt: Optional[float] = None
    bezahlart: Optional[str] = None
    konto_id: Optional[int] = None
    notiz: Optional[str] = None
    positionen: Optional[List[HaushaltsbuchPositionCreate]] = None


# ── WiederkehrendeBuchungen ──────────────────────────────────────────────────
class WiederkehrendOut(OrmBase):
    id: int
    konto_id: Optional[int]
    betrag: float
    empfaenger: Optional[str]
    kategorie_id: Optional[int]
    projekt_id: Optional[int]
    rhythmus: str
    start_datum: str
    end_datum: Optional[str]
    aktiv: bool


class WiederkehrendCreate(BaseModel):
    konto_id: Optional[int] = None
    betrag: float
    empfaenger: Optional[str] = None
    kategorie_id: Optional[int] = None
    projekt_id: Optional[int] = None
    rhythmus: str
    start_datum: str
    end_datum: Optional[str] = None


class WiederkehrendUpdate(BaseModel):
    betrag: Optional[float] = None
    empfaenger: Optional[str] = None
    kategorie_id: Optional[int] = None
    projekt_id: Optional[int] = None
    rhythmus: Optional[str] = None
    start_datum: Optional[str] = None
    end_datum: Optional[str] = None
    aktiv: Optional[bool] = None


# ── Gebäude & Verbrauchszahlen ──────────────────────────────────────────────
class GebaeudeBase(BaseModel):
    name: str
    strasse: Optional[str] = None
    plz: Optional[str] = None
    ort: Optional[str] = None
    notiz: Optional[str] = None
    aktiv: bool = True


class GebaeudeCreate(GebaeudeBase):
    pass


class GebaeudeUpdate(BaseModel):
    name: Optional[str] = None
    strasse: Optional[str] = None
    plz: Optional[str] = None
    ort: Optional[str] = None
    notiz: Optional[str] = None
    aktiv: Optional[bool] = None


class GebaeudeOut(OrmBase, GebaeudeBase):
    id: int
    # Nur in der Liste gefuellt: Grundlage fuer die Warnung im Loesch-Dialog.
    zaehler_anzahl: int = 0
    ablesungen_anzahl: int = 0


class ZaehlerBase(BaseModel):
    name: str
    seriennummer: Optional[str] = None
    art: str = "sonstige"
    einheit: str = "kWh"
    richtung: str = "bezug"
    sortierung: int = 0
    aktiv: bool = True
    notiz: Optional[str] = None
    uebergeordneter_zaehler_id: Optional[int] = None
    kategorie_id: Optional[int] = None
    gueltig_ab: Optional[str] = None
    gueltig_bis: Optional[str] = None
    ersetzt_zaehler_id: Optional[int] = None
    # nur bei richtung='einspeisung': Bezugszaehler, mit dem die Kosten verrechnet werden
    gegenzaehler_id: Optional[int] = None


class ZaehlerCreate(ZaehlerBase):
    gebaeude_id: int


class ZaehlerUpdate(BaseModel):
    name: Optional[str] = None
    seriennummer: Optional[str] = None
    art: Optional[str] = None
    einheit: Optional[str] = None
    richtung: Optional[str] = None
    sortierung: Optional[int] = None
    aktiv: Optional[bool] = None
    notiz: Optional[str] = None
    uebergeordneter_zaehler_id: Optional[int] = None
    kategorie_id: Optional[int] = None
    gueltig_ab: Optional[str] = None
    gueltig_bis: Optional[str] = None
    ersetzt_zaehler_id: Optional[int] = None
    gegenzaehler_id: Optional[int] = None


class ZaehlerOut(OrmBase, ZaehlerBase):
    id: int
    gebaeude_id: int


class AblesungCreate(BaseModel):
    zaehler_id: int
    datum: str
    jahr: Optional[int] = None  # aus dem Datum vorbelegt, wenn nicht angegeben
    stand: float
    art: str = "jahr"
    notiz: Optional[str] = None


class AblesungUpdate(BaseModel):
    datum: Optional[str] = None
    jahr: Optional[int] = None
    stand: Optional[float] = None
    art: Optional[str] = None
    notiz: Optional[str] = None


class AblesungOut(OrmBase):
    id: int
    zaehler_id: int
    datum: str
    jahr: int
    stand: float
    art: str
    notiz: Optional[str] = None
    # Das Foto des Zählwerks, wenn eines hängt. Steht hier statt in einer
    # eigenen Abfrage, damit die Tabelle nicht je Zeile einen Aufruf braucht.
    foto_id: Optional[int] = None


class VerbrauchJahr(BaseModel):
    jahr: int
    stand: Optional[float] = None
    verbrauch: Optional[float] = None
    kosten: Optional[float] = None
    preis_je_einheit: Optional[float] = None
    zaehlerwechsel: bool = False


class VerbrauchReihe(BaseModel):
    """Eine Zählerreihe: der Zähler samt seiner Vorgänger als durchgehende Reihe."""

    zaehler_id: int
    name: str
    art: str
    einheit: str
    richtung: str
    kategorie_id: Optional[int] = None
    # Verrechnung Einspeisung <-> Bezug, schon ueber die Zaehlerketten aufgeloest:
    # am Einspeisezaehler die zaehler_id der Bezugsreihe, am Bezugszaehler die
    # Reihen, die in ihn einfliessen. Der Name steht fuers Badge daneben.
    gegenzaehler_id: Optional[int] = None
    verrechnet_mit: List[str] = []
    jahre: List[VerbrauchJahr] = []


class KostenPosten(BaseModel):
    kategorie_id: int
    kategorie: str
    betrag: float


class GebaeudeJahresuebersicht(BaseModel):
    gebaeude_id: int
    jahre: List[int] = []
    reihen: List[VerbrauchReihe] = []
    # Nebenkosten ohne Verbrauchsbezug, je Jahr
    sonstige_kosten: dict[int, List[KostenPosten]] = {}


class Erinnerung(BaseModel):
    """Eine Zeile der Dashboard-Erinnerungen.

    art:    technischer Schluessel, damit das Frontend Zeilen unterscheiden kann
    text:   die Meldung samt Anzahl, fertig formuliert
    zusatz: Begruendung in Kurzform
    ziel:   Route, auf der sich die Sache erledigen laesst
    """

    art: str
    text: str
    zusatz: str = ""
    anzahl: int
    ziel: str


class OffeneAblesungen(BaseModel):
    """Eine Zaehlerkette und die Jahre, fuer die ihr die Jahresablesung fehlt."""

    gebaeude_id: int
    gebaeude: str
    zaehler_id: int
    zaehler: str
    jahre: List[int]


class GebaeudeKostenkategorieOut(OrmBase):
    id: int
    gebaeude_id: int
    kategorie_id: int
    sortierung: int
