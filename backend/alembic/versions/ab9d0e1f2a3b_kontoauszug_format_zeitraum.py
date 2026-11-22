"""Kontoauszug: Format und bestätigter Zeitraum.

Grundlage der Zeitraum-Sperre beim Import: ein PDF darf in einem Bereich, den
ein CSV-Auszug desselben Kontos abdeckt, nichts mehr importieren. Dafür muss
ein archivierter Auszug sagen können, welches Format er hat.

`format` wird aus der Dateiendung nachgetragen – sie ist im Code schon heute
das maßgebliche Kriterium (siehe `_auszug_ablegen` in routers/import_pdf.py).
Eine unbekannte Endung bleibt leer; leer gilt als "nicht CSV" und sperrt damit
nichts, also genau das Verhalten von vorher.

`zeitraum_bestaetigt` trennt den vom Benutzer bestätigten Zeitraum vom
abgeleiteten. `zeitraum_von/bis` ist bisher min/max der geparsten Buchungen und
damit immer zu eng – der Altbestand steht deshalb auf 0 und wird in der
Auszugsliste als "abgeleitet" ausgewiesen, statt eine Genauigkeit zu behaupten,
die nie erhoben wurde.

Revision ID: ab9d0e1f2a3b
Revises: aa8c9d0e1f2a3
Create Date: 2026-11-22
"""

from alembic import op
import sqlalchemy as sa

revision = "ab9d0e1f2a3b"
down_revision = "aa8c9d0e1f2a3"
branch_labels = None
depends_on = None


def _spalten(conn, tabelle: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({tabelle})"))}


def upgrade() -> None:
    conn = op.get_bind()
    vorhanden = _spalten(conn, "kontoauszug")

    if "format" not in vorhanden:
        op.add_column("kontoauszug", sa.Column("format", sa.String()))
        # Reihenfolge zählt nicht, die Bedingungen schließen sich aus.
        conn.execute(sa.text(
            "UPDATE kontoauszug SET format = 'pdf' WHERE lower(dateiname) LIKE '%.pdf'"
        ))
        conn.execute(sa.text(
            "UPDATE kontoauszug SET format = 'csv' "
            "WHERE lower(dateiname) LIKE '%.csv' OR lower(dateiname) LIKE '%.txt'"
        ))

    if "zeitraum_bestaetigt" not in vorhanden:
        op.add_column("kontoauszug", sa.Column(
            "zeitraum_bestaetigt", sa.Boolean(), nullable=False, server_default=sa.text("0"),
        ))


def downgrade() -> None:
    conn = op.get_bind()
    vorhanden = _spalten(conn, "kontoauszug")
    if "zeitraum_bestaetigt" in vorhanden:
        op.drop_column("kontoauszug", "zeitraum_bestaetigt")
    if "format" in vorhanden:
        op.drop_column("kontoauszug", "format")
