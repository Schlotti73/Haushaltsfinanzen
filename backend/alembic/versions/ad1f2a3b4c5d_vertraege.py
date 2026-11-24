"""Verträge und laufende Verpflichtungen.

Ein Vertrag hält Stammdaten, Laufzeit und Frist — nicht das Geld. Was er
kosten *soll*, steht weiter an den wiederkehrenden Buchungen, die jetzt auf
ihn zeigen dürfen (1:n: Strom hat den monatlichen Abschlag und die
Jahresabrechnung). Was er wirklich gekostet hat, steht an den Buchungen, die
`vertrag_id` tragen.

Der Kündigungstermin ist **keine** Spalte: er wird aus `laufzeit_bis`,
`kuendigungsfrist` und `verlaengerung_monate` gerechnet. Gespeichert würde er
nach jeder stillen Verlängerung falsch sein, ohne dass es auffällt.

`mandatsreferenz` ist UNIQUE: dieselbe SEPA-Referenz an zwei Verträgen wäre
ein stiller Dauerfehler — jede Lastschrift landete beim erstgefundenen. Der
UNIQUE-Index lässt mehrere NULL zu, Verträge ohne Referenz sind also
unbegrenzt erlaubt.

Rückwärts verschwinden die Verknüpfungen und die Tabelle. Die Buchungen und
die wiederkehrenden Buchungen selbst bleiben unangetastet.

Revision ID: ad1f2a3b4c5d
Revises: ac0e1f2a3b4c
Create Date: 2026-11-22
"""

from alembic import op
import sqlalchemy as sa

revision = "ad1f2a3b4c5d"
down_revision = "ac0e1f2a3b4c"
branch_labels = None
depends_on = None


def _spalten(conn, tabelle: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({tabelle})"))}


def _tabelle_da(conn, name: str) -> bool:
    return bool(conn.execute(
        sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
    ).fetchone())


def upgrade() -> None:
    conn = op.get_bind()

    if not _tabelle_da(conn, "vertraege"):
        conn.execute(sa.text("""
            CREATE TABLE vertraege (
                id                       INTEGER PRIMARY KEY,
                name                     TEXT    NOT NULL,
                anbieter                 TEXT,
                vertragsnummer           TEXT,
                kundennummer             TEXT,
                kategorie_id             INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
                konto_id                 INTEGER REFERENCES konten(id) ON DELETE SET NULL,
                empfaenger_id            INTEGER REFERENCES empfaenger(id) ON DELETE SET NULL,
                mandatsreferenz          TEXT,
                beginn                   TEXT,
                laufzeit_bis             TEXT,
                kuendigungsfrist         INTEGER,
                kuendigungsfrist_einheit TEXT    NOT NULL DEFAULT 'monate',
                verlaengerung_monate     INTEGER,
                gekuendigt_am            TEXT,
                endet_am                 TEXT,
                notiz                    TEXT,
                aktiv                    INTEGER NOT NULL DEFAULT 1,
                erstellt_von             INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
                erstellt_am              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (kuendigungsfrist_einheit IN ('tage', 'wochen', 'monate'))
            )
        """))
        # Mehrere NULL bleiben erlaubt - ein Vertrag ohne Referenz ist der Normalfall,
        # etwa wenn er ueber einen Zahlungsdienstleister bezahlt wird.
        conn.execute(sa.text(
            "CREATE UNIQUE INDEX idx_vertraege_mandatsreferenz "
            "ON vertraege(mandatsreferenz) WHERE mandatsreferenz IS NOT NULL"
        ))
        conn.execute(sa.text("CREATE INDEX idx_vertraege_empfaenger ON vertraege(empfaenger_id)"))
        conn.execute(sa.text("CREATE INDEX idx_vertraege_konto ON vertraege(konto_id)"))

    if "vertrag_id" not in _spalten(conn, "buchungen"):
        op.add_column("buchungen", sa.Column("vertrag_id", sa.Integer(), nullable=True))
        conn.execute(sa.text("CREATE INDEX idx_buchungen_vertrag ON buchungen(vertrag_id)"))

    if "vertrag_id" not in _spalten(conn, "wiederkehrende_buchungen"):
        op.add_column("wiederkehrende_buchungen", sa.Column("vertrag_id", sa.Integer(), nullable=True))
        conn.execute(sa.text(
            "CREATE INDEX idx_wiederk_vertrag ON wiederkehrende_buchungen(vertrag_id)"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    if "vertrag_id" in _spalten(conn, "wiederkehrende_buchungen"):
        conn.execute(sa.text("DROP INDEX IF EXISTS idx_wiederk_vertrag"))
        op.drop_column("wiederkehrende_buchungen", "vertrag_id")

    if "vertrag_id" in _spalten(conn, "buchungen"):
        conn.execute(sa.text("DROP INDEX IF EXISTS idx_buchungen_vertrag"))
        op.drop_column("buchungen", "vertrag_id")

    if _tabelle_da(conn, "vertraege"):
        conn.execute(sa.text("DROP TABLE vertraege"))
