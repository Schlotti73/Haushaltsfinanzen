"""Generischer CSV-Import: Tabelle csv_profil und drei Importfelder an der Buchung.

Die Buchungsfelder kommen nur aus strukturierten Exporten (CSV, später CAMT);
in Buchungen aus PDF-Auszügen bleiben sie leer. Sie werden nachgetragen, nicht
befüllt – ein Backfill ist von hier aus nicht möglich, weil die Angaben in den
PDFs nie standen.

Revision ID: aa8c9d0e1f2a3
Revises: z7b8c9d0e1f2
Create Date: 2026-11-21
"""

from alembic import op
import sqlalchemy as sa

revision = "aa8c9d0e1f2a3"
down_revision = "z7b8c9d0e1f2"
branch_labels = None
depends_on = None


SPALTEN = ("import_umsatzart", "import_mandatsreferenz", "import_referenz")


def _spalten(conn, tabelle: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({tabelle})"))}


def upgrade() -> None:
    conn = op.get_bind()

    if "csv_profil" not in sa.inspect(conn).get_table_names():
        op.create_table(
            "csv_profil",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("bank_key", sa.String(), nullable=False),
            sa.Column("struktur", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("zuordnung", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("kopf_signatur", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("notiz", sa.Text()),
            sa.Column("erstellt_am", sa.DateTime(), nullable=False,
                      server_default=sa.func.current_timestamp()),
            sa.UniqueConstraint("bank_key", name="uq_csv_profil_bank_key"),
        )

    vorhanden = _spalten(conn, "buchungen")
    for spalte in SPALTEN:
        if spalte not in vorhanden:
            op.add_column("buchungen", sa.Column(spalte, sa.String()))


def downgrade() -> None:
    conn = op.get_bind()
    vorhanden = _spalten(conn, "buchungen")
    for spalte in SPALTEN:
        if spalte in vorhanden:
            op.drop_column("buchungen", spalte)
    if "csv_profil" in sa.inspect(conn).get_table_names():
        op.drop_table("csv_profil")
