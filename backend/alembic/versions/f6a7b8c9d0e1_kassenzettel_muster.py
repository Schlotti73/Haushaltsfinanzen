"""kassenzettel_muster

Phase 10.1: Muster-Registry für den OCR-Kassenzettel-Import. Legt die Tabelle an
und seedet gängige Geschäfte mit Erkennungs-Keywords. Die MwSt→Kategorie-
Zuordnung bleibt leer (kategorie-IDs sind nicht stabil) und wird in den
Einstellungen pro Geschäft gepflegt; ohne Zuordnung greift die satzbasierte
Voreinstellung im Router.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Seed: gängige Geschäfte mit Erkennungs-Keywords. start/stop-Marker sind
# bewusst grob gewählt und können in den Einstellungen am Beispielfoto
# verfeinert werden.
_SEED = [
    # (name, geschaeft_key, keywords, start_marker, stop_marker)
    ("Aldi",      "aldi",      '["aldi"]',                  None,        "summe"),
    ("Lidl",      "lidl",      '["lidl"]',                  None,        "zu zahlen"),
    ("Edeka",     "edeka",     '["edeka"]',                 None,        "summe"),
    ("Rewe",      "rewe",      '["rewe"]',                  None,        "summe"),
    ("Kaufland",  "kaufland",  '["kaufland"]',              None,        "summe"),
    ("Penny",     "penny",     '["penny"]',                 None,        "summe"),
    ("Netto",     "netto",     '["netto marken", "netto"]', None,        "summe"),
    ("Rossmann",  "rossmann",  '["rossmann"]',              None,        "summe"),
    ("dm",        "dm",        '["dm-drogerie", "dm "]',    None,        "summe"),
]


def upgrade() -> None:
    op.create_table(
        'kassenzettel_muster',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('geschaeft_key', sa.String(), nullable=False, unique=True),
        sa.Column('erkennung_keywords', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('start_marker', sa.String(), nullable=True),
        sa.Column('stop_marker', sa.String(), nullable=True),
        sa.Column('skip_keywords', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('preis_regex', sa.String(), nullable=True),
        sa.Column('mwst_kategorie_map', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('beispiel_bild_pfad', sa.String(), nullable=True),
        sa.Column('aktiv', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('notiz', sa.Text(), nullable=True),
        sa.Column('erstellt_am', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    muster = sa.table(
        'kassenzettel_muster',
        sa.column('name', sa.String),
        sa.column('geschaeft_key', sa.String),
        sa.column('erkennung_keywords', sa.Text),
        sa.column('start_marker', sa.String),
        sa.column('stop_marker', sa.String),
    )
    op.bulk_insert(muster, [
        {"name": name, "geschaeft_key": key, "erkennung_keywords": kw,
         "start_marker": start, "stop_marker": stop}
        for name, key, kw, start, stop in _SEED
    ])


def downgrade() -> None:
    op.drop_table('kassenzettel_muster')
