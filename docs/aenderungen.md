# Änderungen

Je Version ein Abschnitt. Dieser Text ist die Release-Beschreibung: `gh release
create --notes-file` lädt ihn hoch, und die Anwendung zeigt ihn unter
*Einstellungen → Programm-Update* an, sobald die Version verfügbar ist.

Er steht hier im Baum und nicht von Hand getippt im Release, weil sonst genau
der eine öffentliche Text des Projekts nie durch die Prüfung auf Personenbezug
liefe (`scripts\prod\veroeffentlichen.ps1` prüft den Baum, nicht das Release).
`create_prod_zip.ps1` schneidet beim Paketbau den Abschnitt der gebauten
Version heraus und nennt den Pfad der Datei, die `gh release create` erwartet.

Die Überschrift trägt die Versionsnummer, wie der Tag sie hat – `## v0.7.0 —
2026-11-30`. Steht die Nummer beim Schreiben noch nicht fest, bleibt
„unveröffentlicht" stehen – vor dem Paketbau muss sie dort stehen, sonst
findet das Skript den Abschnitt nicht.

Versionen bis v0.6.1 stehen als Releases im archivierten
[Paket-Repository](https://github.com/Schlotti73/Haushaltsfinanz-Releases/releases).

## v0.6.2 — 2026-11-28

**Downloads liegen jetzt beim Quelltext.** Windows-Paket und Container-Image
hängen ab dieser Fassung am öffentlichen Repository
[Haushaltsfinanzen](https://github.com/Schlotti73/Haushaltsfinanzen): das ZIP
als Release, das Image als Paket daneben. Das bisherige Paket-Repository ist
archiviert, seine alten Releases bleiben erreichbar.

- Die Update-Prüfung fragt das neue Repository. Eine Installation, die noch die
  alte Herkunft gespeichert hat, wird beim Lesen umgeschrieben – es ist nichts
  umzustellen.
- Neu: eine [Download-Seite](https://schlotti73.github.io/Haushaltsfinanzen/download/)
  mit Voraussetzungen, Installation und Update für beide Wege.
- Das Container-Image entsteht ab jetzt aus dem veröffentlichten Quellstand,
  nicht mehr aus dem privaten Entwicklungs-Repository. Am Image selbst ändert
  sich dadurch nichts: der veröffentlichte Baum ist eine wortgleiche Kopie.

**Kontoauszug-Import: Jahre im Archiv zuklappbar.** Das Archiv eines Kontos
sammelt pro Jahr zwölf Auszüge und mehr. Die Jahreszahl steht jetzt groß über
ihrem Block, daneben ein Pfeil, der das Jahr zuklappt. Gemerkt werden die
zugeklappten Jahre, nicht die aufgeklappten – ein Jahr, das durch einen Import
dazukommt, steht also nicht von sich aus zu.

Das Schema bleibt unverändert, ein Rollback ist verlustfrei.
