"""
Statistik-Endpunkte für Dashboard/Charts.
Alle Abfragen laufen direkt als SQL über die DB-Connection (kein ORM-Overhead
bei Aggregationen), Ergebnisse werden als plain dicts zurückgegeben.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/statistik", tags=["statistik"])


# ── Jahres-/Monatsübersicht ──────────────────────────────────────────────────

@router.get("/monatsuebersicht")
def monatsuebersicht(
    jahr: Optional[int] = None,
    konto_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Einnahmen, Ausgaben, Saldo je Monat (optional: Jahr-Filter, Konto-Filter)."""
    where = ["b.status IN ('gebucht', 'geplant')", "b.ist_transfer = 0"]
    params: dict = {}
    if jahr:
        where.append("strftime('%Y', b.datum) = :jahr")
        params["jahr"] = str(jahr)
    if konto_id:
        where.append("b.konto_id = :konto_id")
        params["konto_id"] = konto_id

    sql = text(f"""
        SELECT
            strftime('%Y', b.datum)        AS jahr,
            strftime('%m', b.datum)        AS monat,
            ROUND(SUM(CASE WHEN b.betrag > 0 THEN b.betrag ELSE 0 END), 2) AS einnahmen,
            ROUND(SUM(CASE WHEN b.betrag < 0 THEN b.betrag ELSE 0 END), 2) AS ausgaben,
            ROUND(SUM(b.betrag), 2)                                          AS saldo
        FROM buchungen b
        WHERE {' AND '.join(where)}
        GROUP BY jahr, monat
        ORDER BY jahr, monat
    """)
    rows = db.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/jahresuebersicht")
def jahresuebersicht(
    konto_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Einnahmen, Ausgaben, Saldo je Jahr."""
    where = ["b.status IN ('gebucht', 'geplant')", "b.ist_transfer = 0"]
    params: dict = {}
    if konto_id:
        where.append("b.konto_id = :konto_id")
        params["konto_id"] = konto_id

    sql = text(f"""
        SELECT
            strftime('%Y', b.datum)        AS jahr,
            ROUND(SUM(CASE WHEN b.betrag > 0 THEN b.betrag ELSE 0 END), 2) AS einnahmen,
            ROUND(SUM(CASE WHEN b.betrag < 0 THEN b.betrag ELSE 0 END), 2) AS ausgaben,
            ROUND(SUM(b.betrag), 2)                                          AS saldo
        FROM buchungen b
        WHERE {' AND '.join(where)}
        GROUP BY jahr
        ORDER BY jahr
    """)
    rows = db.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


# ── Kategorien-Auswertung ────────────────────────────────────────────────────

@router.get("/kategorien")
def kategorien_auswertung(
    jahr: Optional[int] = None,
    nur_ausgaben: bool = True,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Summe je Kategorie (und Oberkategorie), optional Jahr-Filter.

    Feingranular über erfasste Artikel: Ist ein Haushaltsbuch-Beleg in Artikel
    (`haushaltsbuch_position`) mit eigener Kategorie aufgeteilt, zählen diese
    Artikel-Kategorien statt der einen Buchungskategorie (z.B. Drogerie/
    Haushaltswaren getrennt vom Lebensmittel-Einkauf). Nicht aufgeteilte
    Buchungen bleiben unverändert; ein evtl. nicht durch Artikel gedeckter
    Restbetrag fällt auf die Buchungskategorie zurück – bzw. bei fehlender
    Buchungskategorie auf die Standard-Kategorie des Geschäfts (so genügt es,
    nur die vom Standard abweichenden Artikel zu erfassen). Negative
    Artikelzeilen (Rabatt/Pfand) netten dabei korrekt gegen.
    """
    params: dict = {}
    # Der "nur Ausgaben"-Filter darf nur ganze Buchungen betreffen (Einnahmen
    # ausblenden). Artikelzeilen gehören immer zu einem Kauf-Beleg und werden
    # unabhängig vom Einzel-Vorzeichen einbezogen.
    a_ausgaben = "AND b.betrag < 0" if nur_ausgaben else ""
    jahr_cond = ""
    if jahr:
        jahr_cond = "AND strftime('%Y', b.datum) = :jahr"
        params["jahr"] = str(jahr)

    sql = text(f"""
        WITH effektiv AS (
            -- A: nicht in Artikel aufgeteilte Buchungen → Buchungskategorie, bei
            --    Haushaltsbuch-Belegen ohne eigene Kategorie die Standard-Kategorie
            --    des Geschäfts (COALESCE).
            SELECT COALESCE(b.kategorie_id, hg.standard_kategorie_id) AS kategorie_id, b.betrag AS betrag
            FROM buchungen b
            LEFT JOIN haushaltsbuch_eintrag he ON he.buchung_id = b.id
            LEFT JOIN geschaeft hg ON he.geschaeft_id = hg.id
            WHERE b.status = 'gebucht' {a_ausgaben} {jahr_cond}
              AND NOT EXISTS (
                  SELECT 1 FROM haushaltsbuch_eintrag e
                  JOIN haushaltsbuch_position p ON p.eintrag_id = e.id
                  WHERE e.buchung_id = b.id AND p.kategorie_id IS NOT NULL
              )
            UNION ALL
            -- B: erfasste Artikel (Positionen mit Kategorie) aufgeteilter Buchungen
            SELECT p.kategorie_id, -p.gesamtpreis
            FROM buchungen b
            JOIN haushaltsbuch_eintrag e ON e.buchung_id = b.id
            JOIN haushaltsbuch_position p ON p.eintrag_id = e.id
            WHERE b.status = 'gebucht' {jahr_cond} AND p.kategorie_id IS NOT NULL
            UNION ALL
            -- C: nicht durch Artikel gedeckter Restbetrag → Buchungskategorie bzw.
            --    Standard-Kategorie des Geschäfts (nur erfasste Abweichler eintippen,
            --    Rest zählt automatisch auf den Laden-Standard).
            SELECT COALESCE(b.kategorie_id, hg.standard_kategorie_id), ROUND(b.betrag + psum.summe, 2)
            FROM buchungen b
            JOIN haushaltsbuch_eintrag he ON he.buchung_id = b.id
            LEFT JOIN geschaeft hg ON he.geschaeft_id = hg.id
            JOIN (
                SELECT e.buchung_id AS bid, SUM(p.gesamtpreis) AS summe
                FROM haushaltsbuch_eintrag e
                JOIN haushaltsbuch_position p ON p.eintrag_id = e.id AND p.kategorie_id IS NOT NULL
                GROUP BY e.buchung_id
            ) psum ON psum.bid = b.id
            WHERE b.status = 'gebucht' {jahr_cond}
              AND ROUND(b.betrag + psum.summe, 2) <> 0
        )
        SELECT
            k.id                AS kategorie_id,
            k.name              AS kategorie,
            k.uebergeordnet_id,
            COALESCE(p.name, k.name) AS obergruppe,
            ROUND(SUM(ef.betrag), 2) AS summe,
            COUNT(*)                 AS anzahl
        FROM effektiv ef
        JOIN kategorien k ON ef.kategorie_id = k.id
        LEFT JOIN kategorien p ON k.uebergeordnet_id = p.id
        GROUP BY k.id
        ORDER BY summe
    """)
    rows = db.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


# ── Geschäfte-Auswertung ──────────────────────────────────────────────────────

@router.get("/geschaefte")
def geschaefte_auswertung(
    jahr: Optional[int] = None,
    gruppierung: str = Query("geschaeft", pattern="^(geschaeft|kategorie)$"),
    geschaeft_id: Optional[int] = None,
    kategorie_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Ausgaben je Geschäft bzw. je Kategorie aus den Haushaltsbuch-Belegen.

    Rechnet bewusst rein auf der Belegwelt (`haushaltsbuch_eintrag` /
    `haushaltsbuch_position`), ohne Join auf `buchungen` — Barbelege sollen
    unabhängig vom Buchungsstatus enthalten sein. Die Summen können daher von
    /statistik/kategorien abweichen, das auf der Geldebene rechnet.

    Aufteilung je Beleg wie in Phase 15: Positionen mit Kategorie zählen
    einzeln, der nicht durch Artikel gedeckte Rest fällt auf die
    Standard-Kategorie des Geschäfts (bleibt diese leer → 'Ohne Kategorie').

    `gruppierung` bestimmt die Ebene, `geschaeft_id`/`kategorie_id` filtern auf
    die jeweils andere Dimension (Drilldown)."""
    params: dict = {}
    jahr_cond = ""
    if jahr:
        jahr_cond = "AND strftime('%Y', e.datum) = :jahr"
        params["jahr"] = str(jahr)

    # Drilldown-Filter greifen auf den aufgeteilten Zeilen, nicht auf den Belegen.
    filt = []
    if geschaeft_id is not None:
        filt.append("ef.geschaeft_id = :geschaeft_id")
        params["geschaeft_id"] = geschaeft_id
    if kategorie_id is not None:
        filt.append("ef.kategorie_id = :kategorie_id")
        params["kategorie_id"] = kategorie_id
    filt_cond = f"WHERE {' AND '.join(filt)}" if filt else ""

    if gruppierung == "kategorie":
        id_expr, name_expr, group_expr = "k.id", "COALESCE(k.name, 'Ohne Kategorie')", "k.id"
    else:
        id_expr, name_expr, group_expr = "g.id", "g.name", "g.id"

    sql = text(f"""
        WITH effektiv AS (
            -- A: erfasste Artikel (Positionen mit Kategorie)
            SELECT e.id AS eintrag_id, e.geschaeft_id, p.kategorie_id, p.gesamtpreis AS betrag
            FROM haushaltsbuch_eintrag e
            JOIN haushaltsbuch_position p ON p.eintrag_id = e.id
            WHERE e.geschaeft_id IS NOT NULL AND p.kategorie_id IS NOT NULL {jahr_cond}
            UNION ALL
            -- B: nicht durch Artikel gedeckter Rest → Standard-Kategorie des Ladens.
            --    Belege ganz ohne kategorisierte Artikel fallen hier komplett rein.
            SELECT e.id, e.geschaeft_id, g.standard_kategorie_id,
                   ROUND(e.betrag_gesamt - COALESCE(psum.summe, 0), 2)
            FROM haushaltsbuch_eintrag e
            JOIN geschaeft g ON e.geschaeft_id = g.id
            LEFT JOIN (
                SELECT p.eintrag_id AS eid, SUM(p.gesamtpreis) AS summe
                FROM haushaltsbuch_position p
                WHERE p.kategorie_id IS NOT NULL
                GROUP BY p.eintrag_id
            ) psum ON psum.eid = e.id
            WHERE e.geschaeft_id IS NOT NULL {jahr_cond}
              AND ROUND(e.betrag_gesamt - COALESCE(psum.summe, 0), 2) <> 0
        )
        SELECT
            {id_expr}                        AS id,
            {name_expr}                      AS name,
            ROUND(SUM(ef.betrag), 2)         AS summe,
            COUNT(DISTINCT ef.eintrag_id)    AS anzahl,
            ROUND(SUM(ef.betrag) / COUNT(DISTINCT ef.eintrag_id), 2) AS schnitt
        FROM effektiv ef
        LEFT JOIN geschaeft g ON ef.geschaeft_id = g.id
        LEFT JOIN kategorien k ON ef.kategorie_id = k.id
        {filt_cond}
        GROUP BY {group_expr}
        ORDER BY summe DESC
    """)
    rows = db.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


# ── Soll/Ist-Vergleich ────────────────────────────────────────────────────────

@router.get("/soll-ist")
def soll_ist(
    jahr: int = Query(..., description="Jahr für den Vergleich"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Plan (planung) vs. Ist (buchungen) je Kategorie für ein Jahr.
    planung.betrag_geplant ist Monatswert → * 12 für Jahresvergleich."""
    sql = text("""
        SELECT
            k.id            AS kategorie_id,
            k.name          AS kategorie,
            k.art,
            COALESCE(p.betrag_geplant * 12, 0) AS plan_jahr,
            COALESCE(ist.ist_summe, 0)          AS ist_summe,
            COALESCE(ist.ist_summe, 0) - COALESCE(p.betrag_geplant * 12, 0) AS abweichung
        FROM kategorien k
        LEFT JOIN planung p ON p.kategorie_id = k.id AND p.jahr = :jahr
        LEFT JOIN (
            SELECT kategorie_id, ROUND(SUM(betrag), 2) AS ist_summe
            FROM buchungen
            WHERE status = 'gebucht' AND strftime('%Y', datum) = :jahr_str
            GROUP BY kategorie_id
        ) ist ON ist.kategorie_id = k.id
        WHERE p.id IS NOT NULL OR ist.kategorie_id IS NOT NULL
        ORDER BY k.name
    """)
    rows = db.execute(sql, {"jahr": jahr, "jahr_str": str(jahr)}).mappings().all()
    return [dict(r) for r in rows]


# ── Liquiditätsvorschau ───────────────────────────────────────────────────────

@router.get("/liquiditaet")
def liquiditaet(
    konto_id: Optional[int] = None,
    monate: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Kontostand heute + geplante Buchungen der nächsten N Monate."""
    konto_filter = "AND b.konto_id = :konto_id" if konto_id else ""
    params: dict = {"konto_id": konto_id} if konto_id else {}

    # Aktueller Saldo (gebucht) — Startsaldo und Buchungen getrennt abfragen,
    # um Multiplikation durch den JOIN zu vermeiden
    if konto_id:
        konto_filter_k = "AND k.id = :konto_id"
        konto_typ_filter = ""
    else:
        konto_filter_k = ""
        konto_typ_filter = "AND k.typ = 'giro'"
    sql_startsaldo = text(f"""
        SELECT COALESCE(SUM(k.startsaldo), 0) AS startsaldo
        FROM konten k
        WHERE 1=1 {konto_filter_k} {konto_typ_filter}
    """)
    if konto_id:
        buchungen_konto_join = ""
        buchungen_konto_filter = "AND b.konto_id = :konto_id"
    else:
        buchungen_konto_join = "JOIN konten k ON b.konto_id = k.id"
        buchungen_konto_filter = "AND k.typ = 'giro'"

    sql_buchungen = text(f"""
        SELECT COALESCE(SUM(b.betrag), 0) AS buchungen_summe
        FROM buchungen b
        {buchungen_konto_join}
        WHERE b.status = 'gebucht'
          {buchungen_konto_filter}
    """)
    startsaldo = db.execute(sql_startsaldo, params).mappings().first()["startsaldo"] or 0
    buchungen_summe = db.execute(sql_buchungen, params).mappings().first()["buchungen_summe"] or 0
    saldo_heute = round(startsaldo + buchungen_summe, 2)

    # Geplante Buchungen je Monat
    sql_geplant = text(f"""
        SELECT
            strftime('%Y-%m', b.datum) AS monat,
            ROUND(SUM(b.betrag), 2)   AS summe
        FROM buchungen b
        {buchungen_konto_join}
        WHERE b.status = 'geplant'
          AND b.datum >= date('now')
          AND b.datum <= date('now', :monate_offset)
          {buchungen_konto_filter}
        GROUP BY monat
        ORDER BY monat
    """)
    params["monate_offset"] = f"+{monate} months"
    geplant_rows = db.execute(sql_geplant, params).mappings().all()

    # Kumulativer Vorschau-Verlauf
    lauf = saldo_heute
    verlauf = [{"monat": "heute", "saldo": saldo_heute, "aenderung": 0}]
    for r in geplant_rows:
        lauf = round(lauf + r["summe"], 2)
        verlauf.append({"monat": r["monat"], "saldo": lauf, "aenderung": r["summe"]})

    return {"saldo_heute": saldo_heute, "verlauf": verlauf}


# ── Sparkonten-Entwicklung ───────────────────────────────────────────────────

@router.get("/sparkonten")
def sparkonten_entwicklung(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Kumulativer Saldo je Sparkonto über Zeit (quartalsmäßig)."""
    sql = text("""
        SELECT
            k.name AS konto,
            strftime('%Y', b.datum) || '-Q' ||
                ((CAST(strftime('%m', b.datum) AS INTEGER) - 1) / 3 + 1) AS quartal,
            ROUND(SUM(b.betrag), 2) AS summe_quartal
        FROM buchungen b
        JOIN konten k ON b.konto_id = k.id
        WHERE k.typ IN ('spar', 'depot') AND b.status = 'gebucht'
        GROUP BY k.id, quartal
        ORDER BY k.name, quartal
    """)
    rows = db.execute(sql).mappings().all()
    # Kumulativ je Konto aufbauen
    kumulativ: dict[str, list] = {}
    lauf: dict[str, float] = {}
    for r in rows:
        k = r["konto"]
        if k not in kumulativ:
            kumulativ[k] = []
            lauf[k] = 0.0
        lauf[k] = round(lauf[k] + r["summe_quartal"], 2)
        kumulativ[k].append({"quartal": r["quartal"], "saldo": lauf[k]})
    return kumulativ


# ── Export CSV ───────────────────────────────────────────────────────────────

@router.get("/export/csv")
def export_csv(
    konto_id: Optional[int] = None,
    kategorie_id: Optional[int] = None,
    datum_von: Optional[str] = None,
    datum_bis: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Buchungen als CSV exportieren."""
    where = ["b.status = 'gebucht'"]
    params: dict = {}
    if konto_id:
        where.append("b.konto_id = :konto_id")
        params["konto_id"] = konto_id
    if kategorie_id:
        where.append("b.kategorie_id = :kategorie_id")
        params["kategorie_id"] = kategorie_id
    if datum_von:
        where.append("b.datum >= :datum_von")
        params["datum_von"] = datum_von
    if datum_bis:
        where.append("b.datum <= :datum_bis")
        params["datum_bis"] = datum_bis

    sql = text(f"""
        SELECT b.datum, b.betrag, b.empfaenger,
               k.name AS kategorie, ko.name AS konto,
               b.notiz, b.quelle
        FROM buchungen b
        LEFT JOIN kategorien k ON b.kategorie_id = k.id
        LEFT JOIN konten ko ON b.konto_id = ko.id
        WHERE {' AND '.join(where)}
        ORDER BY b.datum DESC
    """)
    rows = db.execute(sql, params).mappings().all()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["datum", "betrag", "empfaenger", "kategorie", "konto", "notiz", "quelle"],
        delimiter=";",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=buchungen.csv"},
    )


# ── 7.6 Hochrechnung (Ist vs. Prognose) ─────────────────────────────────────

@router.get("/hochrechnung")
def hochrechnung(
    monate: int = Query(12, ge=1, le=24),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Ist-Daten (gebucht) + Prognose aus wiederkehrenden Buchungen bis Folgejahresende."""
    heute = date.today()
    ende = date(heute.year + 1, 12, 31)

    # Ist: monatliche Summen der gebuchten (nicht-Transfer) Buchungen
    sql_ist = text("""
        SELECT
            strftime('%Y-%m', datum) AS monat,
            ROUND(SUM(betrag), 2)    AS summe
        FROM buchungen
        WHERE status = 'gebucht' AND ist_transfer = 0
        GROUP BY monat
        ORDER BY monat
    """)
    ist_rows = {r["monat"]: r["summe"] for r in db.execute(sql_ist).mappings().all()}

    # Virtuelle Projektion aus wiederkehrenden Vorlagen
    sql_vorlagen = text("""
        SELECT id, betrag, rhythmus, start_datum, end_datum, konto_id
        FROM wiederkehrende_buchungen
        WHERE aktiv = 1
    """)
    vorlagen = db.execute(sql_vorlagen).mappings().all()

    prognose: dict[str, float] = {}
    for v in vorlagen:
        aktuell = date.fromisoformat(v["start_datum"])
        end_datum = date.fromisoformat(v["end_datum"]) if v["end_datum"] else None
        rhythmus = v["rhythmus"]

        while aktuell <= ende:
            if end_datum and aktuell > end_datum:
                break
            # Nur zukünftige Termine als Prognose
            if aktuell > heute:
                monat_key = aktuell.strftime("%Y-%m")
                prognose[monat_key] = round(prognose.get(monat_key, 0.0) + v["betrag"], 2)
            if rhythmus == "monatlich":
                aktuell += relativedelta(months=1)
            elif rhythmus == "quartal":
                aktuell += relativedelta(months=3)
            elif rhythmus == "jaehrlich":
                aktuell += relativedelta(years=1)
            else:
                break

    # Alle Monate (Ist + Prognose) zusammenführen
    alle_monate = sorted(set(ist_rows) | set(prognose))
    verlauf = []
    for m in alle_monate:
        verlauf.append({
            "monat": m,
            "ist": ist_rows.get(m),
            "prognose": prognose.get(m),
        })

    return {"verlauf": verlauf}
