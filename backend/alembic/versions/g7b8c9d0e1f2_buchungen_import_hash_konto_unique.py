"""buchungen: import_hash-Unique von global auf (konto_id, import_hash) ändern

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-20
"""

from alembic import op

revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite unterstützt kein DROP CONSTRAINT direkt.
    # Wir bauen die Tabelle über einen temporären Namen neu.
    op.execute("DROP TABLE IF EXISTS buchungen_new")
    op.execute("""
        CREATE TABLE buchungen_new (
            id                  INTEGER PRIMARY KEY,
            konto_id            INTEGER REFERENCES konten(id) ON DELETE CASCADE,
            datum               VARCHAR NOT NULL,
            betrag              FLOAT   NOT NULL,
            empfaenger          VARCHAR,
            empfaenger_id       INTEGER REFERENCES empfaenger(id) ON DELETE SET NULL,
            kategorie_id        INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            projekt_id          INTEGER REFERENCES projekte(id) ON DELETE SET NULL,
            notiz               TEXT,
            status              VARCHAR NOT NULL DEFAULT 'gebucht',
            quelle              VARCHAR NOT NULL DEFAULT 'manuell',
            wiederkehrend_id    INTEGER REFERENCES wiederkehrende_buchungen(id) ON DELETE SET NULL,
            verwendungszweck    TEXT,
            import_hash         VARCHAR,
            import_verwendungszweck TEXT,
            import_empfaenger   VARCHAR,
            import_iban         VARCHAR,
            erstellt_von        INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            erstellt_am         DATETIME NOT NULL,
            gegenbuchung_id     INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
            ist_transfer        BOOLEAN NOT NULL DEFAULT 0,
            verknuepft_mit_id   INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
            verknuepfung_typ    VARCHAR,
            CONSTRAINT ck_buchung_status CHECK (status IN ('geplant', 'gebucht')),
            CONSTRAINT ck_buchung_quelle CHECK (quelle IN ('manuell', 'import', 'haushaltsbuch', 'wiederkehrend')),
            CONSTRAINT uq_buchung_konto_hash UNIQUE (konto_id, import_hash)
        )
    """)
    op.execute("""
        INSERT INTO buchungen_new
            (id, konto_id, datum, betrag, empfaenger, empfaenger_id, kategorie_id,
             projekt_id, notiz, status, quelle, wiederkehrend_id, verwendungszweck,
             import_hash, import_verwendungszweck, import_empfaenger, import_iban,
             erstellt_von, erstellt_am, gegenbuchung_id, ist_transfer,
             verknuepft_mit_id, verknuepfung_typ)
        SELECT
            id, konto_id, datum, betrag, empfaenger, empfaenger_id, kategorie_id,
            projekt_id, notiz,
            COALESCE(status, 'gebucht'),
            COALESCE(quelle, 'manuell'),
            wiederkehrend_id, verwendungszweck,
            import_hash, import_verwendungszweck, import_empfaenger, import_iban,
            erstellt_von, erstellt_am, gegenbuchung_id, COALESCE(ist_transfer, 0),
            verknuepft_mit_id, verknuepfung_typ
        FROM buchungen
    """)
    op.execute("DROP TABLE buchungen")
    op.execute("ALTER TABLE buchungen_new RENAME TO buchungen")


def downgrade() -> None:
    # Zurück zur globalen import_hash-Unique (nur wenn keine Kollisionen vorhanden)
    op.execute("""
        CREATE TABLE buchungen_old (
            id                  INTEGER PRIMARY KEY,
            konto_id            INTEGER REFERENCES konten(id) ON DELETE CASCADE,
            datum               VARCHAR NOT NULL,
            betrag              FLOAT   NOT NULL,
            empfaenger          VARCHAR,
            empfaenger_id       INTEGER REFERENCES empfaenger(id) ON DELETE SET NULL,
            kategorie_id        INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            projekt_id          INTEGER REFERENCES projekte(id) ON DELETE SET NULL,
            notiz               TEXT,
            status              VARCHAR NOT NULL DEFAULT 'gebucht',
            quelle              VARCHAR NOT NULL DEFAULT 'manuell',
            wiederkehrend_id    INTEGER REFERENCES wiederkehrende_buchungen(id) ON DELETE SET NULL,
            verwendungszweck    TEXT,
            import_hash         VARCHAR UNIQUE,
            import_verwendungszweck TEXT,
            import_empfaenger   VARCHAR,
            import_iban         VARCHAR,
            erstellt_von        INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            erstellt_am         DATETIME NOT NULL,
            gegenbuchung_id     INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
            ist_transfer        BOOLEAN NOT NULL DEFAULT 0,
            verknuepft_mit_id   INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
            verknuepfung_typ    VARCHAR,
            CONSTRAINT ck_buchung_status CHECK (status IN ('geplant', 'gebucht')),
            CONSTRAINT ck_buchung_quelle CHECK (quelle IN ('manuell', 'import', 'haushaltsbuch', 'wiederkehrend'))
        )
    """)
    op.execute("INSERT INTO buchungen_old SELECT * FROM buchungen")
    op.execute("DROP TABLE buchungen")
    op.execute("ALTER TABLE buchungen_old RENAME TO buchungen")
