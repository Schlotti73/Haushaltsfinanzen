"""Einstellungs-Tabelle (Schlüssel/Wert).

Legt die erste generische Einstellungstabelle an; genutzt u.a. für die
Toleranzen der PDF-Import-Vorschau beim Abgleich gegen vorhandene Buchungen
(siehe backend/app/services/einstellungen.py).

Bewusst ohne Startwerte: eine neue DB entsteht über create_all + stamp head
(app/db_init.py), diese Migration liefe dort also nie. Fehlende Schlüssel
fallen im Service auf die dort definierten Standardwerte zurück – so gibt es
nur eine Quelle für die Defaults.

Revision ID: t1b2c3d4e5f6
Revises: s0a1b2c3d4e5
Create Date: 2026-08-01
"""

from alembic import op
import sqlalchemy as sa

revision = "t1b2c3d4e5f6"
down_revision = "s0a1b2c3d4e5"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "einstellung",
        sa.Column("schluessel", sa.String(), primary_key=True),
        sa.Column("wert", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("einstellung")
