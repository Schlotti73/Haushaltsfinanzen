from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship, mapped_column, Mapped

from app.database import Base


class Benutzer(Base):
    __tablename__ = "benutzer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    passwort_hash: Mapped[str] = mapped_column(String, nullable=False)
    rolle: Mapped[str] = mapped_column(String, nullable=False, default="bearbeiter")
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Zweiter Faktor (TOTP). mfa_secret steht erst nach dem Bestaetigen des
    # ersten Codes auf aktiv, damit sich niemand aussperrt.
    mfa_secret: Mapped[Optional[str]] = mapped_column(String)
    mfa_aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Wiederherstellungscodes, bcrypt-gehasht, als JSON-Liste
    mfa_recovery: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (CheckConstraint("rolle IN ('admin', 'bearbeiter')", name="ck_benutzer_rolle"),)


class Konto(Base):
    __tablename__ = "konten"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    typ: Mapped[str] = mapped_column(String, nullable=False)
    bank: Mapped[Optional[str]] = mapped_column(String)
    iban: Mapped[Optional[str]] = mapped_column(String)
    bic: Mapped[Optional[str]] = mapped_column(String)
    startsaldo: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    startdatum: Mapped[Optional[str]] = mapped_column(String)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optimierung Modul "Konten": Annuitäten-Darlehen (typ='darlehen') bzw. Ratenkredit (typ='kredit').
    # Beide rechnen mit derselben Annuität; beim Ratenkredit gibt statt tilgungssatz die
    # laufzeit_monate die Rate vor, zinsbindung_jahre/vollauszahlung_datum bleiben ungenutzt.
    # darlehen_art unterscheidet innerhalb typ='darlehen' die Rechenart: 'annuitaet' (Default,
    # NULL wird als 'annuitaet' gelesen) oder 'endfaellig' (Zwischenfinanzierung: keine Tilgung
    # und keine Rate, nur Zinsen; zinsbindung_jahre trägt die Laufzeit bis zur Ablösung).
    # Bewusst ohne CHECK-Constraint – die Validierung sitzt im Pydantic-Schema, und ein
    # nachträglicher Constraint würde unter SQLite ein Tabellen-Rebuild erzwingen.
    darlehen_art: Mapped[Optional[str]] = mapped_column(String)          # 'annuitaet' | 'endfaellig'
    darlehen_betrag: Mapped[Optional[float]] = mapped_column(Float)      # ursprünglicher Darlehensbetrag
    zinssatz: Mapped[Optional[float]] = mapped_column(Float)            # Sollzins % p.a.
    effektiver_zinssatz: Mapped[Optional[float]] = mapped_column(Float) # Effektivzins % p.a. (laut Bank)
    tilgungssatz: Mapped[Optional[float]] = mapped_column(Float)        # Anfangstilgung % p.a.
    rate: Mapped[Optional[float]] = mapped_column(Float)               # monatliche Annuitätsrate (€)
    tilgung_start: Mapped[Optional[str]] = mapped_column(String)       # Datum erster Rate (YYYY-MM-DD)
    vollauszahlung_datum: Mapped[Optional[str]] = mapped_column(String)  # Referenz für Zinsbindungsbeginn (optional)
    zinsbindung_jahre: Mapped[Optional[int]] = mapped_column(Integer)    # Zinsbindungszeitraum in Jahren (optional)
    laufzeit_monate: Mapped[Optional[int]] = mapped_column(Integer)      # Laufzeit in Monaten (nur bei typ='kredit')
    # Modul "Konten": Wertpapierdepot (typ='depot'), genau ein Wertpapier je Konto.
    # Alle vier Felder werden manuell gepflegt – die App ruft bewusst keine Kurse ab
    # (sie macht sonst nirgends ausgehende Requests). isin trägt keine Logik und dient
    # nur der Dokumentation, welches Papier hier gemeint ist.
    isin: Mapped[Optional[str]] = mapped_column(String)                   # ISIN des Wertpapiers
    anteile: Mapped[Optional[float]] = mapped_column(Float)               # Stückzahl (auch Bruchstücke)
    kurs: Mapped[Optional[float]] = mapped_column(Float)                  # letzter bekannter Kurs (€)
    kurs_datum: Mapped[Optional[str]] = mapped_column(String)             # Stand des Kurses (YYYY-MM-DD)

    buchungen: Mapped[List["Buchung"]] = relationship("Buchung", back_populates="konto")
    sondertilgungen: Mapped[List["Sondertilgung"]] = relationship(
        "Sondertilgung", back_populates="konto", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("typ IN ('giro', 'spar', 'darlehen', 'kredit', 'depot')", name="ck_konto_typ"),)


class Sondertilgung(Base):
    """Optimierung Modul 'Konten': geplante/reale Sondertilgung auf ein Darlehenskonto."""
    __tablename__ = "sondertilgung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    konto_id: Mapped[int] = mapped_column(Integer, ForeignKey("konten.id", ondelete="CASCADE"), nullable=False)
    datum: Mapped[str] = mapped_column(String, nullable=False)
    betrag: Mapped[float] = mapped_column(Float, nullable=False)
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    konto: Mapped["Konto"] = relationship("Konto", back_populates="sondertilgungen")


class Kategorie(Base):
    __tablename__ = "kategorien"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    art: Mapped[str] = mapped_column(String, nullable=False, default="ausgabe")
    uebergeordnet_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    uebergeordnet: Mapped[Optional["Kategorie"]] = relationship("Kategorie", remote_side="Kategorie.id", back_populates="kinder")
    kinder: Mapped[List["Kategorie"]] = relationship("Kategorie", back_populates="uebergeordnet")

    __table_args__ = (
        UniqueConstraint("name", "uebergeordnet_id", name="uq_kategorie_name_parent"),
        CheckConstraint("art IN ('einnahme', 'ausgabe', 'beides')", name="ck_kategorie_art"),
    )


class Projekt(Base):
    __tablename__ = "projekte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    typ: Mapped[str] = mapped_column(String, nullable=False)
    budget: Mapped[Optional[float]] = mapped_column(Float)
    start_datum: Mapped[Optional[str]] = mapped_column(String)
    ende_datum: Mapped[Optional[str]] = mapped_column(String)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Optimierung: verknüpftes Darlehenskonto (Konto mit typ='darlehen')
    darlehen_konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="SET NULL"))

    darlehen_raten: Mapped[List["DarlehenRate"]] = relationship("DarlehenRate", back_populates="projekt", cascade="all, delete-orphan")
    geplante_ausgaben: Mapped[List["GeplanteAusgabe"]] = relationship("GeplanteAusgabe", back_populates="projekt", cascade="all, delete-orphan")
    darlehen_konto: Mapped[Optional["Konto"]] = relationship("Konto", foreign_keys=[darlehen_konto_id])

    __table_args__ = (CheckConstraint("typ IN ('darlehen', 'bauprojekt', 'sonstiges')", name="ck_projekt_typ"),)


class GeplanteAusgabe(Base):
    """Optimierung: einzelne geplante Ausgabe (Posten) innerhalb eines Projekts.
    Wird mit echten Buchungen verknüpft, um Plan vs. Ist je Posten zu ermitteln."""
    __tablename__ = "geplante_ausgabe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projekt_id: Mapped[int] = mapped_column(Integer, ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False)
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    betrag: Mapped[float] = mapped_column(Float, nullable=False)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    erledigt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    darlehen_konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="SET NULL"))

    projekt: Mapped["Projekt"] = relationship("Projekt", back_populates="geplante_ausgaben")
    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")
    darlehen_konto: Mapped[Optional["Konto"]] = relationship("Konto", foreign_keys=[darlehen_konto_id])
    buchungen: Mapped[List["Buchung"]] = relationship("Buchung", back_populates="geplante_ausgabe")


class WiederkehrendeBuchung(Base):
    __tablename__ = "wiederkehrende_buchungen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="SET NULL"))
    betrag: Mapped[float] = mapped_column(Float, nullable=False)
    empfaenger: Mapped[Optional[str]] = mapped_column(String)
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    projekt_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projekte.id", ondelete="SET NULL"))
    rhythmus: Mapped[str] = mapped_column(String, nullable=False)
    start_datum: Mapped[str] = mapped_column(String, nullable=False)
    end_datum: Mapped[Optional[str]] = mapped_column(String)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Ein Vertrag darf mehrere Vorlagen halten (Strom: monatlicher Abschlag und
    # Jahresabrechnung). Ohne FK in migrierten DBs - SQLite kann eine Spalte nur
    # ohne REFERENCES nachrüsten; der Router setzt beim Löschen selbst auf NULL.
    vertrag_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("vertraege.id", ondelete="SET NULL"))

    vertrag: Mapped[Optional["Vertrag"]] = relationship("Vertrag", back_populates="raten")

    __table_args__ = (CheckConstraint("rhythmus IN ('monatlich', 'zweimonatlich', 'quartal', 'jaehrlich')", name="ck_wiederk_rhythmus"),)


class Vertrag(Base):
    """Ein Vertrag oder eine laufende Verpflichtung.

    Stammdaten, Laufzeit und Frist stehen hier; das Geld bleibt bei den
    Buchungen. Was der Vertrag kosten *soll*, hängt als wiederkehrende Buchung
    an ihm (`raten`, 1:n und auch leer erlaubt); was er gekostet *hat*, sind
    die Buchungen mit dieser `vertrag_id`.

    Der Kündigungstermin ist bewusst keine Spalte, sondern wird in
    `routers/vertraege.py` aus `laufzeit_bis`, `kuendigungsfrist` und
    `verlaengerung_monate` gerechnet. Gespeichert wäre er nach jeder stillen
    Verlängerung falsch, ohne dass es auffällt — dieselbe Entscheidung wie beim
    Status "überfällig" einer Buchung und bei den Erinnerungen.

    Zwei Wege führen von einer echten Buchung hierher, und sie sind
    unterschiedlich stark:

      `mandatsreferenz` – pro Vertrag stabil und eindeutig (UNIQUE), nur bei
                          Lastschriften vorhanden. Trifft sie, wird ohne
                          Rückfrage zugeordnet.
      `empfaenger_id`   – das weichere Merkmal für Zahlungsdienstleister. Über
                          PayPal trägt die Mandatsreferenz *PayPal*, nicht den
                          Vertrag; sie darf dort nie gelernt werden. Den
                          Empfänger setzt Stufe `haendler` der `import_regel`
                          schon aus dem Verwendungszweck. Das ist ein Indiz,
                          also wird jedes Mal gefragt.
    """

    __tablename__ = "vertraege"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    anbieter: Mapped[Optional[str]] = mapped_column(String)
    vertragsnummer: Mapped[Optional[str]] = mapped_column(String)
    kundennummer: Mapped[Optional[str]] = mapped_column(String)
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="SET NULL"))
    empfaenger_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("empfaenger.id", ondelete="SET NULL"))
    # Kostenstelle: Versicherung, Steuer und Leasing sind Verträge und bleiben
    # es — das Fahrzeug sagt nur, zu wem sie gehören.
    fahrzeug_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("fahrzeuge.id", ondelete="SET NULL"))
    mandatsreferenz: Mapped[Optional[str]] = mapped_column(String)
    beginn: Mapped[Optional[str]] = mapped_column(String)
    # Leer heißt unbefristet und damit zum Ende der Frist kündbar.
    laufzeit_bis: Mapped[Optional[str]] = mapped_column(String)
    kuendigungsfrist: Mapped[Optional[int]] = mapped_column(Integer)
    kuendigungsfrist_einheit: Mapped[str] = mapped_column(String, nullable=False, default="monate")
    # Leer oder 0: der Vertrag endet mit der Laufzeit, verlängert sich also nicht.
    verlaengerung_monate: Mapped[Optional[int]] = mapped_column(Integer)
    # Gesetzt = gekündigt. `endet_am` ist der letzte Tag, an dem er noch läuft.
    gekuendigt_am: Mapped[Optional[str]] = mapped_column(String)
    endet_am: Mapped[Optional[str]] = mapped_column(String)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    erstellt_von: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")
    konto: Mapped[Optional["Konto"]] = relationship("Konto")
    empfaenger_obj: Mapped[Optional["Empfaenger"]] = relationship("Empfaenger")
    fahrzeug: Mapped[Optional["Fahrzeug"]] = relationship("Fahrzeug", back_populates="vertraege")
    raten: Mapped[List["WiederkehrendeBuchung"]] = relationship(
        "WiederkehrendeBuchung", back_populates="vertrag"
    )
    dokumente: Mapped[List["Beleg"]] = relationship(
        "Beleg", back_populates="vertrag", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "kuendigungsfrist_einheit IN ('tage', 'wochen', 'monate')",
            name="ck_vertrag_fristeinheit",
        ),
    )


class Empfaenger(Base):
    __tablename__ = "empfaenger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    iban: Mapped[Optional[str]] = mapped_column(String)
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")
    buchungen: Mapped[List["Buchung"]] = relationship("Buchung", back_populates="empfaenger_obj", foreign_keys="Buchung.empfaenger_id")
    geschaefte: Mapped[List["Geschaeft"]] = relationship("Geschaeft", back_populates="empfaenger_obj")


class Geschaeft(Base):
    """Phase 8: Stammdaten fuer Haushaltsbuch-Eintraege (Laden, nicht Kontoauszug-Name)."""
    __tablename__ = "geschaeft"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    standard_kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    empfaenger_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("empfaenger.id", ondelete="SET NULL"))
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    standard_kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")
    empfaenger_obj: Mapped[Optional["Empfaenger"]] = relationship("Empfaenger", back_populates="geschaefte")
    eintraege: Mapped[List["HaushaltsbuchEintrag"]] = relationship("HaushaltsbuchEintrag", back_populates="geschaeft")
    # Phase 15: 1:1-Verknüpfung zum OCR-Kassenzettel-Muster (Erkennung + MwSt→Kategorie-Map)
    kassenzettel_muster: Mapped[Optional["KassenzettelMuster"]] = relationship(
        "KassenzettelMuster", back_populates="geschaeft", uselist=False
    )


class HaushaltsbuchEintrag(Base):
    """Phase 8: Beleg-/Artikelebene, getrennt von der Geldebene (Buchung)."""
    __tablename__ = "haushaltsbuch_eintrag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    datum: Mapped[str] = mapped_column(String, nullable=False)
    geschaeft_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("geschaeft.id", ondelete="SET NULL"))
    betrag_gesamt: Mapped[float] = mapped_column(Float, nullable=False)
    bezahlart: Mapped[str] = mapped_column(String, nullable=False)
    konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="SET NULL"))
    buchung_id: Mapped[int] = mapped_column(Integer, ForeignKey("buchungen.id", ondelete="CASCADE"), nullable=False)
    abgleich_status: Mapped[str] = mapped_column(String, nullable=False, default="bar_ohne_konto")
    ocr_status: Mapped[str] = mapped_column(String, nullable=False, default="keine")
    ocr_rohtext: Mapped[Optional[str]] = mapped_column(Text)
    ocr_konfidenz: Mapped[Optional[float]] = mapped_column(Float)
    ocr_hinweis: Mapped[Optional[str]] = mapped_column(Text)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    erstellt_von: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    geschaeft: Mapped[Optional["Geschaeft"]] = relationship("Geschaeft", back_populates="eintraege")
    konto: Mapped[Optional["Konto"]] = relationship("Konto")
    buchung: Mapped["Buchung"] = relationship("Buchung", back_populates="haushaltsbuch_eintrag")
    positionen: Mapped[List["HaushaltsbuchPosition"]] = relationship(
        "HaushaltsbuchPosition", back_populates="eintrag", cascade="all, delete-orphan"
    )
    belege: Mapped[List["Beleg"]] = relationship("Beleg", back_populates="eintrag", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("bezahlart IN ('bar', 'karte', 'konto')", name="ck_hhe_bezahlart"),
        CheckConstraint(
            "abgleich_status IN ('bar_ohne_konto', 'offen', 'verknuepft')", name="ck_hhe_abgleich_status"
        ),
        CheckConstraint("ocr_status IN ('keine', 'roh', 'geparst')", name="ck_hhe_ocr_status"),
    )


class HaushaltsbuchPosition(Base):
    """Phase 8: Artikel je Haushaltsbuch-Eintrag (aus OCR oder Hand erfasst)."""
    __tablename__ = "haushaltsbuch_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eintrag_id: Mapped[int] = mapped_column(Integer, ForeignKey("haushaltsbuch_eintrag.id", ondelete="CASCADE"), nullable=False)
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    menge: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    einzelpreis: Mapped[Optional[float]] = mapped_column(Float)
    gesamtpreis: Mapped[float] = mapped_column(Float, nullable=False)
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))

    eintrag: Mapped["HaushaltsbuchEintrag"] = relationship("HaushaltsbuchEintrag", back_populates="positionen")
    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")


class HaushaltsbuchArtikelKorrektur(Base):
    """Gelernte OCR-Korrektur je Geschäft: merkt sich, dass ein bestimmter
    OCR-Rohtext (z.B. „G&G" bei Edeka) zuletzt zu welcher Bezeichnung korrigiert
    wurde, um denselben wiederkehrenden Lesefehler beim nächsten Kassenzettel
    automatisch vorzuschlagen (siehe [[ocr]])."""
    __tablename__ = "haushaltsbuch_artikel_korrektur"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geschaeft_id: Mapped[int] = mapped_column(Integer, ForeignKey("geschaeft.id", ondelete="CASCADE"), nullable=False)
    ocr_text: Mapped[str] = mapped_column(String, nullable=False)  # normalisiert: getrimmt + klein
    bezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    aktualisiert_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("geschaeft_id", "ocr_text", name="uq_artikel_korrektur_geschaeft_text"),
    )


class Einstellung(Base):
    """Anwendungseinstellungen als Schlüssel/Wert, pro Datenbank.

    Bewusst untypisiert: der Wert wird als Text abgelegt und erst an der
    Aufrufstelle konvertiert (siehe app.services.einstellungen). Backup-
    Einstellungen liegen dagegen weiterhin in config/backup.json, weil sie
    datenbankübergreifend gelten.
    """
    __tablename__ = "einstellung"

    schluessel: Mapped[str] = mapped_column(String, primary_key=True)
    wert: Mapped[str] = mapped_column(Text, nullable=False)


class KontoauszugMuster(Base):
    """PDF-Import-Muster pro Bank (Phase 9). Erkennung + Beispiel + Feld-Mapping."""
    __tablename__ = "kontoauszug_muster"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    bank_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    parser_key: Mapped[Optional[str]] = mapped_column(String)
    erkennung_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    beispiel_pdf_pfad: Mapped[Optional[str]] = mapped_column(String)
    screenshot_pfad: Mapped[Optional[str]] = mapped_column(String)
    feld_markierungen: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class CsvProfil(Base):
    """Bank-Profil für den generischen CSV-Import.

    Gegenstück zu `kontoauszug_muster`, aber mit umgekehrtem Kräfteverhältnis:
    beim PDF ist das Layout der Parser und das Muster nur ein Hinweis, bei CSV
    *ist* dieses Profil der Parser. Entsprechend steht hier alles, was eine
    Bank von der anderen unterscheidet, als Daten – geänderte Spaltennamen
    kostet dann eine Korrektur in der Oberfläche statt eines Releases.

    `struktur`   JSON: kodierung, trennzeichen, kopfzeile, datum_format,
                 dezimal, betrag_modus, saldo_modus und die Saldo-Marken.
    `zuordnung`  JSON: Zielfeld -> Spaltenname (oder Liste von Spaltennamen,
                 für über mehrere Spalten verteilte Verwendungszwecke).
    `kopf_signatur` JSON: die Spaltenzeile der Beispieldatei. Daran erkennt der
                 Import dasselbe Format wieder, ohne dass der Benutzer die Bank
                 angeben muss.
    """

    __tablename__ = "csv_profil"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    bank_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    struktur: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    zuordnung: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    kopf_signatur: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ImportRegel(Base):
    """Normalisiert den Bankrohtext beim Kontoauszug-Import (Phase 16).

    Zwei Stufen, bewusst getrennt, weil Zahlungsdienstleister und Händler in
    einem n:m-Verhältnis stehen (PayPal trägt beliebige Läden, ein Laden bucht
    auch per Lastschrift):

      `anbieter` – erkennt den Zahlungsdienstleister im Bankempfänger bzw. an
                   dessen IBAN und setzt den Empfänger.
      `haendler` – erkennt den eigentlichen Laden in Bankempfänger *und*
                   Verwendungszweck und setzt Notiz + Kategorie; den Empfänger
                   nur, wenn Stufe 1 keinen gefunden hat.

    `schluesselwoerter` ist eine JSON-Liste von Schreibvarianten. Verglichen
    wird auf normalisiertem Text (siehe services/import_regel.py), nicht per
    Regex – die Muster pflegst du in den Einstellungen, ein Tippfehler soll
    dort keine Buchungen stillschweigend umschreiben können.
    """
    __tablename__ = "import_regel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    stufe: Mapped[str] = mapped_column(String, nullable=False, default="haendler")
    schluesselwoerter: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Nur Stufe `anbieter`: feste Gläubiger-IBAN, der stabilste Treffer überhaupt.
    iban_muster: Mapped[Optional[str]] = mapped_column(String)
    empfaenger_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("empfaenger.id", ondelete="SET NULL"))
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    # Leer = `name` wird als Notiz verwendet.
    notiz_text: Mapped[Optional[str]] = mapped_column(String)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    empfaenger_obj: Mapped[Optional["Empfaenger"]] = relationship("Empfaenger")
    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")

    __table_args__ = (
        CheckConstraint("stufe IN ('anbieter', 'haendler')", name="ck_import_regel_stufe"),
    )


class KassenzettelMuster(Base):
    """OCR-Import-Muster pro Geschäft (Phase 10). Erkennung + Parser-Konfiguration.

    Datengetrieben: neue Geschäfte (Aldi, Edeka, Rossmann …) lassen sich über die
    Einstellungen anlegen, ohne Code zu schreiben. `mwst_kategorie_map` bildet den
    MwSt-Schlüssel von der Artikelzeile (A/B/1/2 …) auf eine Kategorie-ID ab."""
    __tablename__ = "kassenzettel_muster"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    geschaeft_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Phase 15: echte Verknüpfung zum Geschäft-Stammdatensatz (statt loser Namens-Kopplung)
    geschaeft_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("geschaeft.id", ondelete="SET NULL"), unique=True
    )
    erkennung_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    start_marker: Mapped[Optional[str]] = mapped_column(String)
    stop_marker: Mapped[Optional[str]] = mapped_column(String)
    skip_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    preis_regex: Mapped[Optional[str]] = mapped_column(String)
    mwst_kategorie_map: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    beispiel_bild_pfad: Mapped[Optional[str]] = mapped_column(String)
    # Freie Bereichsmarkierungen auf dem verarbeiteten Beispielbild (rein dokumentarisch,
    # siehe kontoauszug_muster.feld_markierungen für das Vorbild – hier ohne festes
    # Ziel-Attribut, da Kassenzettel keine feste Einzelfeld-Liste haben).
    feld_markierungen: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    geschaeft: Mapped[Optional["Geschaeft"]] = relationship("Geschaeft", back_populates="kassenzettel_muster")


class Buchung(Base):
    __tablename__ = "buchungen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="CASCADE"))
    datum: Mapped[str] = mapped_column(String, nullable=False)
    betrag: Mapped[float] = mapped_column(Float, nullable=False)
    empfaenger: Mapped[Optional[str]] = mapped_column(String)
    empfaenger_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("empfaenger.id", ondelete="SET NULL"))
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    projekt_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projekte.id", ondelete="SET NULL"))
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="gebucht")
    quelle: Mapped[str] = mapped_column(String, nullable=False, default="manuell")
    wiederkehrend_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("wiederkehrende_buchungen.id", ondelete="SET NULL"))
    # Ursprünglich geplanter Termin der Vorlage (unveränderlich) – getrennt von `datum`,
    # das beim PDF-Abgleich auf das tatsächliche Buchungsdatum der Bank überschrieben
    # werden kann. So bleibt der Dublettencheck in generierung.py stabil, auch wenn
    # sich `datum` nach dem Erzeugen verschiebt.
    wiederkehrend_termin: Mapped[Optional[str]] = mapped_column(String)
    verwendungszweck: Mapped[Optional[str]] = mapped_column(Text)
    import_hash: Mapped[Optional[str]] = mapped_column(String)
    import_verwendungszweck: Mapped[Optional[str]] = mapped_column(Text)
    import_empfaenger: Mapped[Optional[str]] = mapped_column(String)
    import_iban: Mapped[Optional[str]] = mapped_column(String)
    # Nur aus strukturierten Formaten (CSV-Export, später CAMT). Die
    # PDF-Auszüge liefern das nicht, deshalb ist der Altbestand hier leer.
    # `umsatzart` ist der Geschäftsvorfall im Klartext ("SEPA Lastschrift",
    # "Kartenzahlung"), `mandatsreferenz` die pro Vertrag stabile Kennung einer
    # Lastschrift und damit ein härteres Kriterium als jedes Textmuster.
    import_umsatzart: Mapped[Optional[str]] = mapped_column(String)
    import_mandatsreferenz: Mapped[Optional[str]] = mapped_column(String)
    import_referenz: Mapped[Optional[str]] = mapped_column(String)
    erstellt_von: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Phase 7.3: Transfers
    gegenbuchung_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("buchungen.id", ondelete="SET NULL"))
    ist_transfer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Phase 7.1: HH-Verknüpfung
    verknuepft_mit_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("buchungen.id", ondelete="SET NULL"))
    verknuepfung_typ: Mapped[Optional[str]] = mapped_column(String)
    # Optimierung: Verknüpfung mit einem geplanten Ausgabenposten
    geplante_ausgabe_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("geplante_ausgabe.id", ondelete="SET NULL"))
    # Archivierter Kontoauszug, aus dem diese Buchung stammt (oder mit dem sie
    # per Treffer verknüpft wurde). SET NULL: das Archiv zu löschen darf die
    # Buchung selbst nicht antasten.
    kontoauszug_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kontoauszug.id", ondelete="SET NULL"))
    # Vertrag, dessen Kosten diese Buchung ist. Gesetzt vom Generator (die Rate
    # kennt ihren Vertrag), beim Import über die Mandatsreferenz oder von Hand.
    # SET NULL: einen Vertrag zu löschen darf die Zahlungen nicht mitnehmen.
    vertrag_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("vertraege.id", ondelete="SET NULL"))

    konto: Mapped[Optional["Konto"]] = relationship("Konto", back_populates="buchungen")
    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")
    projekt: Mapped[Optional["Projekt"]] = relationship("Projekt")
    geplante_ausgabe: Mapped[Optional["GeplanteAusgabe"]] = relationship("GeplanteAusgabe", back_populates="buchungen")
    empfaenger_obj: Mapped[Optional["Empfaenger"]] = relationship("Empfaenger", back_populates="buchungen", foreign_keys=[empfaenger_id])
    belege: Mapped[List["Beleg"]] = relationship("Beleg", back_populates="buchung", cascade="all, delete-orphan")
    positionen: Mapped[List["BuchungPosition"]] = relationship("BuchungPosition", back_populates="buchung", cascade="all, delete-orphan")
    haushaltsbuch_eintrag: Mapped[Optional["HaushaltsbuchEintrag"]] = relationship(
        "HaushaltsbuchEintrag", back_populates="buchung", uselist=False
    )
    kontoauszug: Mapped[Optional["Kontoauszug"]] = relationship("Kontoauszug", back_populates="buchungen")
    vertrag: Mapped[Optional["Vertrag"]] = relationship("Vertrag", foreign_keys=[vertrag_id])

    @property
    def hh_abgleich_status(self) -> Optional[str]:
        if self.haushaltsbuch_eintrag:
            return self.haushaltsbuch_eintrag.abgleich_status
        return None

    __table_args__ = (
        CheckConstraint("status IN ('geplant', 'gebucht')", name="ck_buchung_status"),
        CheckConstraint("quelle IN ('manuell', 'import', 'haushaltsbuch', 'wiederkehrend')", name="ck_buchung_quelle"),
        UniqueConstraint("konto_id", "import_hash", name="uq_buchung_konto_hash"),
    )


class Kontoauszug(Base):
    """Archivierter Kontoauszug-PDF zu einem Konto.

    Bewusst keine Zeile in `belege`: ein Auszug gehört zu einem Konto und zu
    vielen Buchungen, trägt eigene Felder (Bank, Zeitraum, Datei-Hash) und
    sprengt damit das 1:1-Beleg-Schema mit seinem "genau eines von drei"-Check.
    """

    __tablename__ = "kontoauszug"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    konto_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("konten.id", ondelete="CASCADE"), nullable=False
    )
    dateiname: Mapped[str] = mapped_column(String, nullable=False)
    dateipfad: Mapped[str] = mapped_column(String, nullable=False)
    # SHA256 der PDF-Bytes. Zusammen mit konto_id eindeutig: ein zweiter Upload
    # derselben Datei (z.B. der Auffrisch-Lauf) verwendet den Eintrag wieder,
    # statt Datei und Zeile zu verdoppeln.
    datei_hash: Mapped[str] = mapped_column(String, nullable=False)
    bank: Mapped[Optional[str]] = mapped_column(String)
    # 'pdf' | 'csv' - aus der Dateiendung, nicht aus dem Content-Type (siehe
    # _datei_lesen in routers/import_pdf.py). Leer heisst "unbekannt" und wird
    # wie "nicht CSV" behandelt: ein solcher Auszug deckt keinen Zeitraum ab.
    # Traegt die Zeitraum-Sperre: nur CSV-Auszuege sperren.
    format: Mapped[Optional[str]] = mapped_column(String)
    # Vorbelegt aus min/max Buchungsdatum - die Parser lesen keinen Zeitraum
    # aus dem Dateikopf (siehe services/pdf_import/base.py: ParseResult), auch
    # die CSV-Profile nicht. Der abgeleitete Zeitraum ist damit immer zu eng:
    # faengt der Auszug am 1. an und die erste Buchung am 3., fehlen zwei Tage.
    # Beim CSV-Import wird er deshalb bestaetigt und ist danach nachtraeglich
    # korrigierbar (PATCH /import/pdf/auszuege/{id}).
    zeitraum_von: Mapped[Optional[str]] = mapped_column(String)
    zeitraum_bis: Mapped[Optional[str]] = mapped_column(String)
    # False = der Zeitraum ist nur abgeleitet. Sperren tut er trotzdem (zu eng
    # ist harmlos, nur unscharf), die Liste weist ihn aber als ungeprueft aus.
    zeitraum_bestaetigt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    anzahl_buchungen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importiert_von: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("benutzer.id", ondelete="SET NULL"))
    importiert_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    konto: Mapped[Optional["Konto"]] = relationship("Konto")
    buchungen: Mapped[List["Buchung"]] = relationship("Buchung", back_populates="kontoauszug")

    __table_args__ = (
        UniqueConstraint("konto_id", "datei_hash", name="uq_kontoauszug_konto_hash"),
    )


class Beleg(Base):
    __tablename__ = "belege"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    buchung_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("buchungen.id", ondelete="CASCADE"))
    eintrag_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("haushaltsbuch_eintrag.id", ondelete="CASCADE"))
    gebaeude_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gebaeude.id", ondelete="CASCADE"))
    zaehler_ablesung_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("zaehler_ablesung.id", ondelete="CASCADE")
    )
    vertrag_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("vertraege.id", ondelete="CASCADE"))
    fahrzeug_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"))
    dateiname: Mapped[str] = mapped_column(String, nullable=False)
    dateipfad: Mapped[str] = mapped_column(String, nullable=False)
    hochgeladen_von: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("benutzer.id", ondelete="SET NULL"))
    hochgeladen_am: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    buchung: Mapped[Optional["Buchung"]] = relationship("Buchung", back_populates="belege")
    eintrag: Mapped[Optional["HaushaltsbuchEintrag"]] = relationship("HaushaltsbuchEintrag", back_populates="belege")
    gebaeude: Mapped[Optional["Gebaeude"]] = relationship("Gebaeude", back_populates="fotos")
    ablesung: Mapped[Optional["ZaehlerAblesung"]] = relationship(
        "ZaehlerAblesung", back_populates="fotos"
    )
    vertrag: Mapped[Optional["Vertrag"]] = relationship("Vertrag", back_populates="dokumente")
    fahrzeug: Mapped[Optional["Fahrzeug"]] = relationship("Fahrzeug", back_populates="dokumente")

    __table_args__ = (
        CheckConstraint(
            "(buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL) + (gebaeude_id IS NOT NULL)"
            " + (zaehler_ablesung_id IS NOT NULL) + (vertrag_id IS NOT NULL)"
            " + (fahrzeug_id IS NOT NULL) = 1",
            name="ck_beleg_genau_eines",
        ),
    )


class BuchungPosition(Base):
    __tablename__ = "buchung_positionen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    buchung_id: Mapped[int] = mapped_column(Integer, ForeignKey("buchungen.id", ondelete="CASCADE"), nullable=False)
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    betrag: Mapped[float] = mapped_column(Float, nullable=False)
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    buchung: Mapped["Buchung"] = relationship("Buchung", back_populates="positionen")
    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")


class DarlehenRate(Base):
    __tablename__ = "darlehen_raten"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projekt_id: Mapped[int] = mapped_column(Integer, ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False)
    datum: Mapped[str] = mapped_column(String, nullable=False)
    restschuld: Mapped[Optional[float]] = mapped_column(Float)
    tilgung: Mapped[Optional[float]] = mapped_column(Float)
    zinsen: Mapped[Optional[float]] = mapped_column(Float)
    einzahlung: Mapped[Optional[float]] = mapped_column(Float)
    zinssatz: Mapped[Optional[float]] = mapped_column(Float)

    projekt: Mapped["Projekt"] = relationship("Projekt", back_populates="darlehen_raten")


class Planung(Base):
    __tablename__ = "planung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kategorie_id: Mapped[int] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="CASCADE"), nullable=False)
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    betrag_geplant: Mapped[float] = mapped_column(Float, nullable=False)

    kategorie: Mapped["Kategorie"] = relationship("Kategorie")

    __table_args__ = (UniqueConstraint("kategorie_id", "jahr", name="uq_planung_kat_jahr"),)


# ── Gebäude & Verbrauchszahlen ──────────────────────────────────────────────
class Gebaeude(Base):
    __tablename__ = "gebaeude"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    strasse: Mapped[Optional[str]] = mapped_column(String)
    plz: Mapped[Optional[str]] = mapped_column(String)
    ort: Mapped[Optional[str]] = mapped_column(String)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    zaehler: Mapped[List["Zaehler"]] = relationship(
        "Zaehler", back_populates="gebaeude", cascade="all, delete-orphan"
    )
    kostenkategorien: Mapped[List["GebaeudeKostenkategorie"]] = relationship(
        "GebaeudeKostenkategorie", back_populates="gebaeude", cascade="all, delete-orphan"
    )
    fotos: Mapped[List["Beleg"]] = relationship(
        "Beleg", back_populates="gebaeude", cascade="all, delete-orphan"
    )


class Zaehler(Base):
    """Ein Zähler eines Gebäudes.

    Gespeichert werden Zählerstände (siehe ZaehlerAblesung), der Verbrauch wird
    immer daraus berechnet. So kann ein korrigierter Stand nie zu einem
    widersprüchlichen Verbrauch führen.

    Zählerwechsel: der alte Zähler bekommt gueltig_bis und eine Endstand-
    Ablesung, der neue gueltig_ab, einen Anfangsstand und ersetzt_zaehler_id.
    Tabelle und Diagramm zeigen die Kette als eine durchgehende Reihe.
    """

    __tablename__ = "zaehler"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gebaeude_id: Mapped[int] = mapped_column(Integer, ForeignKey("gebaeude.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    seriennummer: Mapped[Optional[str]] = mapped_column(String)
    art: Mapped[str] = mapped_column(String, nullable=False, default="sonstige")
    einheit: Mapped[str] = mapped_column(String, nullable=False, default="kWh")
    # bezug = Verbrauch, einspeisung = Abgabe ans Netz (PV)
    richtung: Mapped[str] = mapped_column(String, nullable=False, default="bezug")
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    # Zwischenzähler, der in einem anderen Zähler mitgemessen wird (z. B. "Wasser oben")
    uebergeordneter_zaehler_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zaehler.id", ondelete="SET NULL"))
    # Kosten dieses Zählers = Summe der Buchungen dieser Kategorie im Jahr
    kategorie_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="SET NULL"))
    gueltig_ab: Mapped[Optional[str]] = mapped_column(String)
    gueltig_bis: Mapped[Optional[str]] = mapped_column(String)
    ersetzt_zaehler_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zaehler.id", ondelete="SET NULL"))
    # Nur am Einspeisezähler: der Bezugszähler, mit dessen Kosten verrechnet wird.
    # Die PV-Vergütung mindert die Stromkosten, sie ist keine eigene Kostenart.
    # Verrechnet wird nur in Euro - bezogene und eingespeiste kWh sind
    # verschiedene Mengen zu verschiedenen Preisen und bleiben getrennt.
    gegenzaehler_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zaehler.id", ondelete="SET NULL"))

    gebaeude: Mapped["Gebaeude"] = relationship("Gebaeude", back_populates="zaehler")
    kategorie: Mapped[Optional["Kategorie"]] = relationship("Kategorie")
    ablesungen: Mapped[List["ZaehlerAblesung"]] = relationship(
        "ZaehlerAblesung", back_populates="zaehler", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("gebaeude_id", "name", "gueltig_ab", name="uq_zaehler_gebaeude_name_ab"),
        CheckConstraint("art IN ('strom', 'wasser', 'abwasser', 'gas', 'waerme', 'sonstige')", name="ck_zaehler_art"),
        CheckConstraint("richtung IN ('bezug', 'einspeisung')", name="ck_zaehler_richtung"),
    )


class ZaehlerAblesung(Base):
    """Ein abgelesener Zählerstand.

    art='jahr' geht in Jahresverbrauch, Diagramm und Kostenrechnung ein,
    art='zwischen' ist reine Information ohne Auswirkung darauf.
    """

    __tablename__ = "zaehler_ablesung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zaehler_id: Mapped[int] = mapped_column(Integer, ForeignKey("zaehler.id", ondelete="CASCADE"), nullable=False)
    datum: Mapped[str] = mapped_column(String, nullable=False)
    # Abrechnungsjahr, aus dem Datum vorbelegt, aber änderbar (Ablesung am 03.01.)
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    stand: Mapped[float] = mapped_column(Float, nullable=False)
    art: Mapped[str] = mapped_column(String, nullable=False, default="jahr")
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    zaehler: Mapped["Zaehler"] = relationship("Zaehler", back_populates="ablesungen")
    # Genau ein Foto je Ablesung haelt die Oberflaeche ein; als Liste, weil es
    # dieselbe belege-Tabelle ist wie bei Buchung, Eintrag und Gebaeude.
    fotos: Mapped[List["Beleg"]] = relationship(
        "Beleg", back_populates="ablesung", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("zaehler_id", "jahr", "art", name="uq_ablesung_zaehler_jahr_art"),
        CheckConstraint("art IN ('jahr', 'zwischen')", name="ck_ablesung_art"),
    )


class GebaeudeKostenkategorie(Base):
    """Nebenkosten ohne Verbrauchsbezug (Grundsteuer, Versicherung, Müll …).

    Gleicher Mechanismus wie beim Zähler, nur ohne Zähler: die Jahressumme ist
    die Summe der Buchungen dieser Kategorie.
    """

    __tablename__ = "gebaeude_kostenkategorie"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gebaeude_id: Mapped[int] = mapped_column(Integer, ForeignKey("gebaeude.id", ondelete="CASCADE"), nullable=False)
    kategorie_id: Mapped[int] = mapped_column(Integer, ForeignKey("kategorien.id", ondelete="CASCADE"), nullable=False)
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    gebaeude: Mapped["Gebaeude"] = relationship("Gebaeude", back_populates="kostenkategorien")
    kategorie: Mapped["Kategorie"] = relationship("Kategorie")

    __table_args__ = (UniqueConstraint("gebaeude_id", "kategorie_id", name="uq_gebaeude_kategorie"),)


class Fahrzeug(Base):
    """Ein Fahrzeug als Kostenstelle.

    Derselbe Aufbau wie beim Gebäude, nur ohne Zähler-Tabelle: ein Fahrzeug
    hat genau einen Zähler. Gespeichert wird darum der **Kilometerstand**, nie
    die Fahrleistung — die ist immer die Differenz zweier Stände.

    Stände kommen aus zwei Quellen: `tankungen` (an der Zapfsäule) und
    `staende` (zum 31.12. und zwischendurch). Beides zusammen ergibt die
    Fahrleistung; Verbrauch gibt es nur, wo Mengen erfasst sind.

    `tankungen_erfassen` ist der Schalter dafür. Niemand muss an der Säule
    etwas abschreiben: steht er aus, gibt es keine Mengen, keinen Verbrauch
    und keinen Reiter — Kraftstoff ist dann nur eine Kostenart aus den
    Buchungen. Fahrleistung und Kosten je Kilometer bleiben trotzdem, solange
    der Stand einmal im Jahr eingetragen wird.

    Die Kosten selbst bleiben bei den Buchungen; `kostenkategorien` sagt nur,
    welche Kategorien zu diesem Fahrzeug gehören.
    """

    __tablename__ = "fahrzeuge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kennzeichen: Mapped[Optional[str]] = mapped_column(String)
    # 17 Stellen aus dem Fahrzeugschein; Versicherung und Werkstatt fragen danach.
    fahrgestellnummer: Mapped[Optional[str]] = mapped_column(String)
    hersteller_modell: Mapped[Optional[str]] = mapped_column(String)
    # Bestimmt die Einheit der Tankungen: Liter oder kWh, beim Plug-in beides.
    antrieb: Mapped[str] = mapped_column(String, nullable=False, default="benzin")
    erstzulassung: Mapped[Optional[str]] = mapped_column(String)
    konto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("konten.id", ondelete="SET NULL"))
    tankungen_erfassen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    konto: Mapped[Optional["Konto"]] = relationship("Konto")
    staende: Mapped[List["FahrzeugStand"]] = relationship(
        "FahrzeugStand", back_populates="fahrzeug", cascade="all, delete-orphan"
    )
    tankungen: Mapped[List["FahrzeugTankung"]] = relationship(
        "FahrzeugTankung", back_populates="fahrzeug", cascade="all, delete-orphan"
    )
    kostenkategorien: Mapped[List["FahrzeugKostenkategorie"]] = relationship(
        "FahrzeugKostenkategorie", back_populates="fahrzeug", cascade="all, delete-orphan"
    )
    termine: Mapped[List["FahrzeugTermin"]] = relationship(
        "FahrzeugTermin", back_populates="fahrzeug", cascade="all, delete-orphan"
    )
    dokumente: Mapped[List["Beleg"]] = relationship(
        "Beleg", back_populates="fahrzeug", cascade="all, delete-orphan"
    )
    # Versicherung, Steuer, Leasing: Verträge bleiben Verträge und werden dort
    # gepflegt, das Fahrzeug ist nur ihre Kostenstelle. Darum keine Kaskade.
    vertraege: Mapped[List["Vertrag"]] = relationship("Vertrag", back_populates="fahrzeug")

    __table_args__ = (
        CheckConstraint(
            "antrieb IN ('benzin', 'diesel', 'elektro', 'hybrid', 'plugin')",
            name="ck_fahrzeug_antrieb",
        ),
    )


class FahrzeugStand(Base):
    """Ein abgelesener Kilometerstand ohne Tankung.

    `art='jahr'` ist der Stand zum 31.12. und geht in die Jahresfahrleistung
    ein; er ist je Fahrzeug und Jahr eindeutig (partieller Index in der
    Migration). `art='zwischen'` ist reine Information — Werkstattbesuch,
    Übernahme, Verkauf — und darf im Jahr mehrfach vorkommen.
    """

    __tablename__ = "fahrzeug_stand"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fahrzeug_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), nullable=False
    )
    datum: Mapped[str] = mapped_column(String, nullable=False)
    # Abrechnungsjahr, aus dem Datum vorbelegt, aber änderbar (Ablesung am 02.01.)
    jahr: Mapped[int] = mapped_column(Integer, nullable=False)
    km: Mapped[int] = mapped_column(Integer, nullable=False)
    art: Mapped[str] = mapped_column(String, nullable=False, default="jahr")
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    fahrzeug: Mapped["Fahrzeug"] = relationship("Fahrzeug", back_populates="staende")

    __table_args__ = (
        CheckConstraint("art IN ('jahr', 'zwischen')", name="ck_fahrzeug_stand_art"),
    )


class FahrzeugTankung(Base):
    """Eine Tankung oder Ladung: Kilometerstand und Menge.

    Der Verbrauch entsteht nur zwischen zwei **Volltankungen** — nur dann ist
    bekannt, wie viel auf die gefahrenen Kilometer wirklich hineingegangen
    ist. Eine Teilbetankung (`voll=False`) zählt mit, bekommt aber keinen
    eigenen Wert; ihre Menge fließt in die nächste Volltankung ein.

    `betrag` ist freiwillig und `buchung_id` der Normalfall: das Geld steht
    schon im Kontoauszug und wird hier verknüpft, nicht abgeschrieben. Eine
    zweite Buchführung gibt es nicht.
    """

    __tablename__ = "fahrzeug_tankung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fahrzeug_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), nullable=False
    )
    datum: Mapped[str] = mapped_column(String, nullable=False)
    km: Mapped[int] = mapped_column(Integer, nullable=False)
    menge: Mapped[float] = mapped_column(Float, nullable=False)
    einheit: Mapped[str] = mapped_column(String, nullable=False, default="liter")
    voll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    betrag: Mapped[Optional[float]] = mapped_column(Float)
    buchung_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("buchungen.id", ondelete="SET NULL")
    )
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    fahrzeug: Mapped["Fahrzeug"] = relationship("Fahrzeug", back_populates="tankungen")
    buchung: Mapped[Optional["Buchung"]] = relationship("Buchung")

    __table_args__ = (
        CheckConstraint("einheit IN ('liter', 'kwh')", name="ck_fahrzeug_tankung_einheit"),
    )


class FahrzeugKostenkategorie(Base):
    """Welche Kategorien zu diesem Fahrzeug gehören.

    Gleicher Mechanismus wie beim Gebäude: die Jahressumme ist die Summe der
    Buchungen dieser Kategorie. Eine Kategorie darf an genau einer
    Kostenstelle hängen — „Kraftstoff" an zwei Fahrzeugen zählte jede
    Tankstellenbuchung zweimal. Das prüft der Router.
    """

    __tablename__ = "fahrzeug_kostenkategorie"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fahrzeug_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), nullable=False
    )
    kategorie_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kategorien.id", ondelete="CASCADE"), nullable=False
    )
    sortierung: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fahrzeug: Mapped["Fahrzeug"] = relationship("Fahrzeug", back_populates="kostenkategorien")
    kategorie: Mapped["Kategorie"] = relationship("Kategorie")

    __table_args__ = (
        UniqueConstraint("fahrzeug_id", "kategorie_id", name="uq_fahrzeug_kategorie"),
    )


class FahrzeugTermin(Base):
    """HU, Inspektion, Zahnriemen, Reifenwechsel.

    Gespeichert ist nur das **Intervall**; wann der Termin fällig ist, wird in
    `routers/fahrzeuge.py` gerechnet. Ein Datumsintervall ergibt ein Datum,
    ein Kilometer-Intervall erst zusammen mit der Fahrleistung einen
    voraussichtlichen Monat — gespeichert wäre das nach der ersten Fahrt
    veraltet, dieselbe Entscheidung wie beim Kündigungstermin am Vertrag.

    Ohne Intervall gibt es keinen Termin und keine Erinnerung, nur die
    Historie der Durchführungen.
    """

    __tablename__ = "fahrzeug_termin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fahrzeug_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fahrzeuge.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    intervall_monate: Mapped[Optional[int]] = mapped_column(Integer)
    intervall_km: Mapped[Optional[int]] = mapped_column(Integer)
    notiz: Mapped[Optional[str]] = mapped_column(Text)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    fahrzeug: Mapped["Fahrzeug"] = relationship("Fahrzeug", back_populates="termine")
    erledigungen: Mapped[List["FahrzeugTerminErledigung"]] = relationship(
        "FahrzeugTerminErledigung",
        back_populates="termin",
        cascade="all, delete-orphan",
        order_by="FahrzeugTerminErledigung.datum.desc()",
    )


class FahrzeugTerminErledigung(Base):
    """Eine Durchführung: Datum, Kilometerstand, bei Bedarf die Buchung.

    Der Kilometerstand zählt als Stand mit — ein Werkstattbesuch ist eine
    Ablesung. Die Kosten stehen an der verknüpften Buchung; eine Rechnung ohne
    Buchung bleibt ohne Betrag.
    """

    __tablename__ = "fahrzeug_termin_erledigung"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    termin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fahrzeug_termin.id", ondelete="CASCADE"), nullable=False
    )
    datum: Mapped[str] = mapped_column(String, nullable=False)
    km: Mapped[Optional[int]] = mapped_column(Integer)
    buchung_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("buchungen.id", ondelete="SET NULL")
    )
    notiz: Mapped[Optional[str]] = mapped_column(Text)

    termin: Mapped["FahrzeugTermin"] = relationship("FahrzeugTermin", back_populates="erledigungen")
    buchung: Mapped[Optional["Buchung"]] = relationship("Buchung")
