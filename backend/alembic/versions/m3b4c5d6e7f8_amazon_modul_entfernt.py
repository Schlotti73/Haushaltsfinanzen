"""Amazon-Modul entfernt: amazon_bestellungen + einstellungen (Key/Value) gedroppt.

Revision ID: m3b4c5d6e7f8
Revises: l2a3b4c5d6e7
Create Date: 2026-07-17
"""

from alembic import op

revision = "m3b4c5d6e7f8"
down_revision = "l2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_amazon_buchung")
    op.execute("DROP TABLE IF EXISTS amazon_bestellungen")
    op.execute("DROP TABLE IF EXISTS einstellungen")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS amazon_bestellungen (
            id              INTEGER PRIMARY KEY,
            bestellnummer   TEXT    NOT NULL UNIQUE,
            bestelldatum    TEXT    NOT NULL,
            betrag_gesamt   REAL    NOT NULL,
            status          TEXT,
            artikel         TEXT,
            buchung_id      INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
            abgeglichen_am  TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS einstellungen (
            schluessel  TEXT PRIMARY KEY,
            wert        TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_amazon_buchung ON amazon_bestellungen(buchung_id)")
