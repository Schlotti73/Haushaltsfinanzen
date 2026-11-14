"""kontoauszug_muster

Phase 9.1: Muster-Registry für den PDF-Kontoauszug-Import.
Legt die Tabelle an und seedet die drei bisher hartkodierten Banken
(Postbank/ING/Sparkasse) mit den Erkennungs-Keywords aus
``dispatcher._detect_bank``.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Seed: bisher hartkodierte Banken (dispatcher._detect_bank)
_SEED = [
    ("Postbank", "postbank", "postbank", '["postbank"]'),
    ("ING", "ing", "ing", '["ing-diba", "ing diba", "ing bank"]'),
    ("Sparkasse", "sparkasse", "sparkasse", '["sparkasse"]'),
]


def upgrade() -> None:
    op.create_table(
        'kontoauszug_muster',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('bank_key', sa.String(), nullable=False, unique=True),
        sa.Column('parser_key', sa.String(), nullable=True),
        sa.Column('erkennung_keywords', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('beispiel_pdf_pfad', sa.String(), nullable=True),
        sa.Column('screenshot_pfad', sa.String(), nullable=True),
        sa.Column('feld_markierungen', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('aktiv', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('notiz', sa.Text(), nullable=True),
        sa.Column('erstellt_am', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    muster = sa.table(
        'kontoauszug_muster',
        sa.column('name', sa.String),
        sa.column('bank_key', sa.String),
        sa.column('parser_key', sa.String),
        sa.column('erkennung_keywords', sa.Text),
    )
    op.bulk_insert(muster, [
        {"name": name, "bank_key": bank_key, "parser_key": parser_key,
         "erkennung_keywords": keywords}
        for name, bank_key, parser_key, keywords in _SEED
    ])


def downgrade() -> None:
    op.drop_table('kontoauszug_muster')
