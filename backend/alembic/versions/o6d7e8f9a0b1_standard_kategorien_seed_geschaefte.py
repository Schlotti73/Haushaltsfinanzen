"""Standard-Kategorien fuer Seed-Geschaefte setzen

Phase 15: Die von o5d6e7f8a9b0 aus den Kassenzettel-Mustern angelegten Laeden
(Aldi, Lidl, Rewe, Kaufland, Penny, Netto, Rossmann, dm) bekommen eine sinnvolle
Standard-Kategorie. Dadurch faellt in der Kategorien-Statistik der nicht
einzeln erfasste Rest eines Belegs automatisch auf diese Kategorie
(COALESCE(Buchungskategorie, Geschaeft.standard_kategorie_id)).

Idempotent: setzt nur, wo `standard_kategorie_id` noch NULL ist, und nur ueber
Kategorie-Namen (IDs nicht stabil). Ueberschreibt keine bestehenden Werte.

Revision ID: o6d7e8f9a0b1
Revises: o5d6e7f8a9b0
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o6d7e8f9a0b1"
down_revision: Union[str, None] = "o5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Geschaeft-Name (lower) -> Standard-Kategorie-Name
_STANDARD_KAT = {
    "aldi": "Lebensmittel", "lidl": "Lebensmittel", "rewe": "Lebensmittel",
    "kaufland": "Lebensmittel", "penny": "Lebensmittel", "netto": "Lebensmittel",
    "rossmann": "Drogerie", "dm": "Drogerie",
}


def upgrade() -> None:
    conn = op.get_bind()
    for name, kat_name in _STANDARD_KAT.items():
        kat = conn.execute(
            sa.text("SELECT id FROM kategorien WHERE lower(name) = lower(:k) ORDER BY id LIMIT 1"),
            {"k": kat_name},
        ).fetchone()
        if not kat:
            continue
        conn.execute(
            sa.text(
                "UPDATE geschaeft SET standard_kategorie_id = :kid "
                "WHERE lower(name) = :n AND standard_kategorie_id IS NULL"
            ),
            {"kid": kat[0], "n": name},
        )


def downgrade() -> None:
    # Keine Rueckabwicklung der Datensetzung (nur Stammdaten-Vorbelegung).
    pass
