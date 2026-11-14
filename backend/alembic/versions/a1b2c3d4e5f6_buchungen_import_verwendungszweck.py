"""buchungen_import_verwendungszweck

Revision ID: a1b2c3d4e5f6
Revises: 0c7cbefa440b
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0c7cbefa440b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buchungen', sa.Column('import_verwendungszweck', sa.Text(), nullable=True))
    # Bestehende Import-Buchungen: notiz → import_verwendungszweck übertragen
    op.execute(
        "UPDATE buchungen SET import_verwendungszweck = notiz WHERE quelle = 'import' AND notiz IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('buchungen', 'import_verwendungszweck')
