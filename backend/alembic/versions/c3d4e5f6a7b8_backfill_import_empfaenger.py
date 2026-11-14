"""backfill_import_empfaenger

Bestehende Import-Buchungen: import_empfaenger aus empfaenger befüllen,
sofern der Wert noch NULL ist (d.h. vor dem neuen Import-Code importiert).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE buchungen
           SET import_empfaenger = empfaenger
         WHERE quelle = 'import'
           AND import_empfaenger IS NULL
           AND empfaenger IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
