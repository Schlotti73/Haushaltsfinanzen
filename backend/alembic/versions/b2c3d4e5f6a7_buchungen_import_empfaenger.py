"""buchungen_import_empfaenger

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buchungen', sa.Column('import_empfaenger', sa.String(), nullable=True))
    op.add_column('buchungen', sa.Column('import_iban', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('buchungen', 'import_iban')
    op.drop_column('buchungen', 'import_empfaenger')
