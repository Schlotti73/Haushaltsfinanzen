"""Haushaltsbuch: gelernte Artikel-Korrekturen je Geschäft (OCR-Rohtext -> Bezeichnung).

Merkt sich pro Geschäft, dass ein bestimmter OCR-Rohtext (z.B. „G&G" bei Edeka)
zuletzt zu einer bestimmten Bezeichnung korrigiert wurde, um denselben
wiederkehrenden Lesefehler beim nächsten Kassenzettel automatisch vorzuschlagen.

Revision ID: s0a1b2c3d4e5
Revises: r9f0a1b2c3d4
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa

revision = "s0a1b2c3d4e5"
down_revision = "r9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "haushaltsbuch_artikel_korrektur",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("geschaeft_id", sa.Integer(), sa.ForeignKey("geschaeft.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ocr_text", sa.String(), nullable=False),
        sa.Column("bezeichnung", sa.String(), nullable=False),
        sa.Column("aktualisiert_am", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("geschaeft_id", "ocr_text", name="uq_artikel_korrektur_geschaeft_text"),
    )


def downgrade() -> None:
    op.drop_table("haushaltsbuch_artikel_korrektur")
