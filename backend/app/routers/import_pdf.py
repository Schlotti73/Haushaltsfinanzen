"""
Kontoauszug-Import (Phase 7.2).
POST /import/pdf/vorschau  – parst PDF, zeigt Vorschau (dry-run)
POST /import/pdf/commit    – schreibt Buchungen in DB, archiviert das PDF
GET  /import/pdf/auszuege  – archivierte Auszüge eines Kontos
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import logging
import traceback

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

_log = logging.getLogger(__name__)

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Benutzer, Buchung, CsvProfil, Konto, Kontoauszug
from app.schemas import HaushaltsbuchEintragOut
from app.services.csv_import.erkennung import SYNONYME, erkennen
from app.services.csv_import.profile import (
    ProfilFehlt, als_dict, bank_key_bilden, profil_finden,
)
from app.services.einstellungen import betrag_toleranz, tage_toleranz
from app.services.empfaenger_match import match as match_empfaenger
from app.routers.vertraege import ordne_nach_referenz
from app.services.hhb_match import finde_kandidaten
from app.services.import_regel import RegelKatalog
from app.services.pdf_import.dispatcher import ist_pdf, parse_datei

router = APIRouter(prefix="/import/pdf", tags=["import"])

MAX_PDF_MB = 20


# ── Zeitraum-Sperre: CSV ist die Quelle ─────────────────────────────────────
# Deckt ein CSV-Auszug einen Zeitraum ab, darf ein PDF darin keine Buchungen
# mehr anlegen. Zur selben Zahlung liefert die CSV mehr Felder (IBAN,
# Umsatzart, Mandatsreferenz) und ist damit die bessere Quelle; das PDF bleibt
# erwünscht, aber als Archiv mit lesbarer Tabelle und zum Verknüpfen.
#
# Über den import_hash ist das nicht zu erkennen: in ihn geht der bank_key ein
# (bei CSV das Profil, bei PDF der Parser), und der Empfängertext lautet aus
# einem strukturierten Feld anders als aus einer geparsten PDF-Zeile. Zwei
# Hashes derselben Zahlung stimmen deshalb nie überein. Der Zeitraum ist das
# einzige Kriterium, das beide Formate gemeinsam haben.


def _csv_deckung(db: Session, konto_id: int) -> list[dict]:
    """Die Zeiträume, die CSV-Auszüge dieses Kontos abdecken.

    Ein nur abgeleiteter Zeitraum (zeitraum_bestaetigt = False) deckt mit: zu
    eng ist harmlos, denn eine Zeile daneben fällt lediglich auf die weiche
    Dublettenprüfung zurück, so wie vor dieser Sperre. Ihn deswegen zu
    ignorieren würde dagegen den ganzen Altbestand ungedeckt lassen.
    """
    auszuege = (
        db.query(Kontoauszug)
        .filter(
            Kontoauszug.konto_id == konto_id,
            Kontoauszug.format == "csv",
            Kontoauszug.zeitraum_von.isnot(None),
            Kontoauszug.zeitraum_bis.isnot(None),
        )
        .order_by(Kontoauszug.zeitraum_von)
        .all()
    )
    return [{
        "auszug_id": a.id,
        "dateiname": a.dateiname,
        "von": a.zeitraum_von,
        "bis": a.zeitraum_bis,
        "bestaetigt": bool(a.zeitraum_bestaetigt),
    } for a in auszuege]


def _gedeckt_von(datum: str, deckung: list[dict]) -> Optional[dict]:
    """Der CSV-Auszug, der dieses Datum abdeckt – oder None."""
    for d in deckung:
        if d["von"] <= datum <= d["bis"]:
            return d
    return None


def _zeitraum_pruefen(von: Optional[str], bis: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Prüft ein Von/Bis-Paar aus dem Formular und gibt es normalisiert zurück.

    Nur beides zusammen zählt: ein halber Zeitraum würde eine Sperre über einen
    offenen Rand legen. Leer heißt "nicht bestätigt", das ist kein Fehler.
    """
    von = (von or "").strip() or None
    bis = (bis or "").strip() or None
    if not von or not bis:
        return None, None
    for wert in (von, bis):
        try:
            datetime.strptime(wert, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, f"Datum '{wert}' ist nicht im Format JJJJ-MM-TT")
    if von > bis:
        raise HTTPException(400, "Der Zeitraum endet vor seinem Anfang")
    return von, bis


def _format_von(pdf_bytes: bytes) -> str:
    """'pdf' oder 'csv' – am Dateikopf, nicht am Namen.

    `ist_pdf` liest die %PDF-Signatur. Eine falsch benannte Datei soll nicht
    über das Format entscheiden, von dem die Sperre abhängt.
    """
    return "pdf" if ist_pdf(pdf_bytes) else "csv"


def _vorschau_buchungen(db: Session, konto_id: int, pdf_bytes: bytes,
                        profil_id: Optional[int] = None) -> dict:
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Konto nicht gefunden")

    result = parse_datei(pdf_bytes, db, profil_id)
    if not result.buchungen and result.fehler:
        raise HTTPException(422, f"Fehler beim Parsen: {'; '.join(result.fehler)}")

    # Intra-PDF-Hashkollisionen auflösen (z.B. zwei identische Buchungen am gleichen Tag)
    _pdf_hash_zaehler: dict[str, int] = {}
    for pb in result.buchungen:
        n = _pdf_hash_zaehler.get(pb.import_hash, 0)
        _pdf_hash_zaehler[pb.import_hash] = n + 1
        if n > 0:
            pb.import_hash = f"{pb.import_hash}:{n}"

    # Duplikatcheck: hard (import_hash) und weich (Datum+Betrag±1 Tag)
    existierende_hashes = {
        row[0]
        for row in db.query(Buchung.import_hash)
        .filter(Buchung.konto_id == konto_id, Buchung.import_hash.isnot(None))
        .all()
    }

    # Konfigurierbare Toleranzen für den Abgleich gegen vorhandene Buchungen.
    tage = tage_toleranz(db)
    betrag_spanne = betrag_toleranz(db)

    # Alle vorhandenen Buchungen des Kontos im PDF-Zeitraum ± Toleranz in einer Abfrage laden
    if result.buchungen:
        alle_daten = [pb.datum for pb in result.buchungen]
        fenster_von = _tag_offset(min(alle_daten), -tage)
        fenster_bis = _tag_offset(max(alle_daten), +tage)
        db_buchungen_im_fenster: list[Buchung] = (
            db.query(Buchung)
            .filter(
                Buchung.konto_id == konto_id,
                Buchung.datum.between(fenster_von, fenster_bis),
            )
            .order_by(Buchung.datum)
            .all()
        )
    else:
        db_buchungen_im_fenster = []

    def _buchung_dict(b: Buchung) -> dict:
        return {"id": b.id, "datum": b.datum, "betrag": b.betrag,
                "empfaenger": b.empfaenger, "notiz": b.notiz}

    # Hard-Duplikat-Buchungen per Hash vorindizieren
    hash_zu_buchung: dict[str, Buchung] = {
        b.import_hash: b for b in db_buchungen_im_fenster if b.import_hash
    }

    # Von diesem PDF bereits per Hash belegte Buchungen. Zwei identische Zeilen
    # am selben Tag (gleicher Empfänger, gleicher Betrag, nur anderer
    # Verwendungszweck) teilen sich den Hash und werden oben per ":n"-Suffix
    # getrennt. Trifft davon nur eine auf eine vorhandene Buchung, taucht genau
    # diese Buchung sonst auch in der Kandidatenliste der anderen Zeile auf –
    # und ist dort als erster Eintrag sogar die Vorauswahl. Ein Treffer darauf
    # würde den bestehenden Hash überschreiben, statt die noch unverknüpfte
    # Partnerbuchung zu binden: der Abgleich kippt bei jedem Import hin und her
    # und konvergiert nie.
    pdf_hashes = {pb.import_hash for pb in result.buchungen}
    belegte_buchung_ids = {
        b.id for b in db_buchungen_im_fenster if b.import_hash in pdf_hashes
    }

    # Import-Regeln einmal laden und auf jede Zeile anwenden (Phase 16).
    katalog = RegelKatalog(db)

    # Zeitraum-Sperre nur für PDF-Uploads. Eine CSV ist selbst die Quelle und
    # darf sich nicht am eigenen Zeitraum blockieren – ein zweiter Lauf
    # derselben Datei oder ein überlappender Export würde sonst gar nichts mehr
    # importieren. Dort greift weiter der harte Hash-Duplikatcheck.
    deckung = _csv_deckung(db, konto_id) if ist_pdf(pdf_bytes) else []

    vorschau = []
    for pb in result.buchungen:
        ist_duplikat_hart = pb.import_hash in existierende_hashes

        # Weiche Dublettenprüfung, zweistufig:
        #   Verdacht  – Betrag exakt, ±1 Tag. Bewusst fest verdrahtet, denn nur
        #               dieser Treffer ist scharf genug, um die Zeile von der
        #               Vorauswahl auszunehmen.
        #   Ähnlich   – Betrag/Datum innerhalb der eingestellten Toleranz. Rein
        #               informativ, die Zeile bleibt vorausgewählt.
        ist_verdacht = False
        ist_aehnlich = False
        vorhandene_buchung = None   # Einzeltreffer für Hard-Duplikate
        nahe_buchungen = []         # Alle Buchungen im Toleranzfenster für Verdacht/Neu

        if ist_duplikat_hart:
            dup = hash_zu_buchung.get(pb.import_hash) or db.query(Buchung).filter(
                Buchung.import_hash == pb.import_hash
            ).first()
            if dup:
                vorhandene_buchung = _buchung_dict(dup)
        else:
            # Nahfenster: alle Buchungen ± Tagestoleranz um diesen Eintrag
            nahe_buchungen = [
                _buchung_dict(b) for b in db_buchungen_im_fenster
                if _tag_offset(pb.datum, -tage) <= b.datum <= _tag_offset(pb.datum, +tage)
                and b.id not in belegte_buchung_ids
            ]
            ist_verdacht = any(
                b["betrag"] == pb.betrag and
                _tag_offset(pb.datum, -1) <= b["datum"] <= _tag_offset(pb.datum, +1)
                for b in nahe_buchungen
            )
            ist_aehnlich = not ist_verdacht and any(
                _betrag_aehnlich(b["betrag"], pb.betrag, betrag_spanne)
                for b in nahe_buchungen
            )

        # Import-Regeln zuerst: eine gepflegte Regel ist eine explizite Aussage,
        # der Fuzzy-Match darunter nur eine Vermutung. Ohne sie erreicht ein
        # Rohtext wie "Paypal Europe S.A.R.L. … Getranke Nord …" gegen den Namen
        # "PayPal" ohnehin nie die Schwelle von 0.85.
        regel = katalog.wende_an(pb.empfaenger, pb.verwendungszweck, pb.iban_empfaenger)
        emp = None
        if not regel.empfaenger_id:
            emp = match_empfaenger(db, pb.empfaenger, pb.iban_empfaenger)

        empfaenger_id = regel.empfaenger_id or (emp.id if emp else None)
        empfaenger_name = regel.empfaenger_name or (emp.name if emp else None)
        # Kategorie: Stufe 2 (Händler) schlägt Stufe 1 und den Empfänger-Match.
        kategorie_id = regel.kategorie_id or (emp.kategorie_id if emp else None)

        vorschau.append({
            "datum": pb.datum,
            "betrag": pb.betrag,
            "empfaenger": pb.empfaenger,
            "verwendungszweck": pb.verwendungszweck,
            "iban_empfaenger": pb.iban_empfaenger,
            # Nur aus strukturierten Formaten; bei PDF-Auszügen durchweg None.
            "umsatzart": pb.umsatzart,
            "mandatsreferenz": pb.mandatsreferenz,
            "referenz": pb.referenz,
            "import_hash": pb.import_hash,
            "duplikat": ist_duplikat_hart,
            "duplikat_verdacht": ist_verdacht,
            "duplikat_aehnlich": ist_aehnlich,
            # Der CSV-Auszug, der dieses Datum abdeckt (oder None). Allein
            # noch keine Sperre – die entscheidet sich unten daran, ob es auch
            # eine Gegenbuchung gibt.
            "gedeckt_von": _gedeckt_von(pb.datum, deckung),
            # Wird gleich nach dem Treffer-Vorschlag gesetzt.
            "gesperrt": False,
            "vorhandene_buchung": vorhandene_buchung,
            "nahe_buchungen": nahe_buchungen,
            "empfaenger_id": empfaenger_id,
            "empfaenger_name": empfaenger_name,
            "kategorie_id": kategorie_id,
            "notiz": regel.notiz,
            # Sichtbar machen, was die Regeln umgeschrieben haben – sonst ändert
            # der Import still Felder und ein Fehlgriff fällt erst Wochen später
            # in der Statistik auf.
            "regel_hinweis": regel.hinweis(),
            "regel_geschaeft_id": regel.geschaeft_id,
        })

    treffer_vorschlag, treffer_hinweise = _treffer_vorschlag(vorschau)
    sammelauftraege = _sammelauftraege(vorschau, treffer_vorschlag)

    # Gesperrt ist eine Zeile erst, wenn sie gedeckt ist *und* eine
    # Gegenbuchung hat. Ohne Gegenbuchung kann nichts doppelt gezählt werden,
    # und ein abgeschnittener CSV-Export (90-Tage-Grenze der Bank, aktiver
    # Filter beim Export) heilt sich damit von allein: die fehlende Zahlung
    # kommt weiter aus dem PDF herein.
    #
    # Die Zeilen einer erkannten Sammelbuchung zählen als gedeckt mit
    # Gegenbuchung. Keine einzelne trifft den Betrag, zusammen schon – ohne
    # diese Ausnahme käme der Gesamtbetrag ein zweites Mal herein.
    sammel_hashes = {h for g in sammelauftraege for h in g["hashes"]}
    for b in vorschau:
        if b["duplikat"] or not b["gedeckt_von"]:
            continue
        b["gesperrt"] = (b["import_hash"] in treffer_vorschlag
                         or b["import_hash"] in sammel_hashes)

    konto_abstimmung = _konto_abstimmung(
        db, konto_id, vorschau, treffer_vorschlag, sammelauftraege,
        db_buchungen_im_fenster, result.saldo_pruefung,
    )

    return {
        "bank": result.bank,
        "konto_hinweis": result.konto_hinweis,
        "konto_id": konto_id,
        # Am Dateikopf erkannt, nicht am Namen. Die Oberfläche fragt den
        # Auszugszeitraum nur bei CSV ab – nur dort trägt er die Sperre.
        "format": _format_von(pdf_bytes),
        "buchungen": vorschau,
        # Vorgerechnete Zuordnung Dateizeile → vorhandene Buchung. Trägt die
        # Anreicherung des Altbestands: Buchungen, die aus PDF-Auszügen oder von
        # Hand entstanden sind, bekommen über den Treffer IBAN, Umsatzart,
        # Mandatsreferenz und den vollen Verwendungszweck nachgetragen, statt
        # ein zweites Mal importiert zu werden.
        "treffer_vorschlag": treffer_vorschlag,
        "treffer_hinweise": treffer_hinweise,
        "sammelauftraege": sammelauftraege,
        "konto_abstimmung": konto_abstimmung,
        "neu": sum(1 for b in vorschau if not b["duplikat"]),
        "duplikate": sum(1 for b in vorschau if b["duplikat"]),
        # Zeitraum-Sperre: die abdeckenden CSV-Auszüge für den Hinweis über der
        # Liste, dazu die beiden Zahlen. `importierbar` ist, was nach Duplikat
        # und Sperre übrig bleibt – ist es 0, bleibt nur "nur archivieren".
        "csv_deckung": deckung,
        "gedeckt": sum(1 for b in vorschau if b["gedeckt_von"]),
        "gesperrt": sum(1 for b in vorschau if b["gesperrt"]),
        "importierbar": sum(1 for b in vorschau if not b["duplikat"] and not b["gesperrt"]),
        "verdaechtigt": sum(1 for b in vorschau if b["duplikat_verdacht"] and not b["duplikat"]),
        "aehnlich": sum(1 for b in vorschau if b["duplikat_aehnlich"] and not b["duplikat"]),
        # Für die Hervorhebung einzelner Kandidaten in der Vorschau-Liste
        "betrag_toleranz": betrag_spanne,
        "tage_toleranz": tage,
        # Abstimmung der Datei gegen ihre eigenen Kontostände. Leer bei PDFs,
        # die keinen Saldo mitliefern – siehe CsvProfilParser._saldo_pruefen.
        "saldo_pruefung": result.saldo_pruefung,
        "parser_fehler": result.fehler,
    }


def _tag_offset(datum_iso: str, tage: int) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(datum_iso)
    return (d + timedelta(days=tage)).isoformat()


def _tage_abstand(a_iso: str, b_iso: str) -> int:
    from datetime import date
    return abs((date.fromisoformat(a_iso) - date.fromisoformat(b_iso)).days)


def _treffer_vorschlag(vorschau: list[dict]) -> tuple[dict[str, int], dict[str, dict]]:
    """Ordnet Dateizeilen eins zu eins vorhandenen Buchungen zu.

    Nur der Betrag muss exakt stimmen; das Datum darf im Toleranzfenster
    abweichen, denn genau dort sitzen die Fälle, um die es geht – Buchungen, die
    beim Erfassen ein paar Tage neben dem Bankdatum gelandet sind.

    Eins zu eins ist der Kern: eine naive Zuordnung pro Zeile ("nimm den ersten
    passenden Kandidaten") gibt bei zwei gleich hohen Buchungen am selben Tag
    beiden Zeilen dieselbe Buchung. Beim Commit schreibt dann die zweite Zeile
    den Hash der ersten über, und die eigentlich gemeinte Partnerbuchung bleibt
    unverknüpft – bei jedem weiteren Import von Neuem.

    Vergeben wird greedy nach Datumsabstand: der exakte Tag zuerst, danach die
    Nachbartage.

    Zurück kommt neben der Zuordnung ein Hinweis je Zeile, aber nur wo es einen
    gibt – und mit dem Grund, nicht als pauschales "unsicher":

    * `abstand` > 0: die Zuordnung verschiebt das Datum der vorhandenen Buchung
      auf das Bankdatum. Auch ein einziger Tag gehört genannt, denn beide Daten
      sind Buchungstage; sie dürften gar nicht auseinanderliegen.
    * `mehrere`: im gleichen Abstand stand mehr als ein freier Kandidat zur
      Wahl. Welcher genommen wurde, entscheidet dann die Reihenfolge – das ist
      eine Vermutung und keine Aussage.

    Vorgeschlagen werden auch diese Zeilen: nichts zu zeigen hilft niemandem,
    eine Markierung mit Begründung schon.
    """
    paare: list[tuple[int, int, int]] = []   # (Abstand, Zeilenindex, Buchungs-ID)
    for i, b in enumerate(vorschau):
        if b["duplikat"]:
            continue
        for nb in b["nahe_buchungen"]:
            if nb["betrag"] != b["betrag"]:
                continue
            paare.append((_tage_abstand(b["datum"], nb["datum"]), i, nb["id"]))

    nach_zeile: dict[int, list[tuple[int, int, int]]] = {}
    for p in paare:
        nach_zeile.setdefault(p[1], []).append(p)

    # Stabile Reihenfolge: kleinster Abstand, dann Dateireihenfolge, dann ID.
    paare.sort()

    vorschlag: dict[str, int] = {}
    hinweise: dict[str, dict] = {}
    belegte_zeilen: set[int] = set()
    belegte_buchungen: set[int] = set()

    for abstand, i, buchung_id in paare:
        if i in belegte_zeilen or buchung_id in belegte_buchungen:
            continue
        gleichwertig = sum(
            1 for a2, _, b2 in nach_zeile[i]
            if a2 == abstand and b2 not in belegte_buchungen
        )
        hash_ = vorschau[i]["import_hash"]
        vorschlag[hash_] = buchung_id
        if abstand > 0 or gleichwertig > 1:
            hinweise[hash_] = {"abstand": abstand, "mehrere": gleichwertig > 1}
        belegte_zeilen.add(i)
        belegte_buchungen.add(buchung_id)

    return vorschlag, hinweise


def _konto_abstimmung(db: Session, konto_id: int, vorschau: list[dict],
                      vorschlag: dict[str, int], sammelauftraege: list[dict],
                      im_fenster: list[Buchung], saldo_pruefung: dict) -> dict:
    """Rechnet den Kontostand nach dem vorgeschlagenen Import gegen die Bank.

    Die Zuordnung Zeile für Zeile kann richtig aussehen und der Bestand trotzdem
    hinterher falsch sein – eine zusammengefasste Buchung, eine doppelt erfasste
    Zeile, eine Lücke weiter vorne. Der Endsaldo der Datei ist die einzige Zahl
    in dieser Kette, die die Bank selbst gesetzt hat; dagegen muss sich das
    Ergebnis messen lassen.

    Verglichen wird der Plan, nicht die Auswahl im Formular: Treffer ändern den
    Saldo nur, wenn sie eine noch nicht gebuchte Buchung auf "gebucht" setzen;
    Zeilen ohne Treffer und ohne Sammelauftrag kommen als neue Buchung hinzu.
    Bank-Endsaldo leer (etwa bei PDFs) heißt: nicht prüfbar, dann steht hier
    `bank_saldo: null` und kein Urteil.
    """
    if not vorschau:
        return {}
    enddatum = max(b["datum"] for b in vorschau)
    konto = db.get(Konto, konto_id)
    start = (konto.startsaldo or 0.0) if konto else 0.0
    bestand = db.query(func.coalesce(func.sum(Buchung.betrag), 0.0)).filter(
        Buchung.konto_id == konto_id,
        Buchung.datum <= enddatum,
        Buchung.status == "gebucht",
    ).scalar() or 0.0

    status_je_id = {b.id: b.status for b in im_fenster}
    in_gruppe = {h for g in sammelauftraege for h in g["hashes"]}

    zugang = 0.0
    neu = 0
    for b in vorschau:
        if b["duplikat"]:
            continue
        hash_ = b["import_hash"]
        if hash_ in vorschlag:
            # Der Treffer schreibt keinen neuen Betrag, hebt aber eine geplante
            # Buchung auf "gebucht" – und erst dann zählt sie im Saldo.
            if status_je_id.get(vorschlag[hash_]) not in (None, "gebucht"):
                zugang += b["betrag"]
            continue
        if hash_ in in_gruppe:
            continue   # Sammelauftrag: Vorschlag ist, die Zeile zu überspringen
        zugang += b["betrag"]
        neu += 1

    bank = (saldo_pruefung or {}).get("saldo_ende")
    danach = round(start + bestand + zugang, 2)
    return {
        "enddatum": enddatum,
        "stand_jetzt": round(start + bestand, 2),
        "zugang": round(zugang, 2),
        "neue_buchungen": neu,
        "stand_danach": danach,
        "bank_saldo": bank,
        "differenz": None if bank is None else round(danach - bank, 2),
    }


def _sammelauftraege(vorschau: list[dict], vorschlag: dict[str, int]) -> list[dict]:
    """Findet vorhandene Buchungen, die mehrere Dateizeilen zusammenfassen.

    Der Fall kommt in echten Beständen vor: im Konto steht eine Buchung über
    den Gesamtbetrag, während die Bank am selben Tag mehrere Einzelaufträge
    führt. Keine einzelne Zeile passt dann auf den Betrag, also gelten alle als
    neu – und der Import zählt den Gesamtbetrag ein zweites Mal.

    Gesucht wird darum nach einer Teilmenge noch unzugeordneter Zeilen desselben
    Tages, deren Summe eine noch freie Buchung dieses Tages exakt trifft. Die
    Gruppen bleiben klein (höchstens fünf Zeilen), und gerechnet wird in Cent,
    damit die Summe nicht an einem Gleitkomma-Rest scheitert.

    Zugeordnet wird hier nichts: ein Hash gehört zu genau einer Buchung, eine
    Buchung kann nicht drei Zeilen tragen. Entweder bleibt die Sammelbuchung
    und die Zeilen werden übersprungen, oder sie wird gelöscht und die Zeilen
    kommen einzeln herein. Das ist eine Entscheidung und keine Rechnung.
    """
    from itertools import combinations

    belegte_buchungen = set(vorschlag.values())
    offen = [b for b in vorschau
             if not b["duplikat"] and b["import_hash"] not in vorschlag]
    if not offen:
        return []

    def cent(x: float) -> int:
        return int(round(x * 100))

    # Freie Buchungen je Tag, aus den Kandidatenlisten der offenen Zeilen.
    frei: dict[str, dict[int, dict]] = {}
    for b in offen:
        for nb in b["nahe_buchungen"]:
            if nb["id"] in belegte_buchungen or nb["datum"] != b["datum"]:
                continue
            frei.setdefault(b["datum"], {})[nb["id"]] = nb

    gruppen: list[dict] = []
    verbraucht: set[str] = set()
    for tag, buchungen in frei.items():
        zeilen = [b for b in offen if b["datum"] == tag and b["import_hash"] not in verbraucht]
        if len(zeilen) < 2:
            continue
        # Große Gruppen zuerst: wäre schon eine Teilmenge ausreichend, müsste
        # die übrige Zeile 0,00 € lauten – praktisch kommt das nicht vor.
        for buchung in sorted(buchungen.values(), key=lambda x: -abs(x["betrag"])):
            if buchung["id"] in belegte_buchungen:
                continue
            ziel = cent(buchung["betrag"])
            treffer = None
            for groesse in range(min(5, len(zeilen)), 1, -1):
                for kombi in combinations(zeilen, groesse):
                    if sum(cent(z["betrag"]) for z in kombi) == ziel:
                        treffer = kombi
                        break
                if treffer:
                    break
            if not treffer:
                continue
            gruppen.append({
                "buchung": buchung,
                "hashes": [z["import_hash"] for z in treffer],
                "summe": round(sum(z["betrag"] for z in treffer), 2),
            })
            belegte_buchungen.add(buchung["id"])
            verbraucht.update(z["import_hash"] for z in treffer)
            zeilen = [z for z in zeilen if z["import_hash"] not in verbraucht]
            if len(zeilen) < 2:
                break

    return gruppen


def _betrag_aehnlich(a: float, b: float, spanne: float) -> bool:
    """Beträge liegen innerhalb der Toleranz – bei gleichem Vorzeichen.

    Ohne die Vorzeichenprüfung läge eine Ausgabe von -2 € nur 4 € von einer
    Einnahme über +2 € entfernt und würde als Treffer durchgehen.
    """
    if (a < 0) != (b < 0):
        return False
    return abs(a - b) <= spanne


# ── Archiv der importierten Auszüge ─────────────────────────────────────────
# Das PDF selbst ist der Nachweis hinter jeder importierten Zeile. Es wird
# ausschließlich beim Commit abgelegt (die Vorschau bleibt folgenlos), dann
# aber immer – auch wenn der Lauf nur Duplikate enthielt, denn ein vollständig
# doppelter Auszug ist trotzdem Archivmaterial.

def _auszug_ablegen(
    db: Session, konto_id: int, pdf_bytes: bytes, daten: dict, dateiname: str | None, user,
    zeitraum_von: Optional[str] = None, zeitraum_bis: Optional[str] = None,
) -> tuple[Kontoauszug, Optional[Path]]:
    """Legt das PDF ab und liefert den Archiv-Eintrag samt neu geschriebener
    Datei (None, wenn ein vorhandener Eintrag wiederverwendet wurde – der
    Aufrufer darf dessen Datei bei einem Rollback nicht löschen).

    Derselbe Upload zum zweiten Mal (z.B. der Auffrisch-Lauf) verwendet den
    vorhandenen Eintrag wieder: gleiche Bytes, gleicher Hash, keine zweite
    Datei auf der Platte und kein zweiter scheinbar fremder Auszug in der
    Liste. Der Zeitstempel des Erstimports bleibt dabei stehen.

    `zeitraum_von`/`bis` sind der im Dialog bestätigte Auszugszeitraum. Ohne
    sie wird er aus min/max der Buchungsdaten abgeleitet und bleibt als
    ungeprüft markiert. Kommen sie bei einem erneuten Upload mit, korrigieren
    sie den vorhandenen Eintrag – sonst gäbe es keinen Weg, einen beim ersten
    Mal falsch bestätigten Zeitraum über den Import zu richten.
    """
    datei_hash = hashlib.sha256(pdf_bytes).hexdigest()
    vorhanden = (
        db.query(Kontoauszug)
        .filter(Kontoauszug.konto_id == konto_id, Kontoauszug.datei_hash == datei_hash)
        .first()
    )
    if vorhanden:
        if not vorhanden.format:
            vorhanden.format = _format_von(pdf_bytes)
        if zeitraum_von and zeitraum_bis:
            vorhanden.zeitraum_von = zeitraum_von
            vorhanden.zeitraum_bis = zeitraum_bis
            vorhanden.zeitraum_bestaetigt = True
        return vorhanden, None

    # Zeitraum aus den geparsten Zeilen ableiten – die Parser lesen keinen
    # Zeitraum aus dem PDF-Kopf (siehe services/pdf_import/base.py).
    alle_daten = sorted(b["datum"] for b in daten["buchungen"])

    unterordner = str(konto_id)
    zielordner = settings.kontoauszuege_dir / unterordner
    zielordner.mkdir(parents=True, exist_ok=True)
    # Endung aus dem Originalnamen, nicht fest ".pdf": seit dem CSV-Import
    # liegen auch Textdateien im Archiv, und ohne richtige Endung liefert der
    # Datei-Endpunkt sie als PDF aus.
    standardname = "kontoauszug.pdf" if ist_pdf(pdf_bytes) else "kontoauszug.csv"
    name = Path(dateiname or standardname).name
    endung = Path(name).suffix.lower() or Path(standardname).suffix
    gespeichert = f"{uuid.uuid4().hex}{endung}"
    (zielordner / gespeichert).write_bytes(pdf_bytes)

    auszug = Kontoauszug(
        konto_id=konto_id,
        dateiname=name,
        dateipfad=f"{unterordner}/{gespeichert}",
        datei_hash=datei_hash,
        bank=daten.get("bank"),
        format=_format_von(pdf_bytes),
        zeitraum_von=zeitraum_von or (alle_daten[0] if alle_daten else None),
        zeitraum_bis=zeitraum_bis or (alle_daten[-1] if alle_daten else None),
        zeitraum_bestaetigt=bool(zeitraum_von and zeitraum_bis),
        anzahl_buchungen=len(daten["buchungen"]),
        importiert_von=user.id,
        importiert_am=datetime.utcnow(),
    )
    db.add(auszug)
    db.flush()
    return auszug, zielordner / gespeichert


def _verwaiste_datei_entfernen(pfad: Optional[Path]) -> None:
    """Räumt die Archivdatei nach einem Rollback weg – der Tabelleneintrag
    dazu existiert dann nicht mehr und die Datei wäre für immer unerreichbar."""
    if pfad is None:
        return
    try:
        pfad.unlink(missing_ok=True)
    except OSError as fehler:  # pragma: no cover - Dateisystem-Eigenheit
        _log.warning("Verwaiste Archivdatei %s nicht entfernbar: %s", pfad, fehler)


def _auszug_holen(db: Session, auszug_id: int) -> Kontoauszug:
    auszug = db.get(Kontoauszug, auszug_id)
    if not auszug:
        raise HTTPException(404, "Kontoauszug nicht gefunden")
    return auszug


@router.get("/auszuege")
def auszuege_liste(
    konto_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Archivierte Auszüge eines Kontos, neueste zuerst."""
    auszuege = (
        db.query(Kontoauszug)
        .filter(Kontoauszug.konto_id == konto_id)
        .order_by(Kontoauszug.importiert_am.desc(), Kontoauszug.id.desc())
        .all()
    )
    namen = {
        b.id: b.name
        for b in db.query(Benutzer).filter(
            Benutzer.id.in_([a.importiert_von for a in auszuege if a.importiert_von])
        ).all()
    } if auszuege else {}
    return [
        {
            "id": a.id,
            "dateiname": a.dateiname,
            "bank": a.bank,
            "format": a.format,
            "zeitraum_von": a.zeitraum_von,
            "zeitraum_bis": a.zeitraum_bis,
            "zeitraum_bestaetigt": bool(a.zeitraum_bestaetigt),
            "anzahl_buchungen": a.anzahl_buchungen,
            "importiert_am": a.importiert_am.isoformat(timespec="seconds"),
            "importiert_von": namen.get(a.importiert_von),
        }
        for a in auszuege
    ]


class AuszugPatch(BaseModel):
    """Nachträgliche Korrektur eines Archiveintrags.

    Nur diese drei Felder: alles andere stammt aus der Datei selbst (Hash,
    Buchungszahl, Bank) und wäre von Hand geändert eine Behauptung über einen
    Inhalt, der daneben unverändert liegt.
    """
    zeitraum_von: Optional[str] = None
    zeitraum_bis: Optional[str] = None
    format: Optional[str] = None


@router.patch("/auszuege/{auszug_id}")
def auszug_aendern(
    auszug_id: int,
    felder: AuszugPatch,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Korrigiert Format und Zeitraum eines archivierten Auszugs.

    Nötig für den Altbestand: dessen Zeiträume sind aus min/max der Buchungen
    abgeleitet und damit zu eng, und das Format wurde bei der Migration aus der
    Dateiendung geraten. Beides trägt die Zeitraum-Sperre, also muss es sich
    richtigstellen lassen, ohne den Auszug zu löschen und neu zu importieren.
    """
    auszug = _auszug_holen(db, auszug_id)

    if felder.format is not None:
        # Leerstring heißt "Format unbekannt" – dann deckt der Auszug nichts ab.
        wert = felder.format.strip().lower() or None
        if wert not in (None, "pdf", "csv"):
            raise HTTPException(400, "Format muss 'pdf', 'csv' oder leer sein")
        auszug.format = wert

    # Beide oder keines: ein halber Zeitraum ist kein Zeitraum, und ein
    # einzelnes geändertes Ende ohne Prüfung gegen den Anfang kann von > bis
    # ergeben.
    if felder.zeitraum_von is not None or felder.zeitraum_bis is not None:
        von, bis = _zeitraum_pruefen(
            felder.zeitraum_von or auszug.zeitraum_von,
            felder.zeitraum_bis or auszug.zeitraum_bis,
        )
        if not (von and bis):
            raise HTTPException(400, "Zeitraum braucht Von und Bis")
        auszug.zeitraum_von = von
        auszug.zeitraum_bis = bis
        auszug.zeitraum_bestaetigt = True

    db.commit()
    db.refresh(auszug)
    return {
        "id": auszug.id,
        "dateiname": auszug.dateiname,
        "format": auszug.format,
        "zeitraum_von": auszug.zeitraum_von,
        "zeitraum_bis": auszug.zeitraum_bis,
        "zeitraum_bestaetigt": bool(auszug.zeitraum_bestaetigt),
    }


@router.get("/auszuege/{auszug_id}/datei")
def auszug_datei(
    auszug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    auszug = _auszug_holen(db, auszug_id)
    pfad = settings.kontoauszuege_dir / auszug.dateipfad
    if not pfad.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    # Bewusst ohne `filename=`: FastAPI setzt damit Content-Disposition
    # "attachment", und der Browser würde statt der Anzeige einen Download
    # starten. Die Anzeige im Frontend läuft über ein <iframe> auf diese URL –
    # CSV-Auszüge zeigt das Frontend als Tabelle über /tabelle, der Typ hier
    # muss aber trotzdem stimmen, sonst versucht der Browser ein PDF zu malen.
    suffix = pfad.suffix.lower()
    if suffix in (".csv", ".txt"):
        # Die Kodierung aus der Datei lesen, nicht raten: ein cp1252-Export als
        # UTF-8 ausgeliefert zeigt in Excel und im Browser zerlegte Umlaute.
        from app.services.csv_import.erkennung import kodierung_erkennen
        kodierung = kodierung_erkennen(pfad.read_bytes()[:65536])
        # Python-Namen sind nicht die der Browser: "cp1252" kennt kein Browser,
        # "windows-1252" jeder. Und "utf-8-sig" ist für HTTP schlicht utf-8,
        # das BOM steht ja in der Datei.
        zeichensatz = {
            "utf-8-sig": "utf-8",
            "cp1252": "windows-1252",
        }.get(kodierung, kodierung)
        basis = "text/csv" if suffix == ".csv" else "text/plain"
        typ = f"{basis}; charset={zeichensatz}"
    else:
        typ = {
            ".pdf": "application/pdf",
            ".xml": "application/xml",
        }.get(suffix, "application/octet-stream")
    return FileResponse(
        str(pfad),
        media_type=typ,
        headers={
            "Content-Disposition":
                f"inline; filename*=UTF-8''{quote(auszug.dateiname)}",
        },
    )


# Obergrenze für die Tabellenansicht. Ein Jahresexport hat gut 400 Zeilen, aber
# die Ansicht ist zum Nachsehen da und nicht zum Auswerten: irgendwo muss eine
# Grenze stehen, damit ein versehentlich archivierter Riesenexport nicht den
# Browser des Betrachters lahmlegt.
TABELLE_MAX_ZEILEN = 3000


@router.get("/auszuege/{auszug_id}/tabelle")
def auszug_tabelle(
    auszug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Einen archivierten CSV-Auszug als Zeilen und Spalten ausliefern.

    Die Anzeige läuft nicht über das <iframe> wie beim PDF: eine CSV käme dort
    als eine Spalte Rohtext an. Zerlegt wird sie hier und nicht im Browser,
    weil Kodierung und Trennzeichen schon für den Import erkannt werden – diese
    Logik ein zweites Mal in JavaScript zu haben, hieße zwei Wahrheiten.

    Die Kopfzeile kommt aus derselben Erkennung wie beim Import, damit die
    Vorlaufzeilen der Bank (Konto, Zeitraum, Anfangssaldo) als solche erkennbar
    bleiben und nicht als erste Datenzeile erscheinen.
    """
    auszug = _auszug_holen(db, auszug_id)
    pfad = settings.kontoauszuege_dir / auszug.dateipfad
    if not pfad.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    if pfad.suffix.lower() not in (".csv", ".txt"):
        raise HTTPException(400, "Nur CSV- und Textdateien lassen sich als Tabelle anzeigen")

    import csv as csv_modul

    from app.services.csv_import.erkennung import (
        kodierung_erkennen, kopfzeile_finden, trennzeichen_erkennen, zeilen_lesen,
    )

    daten = pfad.read_bytes()
    kodierung = kodierung_erkennen(daten)
    zeilen = zeilen_lesen(daten, kodierung)
    if not any(z.strip() for z in zeilen):
        return {"dateiname": auszug.dateiname, "kopf": [], "zeilen": [],
                "vorlauf": [], "nachlauf": [], "zeilen_gesamt": 0, "gekuerzt": False}

    trenner = trennzeichen_erkennen(zeilen)
    tabelle = [z for z in csv_modul.reader(zeilen, delimiter=trenner) if any(f.strip() for f in z)]
    kopf_index = kopfzeile_finden(tabelle)
    kopf = [f.strip() for f in tabelle[kopf_index]]
    breite = len(kopf)

    vorlauf = [[f.strip() for f in z] for z in tabelle[:kopf_index]]
    rest = tabelle[kopf_index + 1:]
    # Alles, was nicht die Breite der Kopfzeile hat, ist Fußzeile der Bank
    # (typisch der Endsaldo) und keine Buchung.
    inhalt = [[f.strip() for f in z] for z in rest if len(z) == breite]
    nachlauf = [[f.strip() for f in z] for z in rest if len(z) != breite]

    return {
        "dateiname": auszug.dateiname,
        "kodierung": kodierung,
        "trennzeichen": trenner,
        "kopf": kopf,
        "vorlauf": vorlauf,
        "zeilen": inhalt[:TABELLE_MAX_ZEILEN],
        "nachlauf": nachlauf,
        "zeilen_gesamt": len(inhalt),
        "gekuerzt": len(inhalt) > TABELLE_MAX_ZEILEN,
    }


@router.delete("/auszuege/{auszug_id}")
def auszug_loeschen(
    auszug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Entfernt nur das Archiv. Die importierten Buchungen sind eigenständige
    Daten und bleiben unberührt; ihre Herkunftsangabe fällt weg."""
    auszug = _auszug_holen(db, auszug_id)
    # Ausdrücklich, nicht per ON DELETE SET NULL: in migrierten Datenbanken ist
    # die Spalte per ALTER TABLE ohne REFERENCES entstanden (siehe
    # alembic/versions/z7b8c9d0e1f2_kontoauszug_archiv.py).
    db.query(Buchung).filter(Buchung.kontoauszug_id == auszug.id).update(
        {Buchung.kontoauszug_id: None}, synchronize_session=False,
    )
    pfad = settings.kontoauszuege_dir / auszug.dateipfad
    if pfad.exists():
        pfad.unlink()
    db.delete(auszug)
    db.commit()
    return {"ok": True}


ERLAUBTE_ENDUNGEN = (".pdf", ".csv", ".txt")


def _profil_fehlt_detail(exc: "ProfilFehlt") -> dict:
    """Nutzlast für die Zuordnungsmaske.

    Die Liste der Zielfelder kommt aus der Erkennung (SYNONYME), ihre
    Beschriftung aus FELD_BESCHRIFTUNG – beides liegt im Backend, damit ein
    neues Feld nicht an zwei Stellen gepflegt werden muss.
    """
    return {
        "profil_fehlt": True,
        "felder": [{"feld": f, "beschriftung": FELD_BESCHRIFTUNG.get(f, f)}
                   for f in SYNONYME],
        **exc.vorschlag,
    }


async def _datei_lesen(datei: UploadFile) -> bytes:
    """Liest den Upload und prüft Endung und Größe.

    Die Endung ist das einzige Kriterium: Browser melden für CSV je nach
    Betriebssystem "text/csv", "application/vnd.ms-excel" oder gar nichts, der
    Content-Type taugt hier also nicht als Schranke.
    """
    name = (datei.filename or "").lower()
    if not name.endswith(ERLAUBTE_ENDUNGEN):
        raise HTTPException(400, "Erlaubt sind PDF- und CSV-Dateien")
    daten = await datei.read()
    if len(daten) > MAX_PDF_MB * 1024 * 1024:
        raise HTTPException(413, f"Datei zu groß (max. {MAX_PDF_MB} MB)")
    return daten


@router.post("/vorschau")
async def vorschau(
    konto_id: int = Form(...),
    datei: UploadFile = File(...),
    profil_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    pdf_bytes = await _datei_lesen(datei)
    try:
        return _vorschau_buchungen(db, konto_id, pdf_bytes, profil_id)
    except ProfilFehlt as exc:
        # Kein Fehlerfall, sondern ein offener Posten: die Datei ist lesbar,
        # nur ihre Spalten sind noch nicht zugeordnet. 409 plus Vorschlag,
        # damit das Frontend die Zuordnungsmaske gefüllt anzeigen kann.
        raise HTTPException(409, detail=_profil_fehlt_detail(exc))


@router.post("/commit")
async def commit(
    konto_id: int = Form(...),
    datei: UploadFile = File(...),
    hashes: Optional[str] = Form(default=None),
    treffer: Optional[str] = Form(default=None),
    auffrischen: bool = Form(default=False),
    profil_id: Optional[int] = Form(default=None),
    zeitraum_von: Optional[str] = Form(default=None),
    zeitraum_bis: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Importiert Buchungen aus der Datei (überspringt Duplikate, gesperrte und
    nicht ausgewählte Zeilen)."""
    pdf_bytes = await _datei_lesen(datei)
    von, bis = _zeitraum_pruefen(zeitraum_von, zeitraum_bis)
    try:
        daten = _vorschau_buchungen(db, konto_id, pdf_bytes, profil_id)
    except ProfilFehlt as exc:
        raise HTTPException(409, detail=_profil_fehlt_detail(exc))

    # Vor dem Schreiben der Buchungen, damit die Archiv-ID für die
    # Herkunftsangabe an jeder Buchung schon vorliegt.
    auszug, neue_auszug_datei = _auszug_ablegen(
        db, konto_id, pdf_bytes, daten, datei.filename, user, von, bis,
    )

    ausgewaehlt: Optional[set] = None
    if hashes:
        try:
            ausgewaehlt = set(json.loads(hashes))
        except Exception:
            raise HTTPException(400, "Ungültiges hashes-Format")

    # Treffer-Zuordnungen: import_hash → existing_buchung_id
    treffer_map: dict[str, int] = {}
    if treffer:
        try:
            treffer_map = json.loads(treffer)
        except Exception:
            raise HTTPException(400, "Ungültiges treffer-Format")

    pdf_hashes = {b["import_hash"] for b in daten["buchungen"]}

    importiert = 0
    neue_buchungen: list[Buchung] = []
    for b in daten["buchungen"]:
        if b["duplikat"]:
            continue
        # Die Sperre wird hier entschieden, nicht nur in der Oberfläche: der
        # Aufrufer schickt eine Hash-Liste, und die darf eine gedeckte Zeile
        # nicht hereinholen können.
        if b["gesperrt"]:
            continue
        if ausgewaehlt is not None and b["import_hash"] not in ausgewaehlt:
            continue
        buch = Buchung(
            konto_id=konto_id,
            datum=b["datum"],
            betrag=b["betrag"],
            # Der definierte Empfängername gewinnt gegen den Bankrohtext; dieser
            # bleibt vollständig in `import_empfaenger` erhalten.
            empfaenger=b.get("empfaenger_name") or b["empfaenger"],
            empfaenger_id=b.get("empfaenger_id"),
            kategorie_id=b.get("kategorie_id"),
            notiz=b.get("notiz"),
            verwendungszweck=b.get("verwendungszweck"),
            import_verwendungszweck=b.get("verwendungszweck"),
            import_empfaenger=b.get("empfaenger"),
            import_iban=b.get("iban_empfaenger"),
            import_umsatzart=b.get("umsatzart"),
            import_mandatsreferenz=b.get("mandatsreferenz"),
            import_referenz=b.get("referenz"),
            import_hash=b["import_hash"],
            kontoauszug_id=auszug.id,
            quelle="import",
            erstellt_von=user.id,
        )
        db.add(buch)
        neue_buchungen.append(buch)
        importiert += 1

    neue_hashes = {b.import_hash for b in neue_buchungen if b.import_hash}

    try:
        db.flush()
    except Exception as exc:
        db.rollback()
        _verwaiste_datei_entfernen(neue_auszug_datei)
        _log.error("Flush fehlgeschlagen: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, f"Datenbankfehler beim Einfügen: {exc}") from exc

    # Treffer-Buchungen patchen: import_hash + Verwendungszweck/Datum vom Kontoauszug übertragen
    verknuepft = 0
    gebucht_gesetzt = 0
    # Buchungen, die in diesem Durchlauf eine Mandatsreferenz bekommen haben
    # oder schon hatten - sie kommen fuer die Vertragszuordnung in Frage.
    angereichert: list[Buchung] = []
    # Wie oft das Bankdatum ein abweichendes Erfassungsdatum ersetzt hat. Beim
    # Anreichern des Altbestands ist das die stillste der Änderungen und
    # deshalb die, die genannt werden muss.
    datum_korrigiert = 0
    if treffer_map:
        pdf_hash_zu_eintrag = {b["import_hash"]: b for b in daten["buchungen"]}
        for pdf_hash, buchung_id in treffer_map.items():
            if pdf_hash in neue_hashes:
                continue  # als neue Buchung importiert, kein Update nötig
            vorhandene = db.get(Buchung, buchung_id)
            if not vorhandene:
                continue
            pdf_b = pdf_hash_zu_eintrag.get(pdf_hash)
            if not pdf_b:
                continue
            # Nie den Hash einer Buchung überschreiben, die schon eine andere
            # Zeile dieses PDFs belegt: sonst verliert die belegte Zeile ihren
            # Hartmatch und die eigentlich gemeinte Partnerbuchung bleibt
            # unverknüpft (siehe Kandidatenfilter in der Vorschau).
            if (vorhandene.import_hash
                    and vorhandene.import_hash != pdf_hash
                    and vorhandene.import_hash in pdf_hashes):
                continue

            vorhandene.import_hash = pdf_hash
            # Auch eine vorher manuell erfasste Buchung ist ab jetzt durch
            # diesen Auszug belegt.
            vorhandene.kontoauszug_id = auszug.id
            if pdf_b.get("verwendungszweck"):
                vorhandene.import_verwendungszweck = pdf_b["verwendungszweck"]
            # Hier wird eine mit dem PDF-Weg entstandene Buchung angereichert:
            # IBAN, Umsatzart und Mandatsreferenz standen in keinem Auszug, die
            # CSV liefert sie mit. Nur setzen, nie leeren – ein Format ohne
            # diese Felder darf vorhandene Angaben nicht wieder abräumen.
            for feld, wert in (("import_iban", pdf_b.get("iban_empfaenger")),
                               ("import_umsatzart", pdf_b.get("umsatzart")),
                               ("import_mandatsreferenz", pdf_b.get("mandatsreferenz")),
                               ("import_referenz", pdf_b.get("referenz")),
                               # Der Bankrohtext des Empfängers. Er ersetzt den
                               # gepflegten Namen in `empfaenger` nicht, hält aber
                               # fest, was auf dem Auszug stand.
                               ("import_empfaenger", pdf_b.get("empfaenger"))):
                if wert:
                    setattr(vorhandene, feld, wert)
            # Kassenzettel-Kaufdatum aus dem Haushaltsbuch bleibt erhalten, sonst
            # zählt das Buchungsdatum laut Kontoauszug.
            if vorhandene.quelle != "haushaltsbuch" and vorhandene.datum != pdf_b["datum"]:
                vorhandene.datum = pdf_b["datum"]
                datum_korrigiert += 1
            # Der Kontoauszug belegt, dass das Geld tatsächlich geflossen ist. Eine
            # noch als "geplant" geführte Buchung (z.B. aus einer wiederkehrenden
            # Vorlage generiert) zählt sonst nicht in den Kontosaldo, obwohl sie
            # real stattgefunden hat.
            if vorhandene.status != "gebucht":
                vorhandene.status = "gebucht"
                gebucht_gesetzt += 1
            angereichert.append(vorhandene)
            verknuepft += 1

    # Hart-Duplikate optional mit den aktuellen PDF-Werten auffrischen
    # (z.B. erneuter Upload eines alten Kontoauszugs zur Korrektur von Altdaten).
    aufgefrischt = 0
    if auffrischen:
        for b in daten["buchungen"]:
            if not b["duplikat"]:
                continue
            vb = b.get("vorhandene_buchung")
            if not vb:
                continue
            bestehende = db.get(Buchung, vb["id"])
            if not bestehende:
                continue
            geaendert = False
            if b.get("verwendungszweck") and bestehende.import_verwendungszweck != b["verwendungszweck"]:
                bestehende.import_verwendungszweck = b["verwendungszweck"]
                geaendert = True
            for feld, wert in (("import_iban", b.get("iban_empfaenger")),
                               ("import_umsatzart", b.get("umsatzart")),
                               ("import_mandatsreferenz", b.get("mandatsreferenz")),
                               ("import_referenz", b.get("referenz")),
                               ("import_empfaenger", b.get("empfaenger"))):
                if wert and getattr(bestehende, feld) != wert:
                    setattr(bestehende, feld, wert)
                    geaendert = True
            if bestehende.quelle != "haushaltsbuch" and bestehende.datum != b["datum"]:
                bestehende.datum = b["datum"]
                datum_korrigiert += 1
                geaendert = True
            # Repariert Altbestand: vor Einführung der Status-Übernahme per Treffer
            # verknüpfte Buchungen blieben fälschlich "geplant".
            if bestehende.status != "gebucht":
                bestehende.status = "gebucht"
                gebucht_gesetzt += 1
                geaendert = True
            # Herkunft nachtragen: beim Auffrischen ist dieser Auszug
            # ausdrücklich der maßgebliche Nachweis für die Zeile.
            if bestehende.kontoauszug_id != auszug.id:
                bestehende.kontoauszug_id = auszug.id
                geaendert = True
            if geaendert:
                aufgefrischt += 1
            angereichert.append(bestehende)

    # Phase 8.5.1: für jede neu importierte Buchung nach offenen HHB-Einträgen
    # suchen, die dazu passen könnten (Betrag/Datum/Empfänger).
    abgleich_vorschlaege = []
    hash_zu_vorschau = {b["import_hash"]: b for b in daten["buchungen"]}
    for buch in neue_buchungen:
        if buch.betrag >= 0:
            continue  # nur Ausgaben können zu einem HHB-Eintrag passen
        vorschau_zeile = hash_zu_vorschau.get(buch.import_hash or "", {})
        kandidaten = finde_kandidaten(
            db, datum=buch.datum, betrag=buch.betrag,
            # Bewusst der Bankrohtext und nicht `buch.empfaenger`: seit die
            # Import-Regeln dort "PayPal" hineinschreiben, stünde der Laden
            # nicht mehr darin und der Namensvergleich in hhb_match liefe leer.
            empfaenger_text=buch.import_empfaenger or buch.empfaenger,
            empfaenger_id=buch.empfaenger_id,
            verwendungszweck=buch.import_verwendungszweck,
            geschaeft_id=vorschau_zeile.get("regel_geschaeft_id"),
        )
        if kandidaten:
            abgleich_vorschlaege.append({
                "buchung_id": buch.id,
                "buchung_empfaenger": buch.empfaenger,
                "buchung_datum": buch.datum,
                "buchung_betrag": buch.betrag,
                "kandidaten": [HaushaltsbuchEintragOut.model_validate(k).model_dump(mode="json") for k in kandidaten],
            })

    # Vertraege nach Mandatsreferenz zuordnen - erst hier, damit auch die per
    # Treffer angereicherten Buchungen ihre gerade nachgetragene Referenz
    # mitbringen. Nur der harte Weg; alles Weichere fragt der Vertragsdialog.
    vertraege_zugeordnet = ordne_nach_referenz(
        db, neue_buchungen + angereichert
    )

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        _verwaiste_datei_entfernen(neue_auszug_datei)
        _log.error("Commit fehlgeschlagen: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, f"Datenbankfehler: {exc}") from exc
    # Gegenprüfung nach dem Schreiben: stimmt der Kontostand jetzt mit dem
    # Endsaldo der Datei? Das ist die einzige Zahl, die nicht aus dieser
    # Anwendung stammt. Weicht sie ab, ist etwas doppelt oder gar nicht
    # gebucht – unabhängig davon, wie plausibel jede einzelne Zeile aussah.
    abstimmung = dict(daten.get("konto_abstimmung") or {})
    if abstimmung.get("enddatum"):
        konto = db.get(Konto, konto_id)
        bestand = db.query(func.coalesce(func.sum(Buchung.betrag), 0.0)).filter(
            Buchung.konto_id == konto_id,
            Buchung.datum <= abstimmung["enddatum"],
            Buchung.status == "gebucht",
        ).scalar() or 0.0
        ist = round((konto.startsaldo or 0.0) + bestand, 2)
        bank = abstimmung.get("bank_saldo")
        abstimmung = {
            "enddatum": abstimmung["enddatum"],
            "stand_danach": ist,
            "bank_saldo": bank,
            "differenz": None if bank is None else round(ist - bank, 2),
        }

    return {
        "kontoauszug_id": auszug.id,
        "kontoauszug_dateiname": auszug.dateiname,
        "konto_abstimmung": abstimmung,
        "importiert": importiert,
        "verknuepft": verknuepft,
        "gebucht_gesetzt": gebucht_gesetzt,
        "aufgefrischt": aufgefrischt,
        "datum_korrigiert": datum_korrigiert,
        "duplikate": daten["duplikate"],
        "abgleich_vorschlaege": abgleich_vorschlaege,
        "vertraege_zugeordnet": vertraege_zugeordnet,
    }


# ── CSV-Profile ─────────────────────────────────────────────────────────────
# Beim PDF ist das Layout der Parser, bei CSV ist es das Profil. Deshalb liegen
# diese Endpunkte hier beim Import und nicht bei den Einstellungen: ein Profil
# entsteht beim ersten Import einer neuen Bank, nicht in einer Verwaltungsmaske.

# Beschriftung der Zielfelder für die Zuordnungsmaske. Die Liste der Felder
# selbst kommt aus der Erkennung (SYNONYME), damit sie nur an einer Stelle
# gepflegt wird.
FELD_BESCHRIFTUNG = {
    "datum": "Buchungsdatum*",
    "betrag": "Betrag",
    "soll": "Soll (Belastung)",
    "haben": "Haben (Gutschrift)",
    "saldo": "Kontostand je Zeile",
    "valuta": "Wertstellung",
    "empfaenger": "Empfänger / Auftraggeber",
    "empfaenger_zusatz": "Abweichender Empfänger",
    "iban": "IBAN der Gegenseite",
    "mandatsreferenz": "Mandatsreferenz",
    "referenz": "Referenz",
    "verwendungszweck": "Verwendungszweck",
    "umsatzart": "Umsatzart",
}


class ProfilEingabe(BaseModel):
    name: str
    struktur: dict = {}
    zuordnung: dict = {}
    kopf_signatur: list = []
    notiz: Optional[str] = None
    aktiv: bool = True


def _profil_pruefen(eingabe: ProfilEingabe) -> None:
    """Ohne Datum und ohne Betrag ist ein Profil nicht benutzbar."""
    z = eingabe.zuordnung or {}
    if not z.get("datum"):
        raise HTTPException(400, "Ohne zugeordnete Datumsspalte lässt sich nichts lesen.")
    if eingabe.struktur.get("betrag_modus") == "soll_haben":
        if not (z.get("soll") or z.get("haben")):
            raise HTTPException(400, "Soll- oder Haben-Spalte zuordnen.")
    elif not z.get("betrag"):
        raise HTTPException(400, "Ohne zugeordnete Betragsspalte lässt sich nichts lesen.")


@router.post("/csv-erkennen")
async def csv_erkennen(
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Analysiert eine CSV und liefert Strukturvorschlag, Probe und Profiltreffer.

    Folgenlos: es wird nichts gespeichert und nichts importiert. Das Frontend
    füllt damit die Zuordnungsmaske.
    """
    daten = await _datei_lesen(datei)
    if ist_pdf(daten):
        raise HTTPException(400, "Das ist ein PDF – dafür braucht es kein CSV-Profil.")
    vorschlag = erkennen(daten)
    if vorschlag.get("fehler"):
        raise HTTPException(422, vorschlag["fehler"])

    profil, quote = profil_finden(db, vorschlag.get("kopf_signatur") or [])
    return {
        **vorschlag,
        "profil": profil,
        "quote": round(quote, 2),
        "felder": [{"feld": f, "beschriftung": FELD_BESCHRIFTUNG.get(f, f)}
                   for f in SYNONYME],
    }


@router.get("/csv-profile")
def csv_profile(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.query(CsvProfil).order_by(CsvProfil.name).all()
    return [als_dict(p) for p in rows]


@router.post("/csv-profile")
def csv_profil_anlegen(
    eingabe: ProfilEingabe,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    _profil_pruefen(eingabe)
    p = CsvProfil(
        name=eingabe.name.strip() or "Unbenannt",
        bank_key=bank_key_bilden(eingabe.name, db),
        struktur=json.dumps(eingabe.struktur, ensure_ascii=False),
        zuordnung=json.dumps(eingabe.zuordnung, ensure_ascii=False),
        kopf_signatur=json.dumps(eingabe.kopf_signatur, ensure_ascii=False),
        notiz=eingabe.notiz,
        aktiv=eingabe.aktiv,
    )
    db.add(p)
    db.commit()
    return als_dict(p)


@router.put("/csv-profile/{profil_id}")
def csv_profil_aendern(
    profil_id: int,
    eingabe: ProfilEingabe,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Ändert ein Profil.

    Der `bank_key` bleibt stehen, auch wenn der Name sich ändert: er geht in
    den Import-Hash ein, und ein neuer Schlüssel würde jede künftige Zeile als
    neu erscheinen lassen.
    """
    p = db.get(CsvProfil, profil_id)
    if not p:
        raise HTTPException(404, "Profil nicht gefunden")
    _profil_pruefen(eingabe)
    p.name = eingabe.name.strip() or p.name
    p.struktur = json.dumps(eingabe.struktur, ensure_ascii=False)
    p.zuordnung = json.dumps(eingabe.zuordnung, ensure_ascii=False)
    p.kopf_signatur = json.dumps(eingabe.kopf_signatur, ensure_ascii=False)
    p.notiz = eingabe.notiz
    p.aktiv = eingabe.aktiv
    db.commit()
    return als_dict(p)


@router.delete("/csv-profile/{profil_id}")
def csv_profil_loeschen(
    profil_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Entfernt nur das Profil. Importierte Buchungen bleiben unberührt – ein
    erneuter Import derselben Bank braucht dann aber wieder eine Zuordnung,
    und mit neuem `bank_key` erkennt er die alten Zeilen nicht als Duplikat."""
    p = db.get(CsvProfil, profil_id)
    if not p:
        raise HTTPException(404, "Profil nicht gefunden")
    db.delete(p)
    db.commit()
    return {"ok": True}
