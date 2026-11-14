"""import_regel

Phase 16: Zwei-Stufen-Regeln zur Normalisierung des Bankrohtexts beim
Kontoauszug-Import (Anbieter -> Empfänger, Händler -> Notiz/Kategorie).

Bewusst als reguläre Alembic-Revision und nicht als Handskript unter
``scripts/``: sowohl das Anlegen einer neuen Datenbank
(routers/datenbanken.py -> init_db_schema) als auch das Zurückspielen eines
alten Backups (routers/einstellungen.py -> init_db_schema) laufen über
Alembic. Nur so existiert die Tabelle danach in beiden Fällen.

Revision ID: v3d4e5f6a7b8
Revises: u2c3d4e5f6a7
Create Date: 2026-08-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v3d4e5f6a7b8"
down_revision: Union[str, None] = "u2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_regel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("stufe", sa.String(), nullable=False, server_default="haendler"),
        sa.Column("schluesselwoerter", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("iban_muster", sa.String(), nullable=True),
        sa.Column(
            "empfaenger_id",
            sa.Integer(),
            sa.ForeignKey("empfaenger.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "kategorie_id",
            sa.Integer(),
            sa.ForeignKey("kategorien.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notiz_text", sa.String(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("notiz", sa.Text(), nullable=True),
        sa.Column(
            "erstellt_am",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("stufe IN ('anbieter', 'haendler')", name="ck_import_regel_stufe"),
    )
    # Regeln werden bei jedem Import über alle Buchungen des PDFs geprüft;
    # der Index hält den Stufenfilter billig, auch wenn die Liste wächst.
    op.create_index("ix_import_regel_stufe", "import_regel", ["stufe", "aktiv"])


def downgrade() -> None:
    op.drop_index("ix_import_regel_stufe", table_name="import_regel")
    op.drop_table("import_regel")
