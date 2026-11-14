"""geschaeft <-> kassenzettel_muster verknuepfen (FK)

Phase 15: Echte 1:1-Verknuepfung zwischen Geschaeft-Stammdaten und dem
OCR-Kassenzettel-Muster statt loser Namens-/Keyword-Kopplung. Fuegt
`kassenzettel_muster.geschaeft_id` (FK, unique) hinzu und verknuepft die
Bestandsdaten: je Muster wird das gleichnamige Geschaeft gesucht (case-insensitiv)
bzw. angelegt und verknuepft. Damit ist die MwSt->Kategorie-Zuordnung pro
Geschaeft auf der Geschaefte-Seite pflegbar.

Revision ID: o5d6e7f8a9b0
Revises: n4c5d6e7f8a9
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o5d6e7f8a9b0"
down_revision: Union[str, None] = "n4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Spalte + FK + Unique (Batch-Modus, damit SQLite den FK sauber anlegt)
    with op.batch_alter_table("kassenzettel_muster", schema=None) as batch:
        batch.add_column(sa.Column("geschaeft_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_kzm_geschaeft", "geschaeft", ["geschaeft_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_unique_constraint("uq_kzm_geschaeft", ["geschaeft_id"])

    # Bestandsdaten verknuepfen: je Muster ein Geschaeft (per Name) finden/anlegen.
    # (Standard-Kategorien der Seed-Laeden setzt die Folge-Migration o6d7e8f9a0b1.)
    conn = op.get_bind()
    muster = conn.execute(sa.text("SELECT id, name FROM kassenzettel_muster ORDER BY id")).fetchall()
    for mid, mname in muster:
        row = conn.execute(
            sa.text("SELECT id FROM geschaeft WHERE lower(name) = lower(:n)"), {"n": mname}
        ).fetchone()
        if row:
            gid = row[0]
        else:
            conn.execute(
                sa.text("INSERT INTO geschaeft (name, aktiv) VALUES (:n, 1)"), {"n": mname}
            )
            gid = conn.execute(
                sa.text("SELECT id FROM geschaeft WHERE lower(name) = lower(:n)"), {"n": mname}
            ).fetchone()[0]
        conn.execute(
            sa.text("UPDATE kassenzettel_muster SET geschaeft_id = :g WHERE id = :m"),
            {"g": gid, "m": mid},
        )


def downgrade() -> None:
    with op.batch_alter_table("kassenzettel_muster", schema=None) as batch:
        batch.drop_constraint("uq_kzm_geschaeft", type_="unique")
        batch.drop_constraint("fk_kzm_geschaeft", type_="foreignkey")
        batch.drop_column("geschaeft_id")
