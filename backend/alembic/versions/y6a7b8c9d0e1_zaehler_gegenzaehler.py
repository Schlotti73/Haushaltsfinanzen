"""Zähler: Gegenzähler für Einspeisung, Stilllegung nachtragen, Doppelzuordnung aufräumen.

Vier Dinge:

1. Neue Spalte zaehler.gegenzaehler_id. Am Einspeisezähler gesetzt, zeigt auf den
   Bezugszähler, mit dem er verrechnet wird (PV-Einspeisung mindert die Stromkosten).
   Bewusst ohne FK-Constraint - SQLite müsste die Tabelle dafür neu bauen; die
   Gültigkeit erzwingt der Router beim Speichern.

2. Einspeisezähler, zu denen es genau einen nicht stillgelegten Bezugszähler
   derselben Art im selben Gebäude gibt, werden damit verknüpft.

3. Zähler mit Kategorie, deren letzte Ablesung vor der eines anderen Zählers
   derselben Art und Richtung im selben Gebäude liegt, sind ausgebaut und durch
   diesen ersetzt: aktiv=0 und gueltig_bis auf den letzten Ablesetag. Ohne
   gueltig_bis mahnt die Erinnerung weiter Ablesungen an, die niemand mehr machen
   kann. Dazu aktiv für alle Zähler von NULL auf 1 - das Feld war dreiwertig,
   weil der Erstimport es nicht gesetzt hat.

4. Kategorien, die an einem Zähler des Gebäudes hängen und zusätzlich als
   gebaeude_kostenkategorie geführt werden, wurden doppelt als Kosten gezählt.
   Die Zuordnung am Gebäude fällt weg, der Zähler gewinnt.

Revision ID: y6a7b8c9d0e1
Revises: x5f6a7b8c9d0
Create Date: 2026-11-01
"""

from alembic import op

revision = "y6a7b8c9d0e1"
down_revision = "x5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    cols = [r[1] for r in bind.exec_driver_sql("PRAGMA table_info(zaehler)").fetchall()]
    if "gegenzaehler_id" not in cols:
        op.execute("ALTER TABLE zaehler ADD COLUMN gegenzaehler_id INTEGER")

    # aktiv war dreiwertig (NULL aus dem Erstimport)
    op.execute("UPDATE zaehler SET aktiv = 1 WHERE aktiv IS NULL")

    # 3. Ausgebaute Zähler stilllegen. Eng gefasst: nur Zähler mit Kategorie
    #    (also in der Kostenrechnung geführt), deren letzte Ablesung vor der eines
    #    anderen Zählers derselben Art und Richtung im selben Gebäude liegt.
    #    Zähler ohne Kategorie bleiben unangetastet - dort ist nicht zu erkennen,
    #    ob sie ausgebaut oder nur lange nicht abgelesen wurden.
    op.execute("""
        UPDATE zaehler SET aktiv = 0, gueltig_bis = (
            SELECT MAX(a.datum) FROM zaehler_ablesung a WHERE a.zaehler_id = zaehler.id
        )
        WHERE gueltig_bis IS NULL AND kategorie_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM zaehler_ablesung a WHERE a.zaehler_id = zaehler.id)
          AND (SELECT MAX(a.jahr) FROM zaehler_ablesung a WHERE a.zaehler_id = zaehler.id)
              < (SELECT MAX(a2.jahr) FROM zaehler_ablesung a2
                 JOIN zaehler z2 ON z2.id = a2.zaehler_id
                 WHERE z2.gebaeude_id = zaehler.gebaeude_id AND z2.art = zaehler.art
                   AND z2.richtung = zaehler.richtung)
    """)

    # 2. Einspeisezähler mit genau einem aktiven Bezugszähler derselben Art verknüpfen
    op.execute("""
        UPDATE zaehler SET gegenzaehler_id = (
            SELECT b.id FROM zaehler b
            WHERE b.gebaeude_id = zaehler.gebaeude_id AND b.art = zaehler.art
              AND b.richtung = 'bezug' AND b.gueltig_bis IS NULL
        )
        WHERE richtung = 'einspeisung' AND gegenzaehler_id IS NULL
          AND (SELECT COUNT(*) FROM zaehler b
               WHERE b.gebaeude_id = zaehler.gebaeude_id AND b.art = zaehler.art
                 AND b.richtung = 'bezug' AND b.gueltig_bis IS NULL) = 1
    """)

    # 4. Doppelzuordnung auflösen
    op.execute("""
        DELETE FROM gebaeude_kostenkategorie
        WHERE EXISTS (
            SELECT 1 FROM zaehler z
            WHERE z.gebaeude_id = gebaeude_kostenkategorie.gebaeude_id
              AND z.kategorie_id = gebaeude_kostenkategorie.kategorie_id
        )
    """)


def downgrade() -> None:
    pass
    # Spalte wird bewusst belassen (additive Migration); die Datenkorrekturen
    # sind Reparaturen und werden nicht zurückgedreht.
