"""Tag-Modul entfernt: Tags → Kategorien (Option A), dann tags + buchung_tags gedroppt.

Die Tags dieser App wurden faktisch als Einzelwert-Unterklassifikation von
"Nebenkosten" (bzw. "Instandhaltung") genutzt. Diese Migration überführt sie in
den hierarchischen Kategoriebaum und entfernt anschließend die Tag-Tabellen.

Idempotent: existiert die Tabelle `tags` nicht mehr oder ist leer, wird nur der
DROP ausgeführt (bzw. übersprungen). Die Datenüberführung ist hier ein No-Op –
siehe den Kommentar an TAGS_A weiter unten; übrig bleibt der Tabellen-Drop.

Revision ID: n4c5d6e7f8a9
Revises: m3b4c5d6e7f8
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

revision = "n4c5d6e7f8a9"
down_revision = "m3b4c5d6e7f8"
branch_labels = None
depends_on = None

# Zähler-/Vertrags-Tags → Unterkategorie unter "Nebenkosten"
#
# Die Listen sind absichtlich leer. Sie enthielten die Zähler- und
# Vertragsnummern einer einzelnen echten Datenbank; die ist längst migriert und
# in jeder anderen Datenbank hätte kein einziger Name getroffen. Die Migration
# läuft deshalb als No-Op durch: der Drop der Tag-Tabellen am Ende passiert
# weiterhin, nur die Datenüberführung entfällt. Eine noch nicht migrierte
# Alt-Datenbank wird vorher mit dem Einmal-Skript überführt, das außerhalb des
# Repositorys liegt (siehe docs/beispieldaten.md).
TAGS_A: list[str] = []
# → Unterkategorie unter "Instandhaltung" (enthält keine Nummern und bleibt)
TAGS_B: list[str] = ["Instandsetzung"]
# Übrige Tags (Streu-/Einzelfälle, ungenutzt) werden nur entfernt (Kategorie bleibt).


def _kategorie(conn, name, parent_id, art):
    row = conn.execute(
        sa.text("SELECT id FROM kategorien WHERE name=:n AND uebergeordnet_id IS :p"),
        {"n": name, "p": parent_id},
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        sa.text(
            "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) "
            "VALUES (:n, :a, :p, 1)"
        ),
        {"n": name, "a": art, "p": parent_id},
    )
    return conn.execute(sa.text("SELECT last_insert_rowid()")).scalar()


def _daten_ueberfuehren(conn) -> None:
    insp = sa.inspect(conn)
    if "tags" not in insp.get_table_names() or "buchung_tags" not in insp.get_table_names():
        return
    # Nichts zu tun, wenn keine Verknüpfungen mehr existieren
    if not conn.execute(sa.text("SELECT 1 FROM buchung_tags LIMIT 1")).fetchone():
        return

    parents = {}
    for pname in ("Nebenkosten", "Instandhaltung"):
        r = conn.execute(
            sa.text("SELECT id, art FROM kategorien WHERE name=:n"), {"n": pname}
        ).fetchone()
        if r:
            parents[pname] = (r[0], r[1])

    plan = [(t, "Nebenkosten") for t in TAGS_A] + [(t, "Instandhaltung") for t in TAGS_B]
    for tag_name, parent_name in plan:
        if parent_name not in parents:
            continue
        parent_id, art = parents[parent_name]
        trow = conn.execute(
            sa.text("SELECT id FROM tags WHERE name=:n"), {"n": tag_name}
        ).fetchone()
        if not trow:
            continue
        kat_id = _kategorie(conn, tag_name, parent_id, art)
        conn.execute(
            sa.text(
                "UPDATE buchungen SET kategorie_id=:k WHERE id IN "
                "(SELECT buchung_id FROM buchung_tags WHERE tag_id=:t)"
            ),
            {"k": kat_id, "t": trow[0]},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _daten_ueberfuehren(conn)
    op.execute("DROP TABLE IF EXISTS buchung_tags")
    op.execute("DROP TABLE IF EXISTS tags")


def downgrade() -> None:
    # Leere Tag-Tabellen wiederherstellen (Daten sind unwiederbringlich in
    # Kategorien überführt und werden nicht zurückgeschrieben).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS buchung_tags (
            buchung_id INTEGER NOT NULL REFERENCES buchungen(id) ON DELETE CASCADE,
            tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (buchung_id, tag_id)
        )
        """
    )
