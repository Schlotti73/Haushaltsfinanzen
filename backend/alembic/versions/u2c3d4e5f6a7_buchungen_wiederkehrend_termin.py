"""Buchungen: wiederkehrend_termin (ursprünglich geplantes Datum).

`datum` einer generierten Buchung kann beim PDF-Kontoauszug-Abgleich auf das
tatsächliche Bankdatum überschrieben werden (Treffer-Verknüpfung in
import_pdf.py). Der Dublettencheck in generierung.py verglich bisher gegen
`datum` – nach so einer Verschiebung fand er den ursprünglichen Termin nicht
mehr und erzeugte beim nächsten Lauf eine zweite, doppelte Buchung.

`wiederkehrend_termin` speichert den Termin, wie ihn die Vorlage vorsieht,
unveränderlich ab dem Erzeugen. Der Dublettencheck vergleicht jetzt dagegen
statt gegen `datum`.

Revision ID: u2c3d4e5f6a7
Revises: t1b2c3d4e5f6
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa

revision = "u2c3d4e5f6a7"
down_revision = "t1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("buchungen", sa.Column("wiederkehrend_termin", sa.String(), nullable=True))
    # Bestehende generierte Buchungen: `datum` ist beim Erzeugen == Termin gewesen,
    # solange es nicht bereits durch einen PDF-Treffer überschrieben wurde. Das ist
    # die einzig verfügbare Näherung für den Rückwirkungs-Backfill.
    op.execute(
        "UPDATE buchungen SET wiederkehrend_termin = datum WHERE wiederkehrend_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("buchungen", "wiederkehrend_termin")
