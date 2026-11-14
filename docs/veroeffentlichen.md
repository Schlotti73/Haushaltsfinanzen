# Veröffentlichen: wie der Stand ins öffentliche Repository kommt

## Warum es zwei Repositories gibt

Die Entwicklung läuft in einem privaten Repository. Dessen Historie lässt sich
nicht veröffentlichen: in Testdateien, Screenshots und Commit-Texten stecken
Jahre echter Haushaltsdaten – Adressen, Zählernummern, Kontobewegungen. Eine
Historie nachträglich zu säubern hilft nicht zuverlässig, weil GitHub den Stand
zusammengeführter Pull Requests behält.

Das öffentliche Repository beginnt deshalb mit einem **elternlosen** Commit. Es
hat mit dem privaten keinen gemeinsamen Vorfahren, und das ist Absicht: so kann
die alte Historie gar nicht erst mitwandern.

| | |
|---|---|
| Entwicklung, volle Historie | privat, hier |
| Quelltext | `Schlotti73/Haushaltsfinanzen` |
| Release-Pakete | `Schlotti73/Haushaltsfinanz-Releases` |

## Der Weg

Ein `git push public main` wäre zurückgewiesen (keine gemeinsame Basis), ein
erzwungener Push hätte die ganze Vorgeschichte mitgenommen. Veröffentlicht wird
darum nicht der Commit, sondern sein **Baum**: er wird an die Spitze des
öffentlichen Zweiges gehängt, und nur dieser eine neue Commit geht hinüber.
Drüben steht danach exakt der Dateibestand von hier – ohne einen einzigen
Commit, der hier je gemacht wurde.

```powershell
.\scripts\prod\veroeffentlichen.ps1 -Trockenlauf
.\scripts\prod\veroeffentlichen.ps1 -Nachricht "Texterkennung im Image"
```

[`scripts/prod/veroeffentlichen.ps1`](../scripts/prod/veroeffentlichen.ps1)

| Aufruf | Wirkung |
|---|---|
| `-Trockenlauf` | alles prüfen und zeigen, nichts pushen |
| `-Nachricht "…"` | Commit-Text, sonst wird danach gefragt |
| `-Unsauber` | Änderungen im Arbeitsverzeichnis zulassen |
| `-Trotzdem` | Funde der Inhaltsprüfung übergehen |
| `-Absender "Name <adresse>"` | anderer Absender für den Commit |
| `-Repo`, `-Remote`, `-Zweig` | Ziel abweichend vom Standard |

Das Skript bricht ab, wenn das Arbeitsverzeichnis nicht sauber ist. Das ist
hier wichtiger als anderswo: gepusht wird der Baum des letzten **Commits**,
nicht der Dateien auf der Platte. Ohne diesen Abbruch hielte man eine Änderung
für veröffentlicht, die man nur gespeichert hat.

Ist der Baum drüben schon derselbe, endet das Skript ohne Commit – ein zweiter
Aufruf erzeugt also keinen Leerlauf-Commit.

## Der Absender

Autor und Committer stehen bei GitHub offen in jedem Commit – an einer Stelle,
die keine Dateiprüfung je zu sehen bekommt, weil sie nicht im Baum liegt. Die
Git-Identität dieses Rechners trägt eine private Mailadresse; sie gehört dort
nicht hin.

Das Skript setzt deshalb für den einen Commit, den es baut, einen eigenen
Absender: die `noreply`-Adresse des GitHub-Kontos. Der Commit wird dem Konto
genauso zugeordnet, nur ohne die Adresse zu nennen. Danach stellt es die
Identität dieses Rechners wieder her – alles andere würde sonst unter dem
falschen Absender committen. Abweichend über `-Absender "Name <adresse>"`.

## Die Inhaltsprüfung

Jede Veröffentlichung ist endgültig: was einmal auf GitHub lag, steckt in
Forks, Caches und Suchmaschinen. Vor dem Push durchsucht das Skript deshalb den
**ganzen Baum**, nicht nur die Änderung – ein Personenbezug, der vor drei
Commits hereingerutscht ist, fiele sonst nie auf.

Fest eingebaut sind zwei allgemeine Muster: ein konkreter Pfad im
Benutzerprofil (`C:\Users\<name>` als Platzhalter in der Doku zählt nicht) und
E-Mail-Adressen. Die `LICENSE` ist ausgenommen, denn dort steht der
Rechteinhaber absichtlich mit Klarnamen.

Alles Weitere – Namen, Anschrift, Vertrags- und Zählernummern – steht in
`config\veroeffentlichung-tabu.txt`, eine Zeile je regulärer Ausdruck. Die
Datei liegt unter `config\` und ist damit `.gitignore`t: eine Liste echter
Daten darf selbst nicht veröffentlicht werden. Fehlt sie, sagt das Skript das
deutlich und prüft nur die allgemeinen Muster.

Ein Treffer bricht ab. Sind wirklich alle Treffer harmlos, wiederholt
`-Trotzdem` den Lauf – bewusst als eigener, zweiter Aufruf.

## Was das Skript nicht prüft

- **Bilder.** Screenshots unter `docs/demo/bilder/` werden nicht gelesen. Neue
  Screenshots immer selbst ansehen, bevor sie hineinwandern.
- **Binärdateien** allgemein (`git grep -I` überspringt sie).
- **Die Release-Pakete.** Das ZIP entsteht aus
  [`create_prod_zip.ps1`](../scripts/prod/create_prod_zip.ps1) und geht an ein
  anderes Repository; es enthält das gebaute Frontend, in dem Texte aus dem
  Quelltext nochmals stecken.

## Seiten

GitHub Pages liefert `docs/` aus dem öffentlichen Repository aus. Der Rundgang
liegt damit unter
<https://schlotti73.github.io/Haushaltsfinanzen/demo/> und baut sich nach jeder
Veröffentlichung neu, bei der sich `docs/` geändert hat. `docs/.nojekyll`
schaltet den Jekyll-Bau ab: hier liegen fertige Dateien, und die
Markdown-Dokumente sollen Dokumente bleiben.
