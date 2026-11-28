import { HilfeFlow, HilfeKasten, HilfeSchritt, HilfeVerzweigung } from '../components/HilfeDiagramm'

function ErsteSchritte() {
  return (
    <>
      <p>
        Kurzer Überblick über die Module und eine sinnvolle Reihenfolge zum Einrichten – muss nicht
        starr befolgt werden, hilft aber beim ersten Einstieg.
      </p>
      <ol className="list-decimal list-inside space-y-1.5">
        <li><span className="font-medium">Kategorien</span> – der Baum, nach dem später alles ausgewertet wird.</li>
        <li><span className="font-medium">Konten</span> – Girokonto, Sparkonto, ggf. Darlehen anlegen.</li>
        <li>
          <span className="font-medium">Buchungen erfassen</span> – manuell, per Kassenzettel-Foto
          (<span className="font-medium">Haushaltsbuch</span>) oder per <span className="font-medium">Kontoauszug-Import</span>
          eines Kontoauszugs.
        </li>
        <li><span className="font-medium">Geschäfte &amp; Empfänger</span> – verbessert den automatischen Abgleich zwischen Beleg und Kontobuchung.</li>
        <li>
          <span className="font-medium">Verträge, Gebäude, Fahrzeuge</span> – eigene Bereiche für laufende
          Verpflichtungen und für Kostenstellen. Sie führen keine zweite Buchhaltung: ihre Kosten kommen
          aus den Buchungen, über die Kategorien, die dort hinterlegt sind.
        </li>
        <li>
          <span className="font-medium">Statistik, Liquidität, Projekte</span> – Auswertungen, sobald genug Buchungen
          vorhanden sind. Für die Liquiditätsvorschau zusätzlich <span className="font-medium">wiederkehrende
          Vorlagen</span> anlegen (siehe unten).
        </li>
      </ol>
      <HilfeFlow>
        <HilfeKasten titel="Zuerst" wert="Kategorien" />
        <HilfeSchritt titel="Dann" wert="Konten" />
        <HilfeVerzweigung
          label="Erfassen"
          optionen={[
            { label: 'manuell', schritte: [{ titel: 'Beleg/Konto', wert: 'Buchungen' }] },
            { label: 'Kassenzettel-Foto', schritte: [{ titel: 'Beleg', wert: 'Haushaltsbuch' }] },
            { label: 'Kontoauszug-PDF', schritte: [{ titel: 'Auszug', wert: 'Kontoauszug-Import' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Alle drei Erfassungswege münden im selben Buchungsbestand – <span className="font-medium">Statistik</span>,{' '}
        <span className="font-medium">Liquidität</span> und <span className="font-medium">Projekte</span> werten ihn
        anschließend aus. Die <span className="font-medium">Geschäft/Empfänger-Verknüpfung</span> (siehe unten)
        verbessert dabei, wie sicher Belege und Kontobuchungen einander zugeordnet werden.
      </p>
    </>
  )
}

function Haushaltsbuch() {
  return (
    <>
      <p>
        Beim Erfassen eines Kassenzettel-Fotos kannst du einzelne Artikel auf Kategorien aufteilen –
        etwa Lebensmittel und Haushaltswaren getrennt, obwohl beides auf demselben Beleg steht.
      </p>
      <p>
        Was du nicht einzeln aufteilst (den <span className="font-medium">Rest</span> der Belegsumme),
        fällt automatisch auf die <span className="font-medium">Standard-Kategorie</span> des gewählten
        Geschäfts. Kein manuelles Nacherfassen nötig, wenn der Rest ohnehin in diese Kategorie gehört.
      </p>
      <p>
        Voraussetzung: Das Geschäft braucht eine hinterlegte Standard-Kategorie (unter „Geschäfte"
        einstellbar). Fehlt sie, bleibt der Rest der ursprünglichen Buchungskategorie zugeordnet und
        es erscheint ein Hinweis statt der automatischen Zuordnung.
      </p>
      <p>
        Wird der Beleg per Texterkennung (OCR) erfasst, durchläuft das Foto mehrere Schritte, bevor
        einzelne Preiszeilen daraus werden:
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Foto" wert="Kassenzettel" />
        <HilfeSchritt label="Vorverarbeitung" titel="Bild" wert="Zuschnitt, Kontrast" />
        <HilfeSchritt label="OCR" titel="Text" wert="Rohtext" />
        <HilfeVerzweigung
          label="Dispatcher"
          optionen={[
            { label: 'Geschäft erkannt', schritte: [{ titel: 'Muster', wert: 'automat. Preiszeilen', ton: 'gruen' }] },
            { label: 'kein Muster', schritte: [{ titel: 'Fallback', wert: 'generischer Parser', ton: 'grau' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Die App zeigt zusätzlich eine kurze Qualitäts-Info und einen Link zum verarbeiteten
        Vorschaubild, damit du prüfen kannst, ob die Erkennung sauber war.
      </p>
    </>
  )
}

function EmpfaengerLink() {
  return (
    <>
      <p>
        Ein <span className="font-medium">Geschäft</span> ist der Laden auf dem Kassenzettel,
        ein <span className="font-medium">Empfänger</span> das Gegenkonto auf dem Kontoauszug.
        Der Empfänger-Link verbindet beides, damit der Abgleich einen Beleg sicher der richtigen
        Bankbuchung zuordnet.
      </p>

      <HilfeFlow>
        <HilfeKasten titel="Kassenzettel" wert="Markt Müller" />
        <HilfeSchritt label="Link" titel="Kontoauszug" wert="MARKT MUELLER DANKT" ton="blau" />
        <HilfeSchritt titel="Abgleich" wert="sicherer Treffer" ton="gruen" />
      </HilfeFlow>

      <p>
        <span className="font-medium text-gray-700">Wann setzen?</span> Bei Läden mit eigenem
        Bank-Gegenkonto – also allem, was per Karte oder Lastschrift direkt abgebucht wird.
        Ohne Link matcht der Abgleich nur über Namensähnlichkeit.
      </p>

      <div className="border-t pt-2.5 space-y-1.5">
        <p>
          <span className="font-medium text-gray-700">Sonderfall PayPal &amp; Klarna:</span> Dort steht
          auf dem Auszug immer derselbe Empfänger – egal ob Pizza Primo oder Streamflix. Ein Link auf
          „PayPal" kann die Läden also <span className="font-medium">nicht</span> unterscheiden.
        </p>
        <HilfeFlow>
          <HilfeKasten titel="Kassenzettel" wert="Pizza Primo" />
          <HilfeSchritt label="Zweck" titel="Verwendungszweck" wert="… PIZZA PRIMO 12345 …" ton="blau" />
          <HilfeSchritt titel="Abgleich" wert="Treffer" ton="gruen" />
        </HilfeFlow>
        <p>
          Solche Einkäufe erkennt der Abgleich stattdessen am <span className="font-medium">Geschäftsnamen
          im Verwendungszweck</span>. Dafür den Namen genauso schreiben wie auf dem Auszug
          (mindestens 3 Zeichen) – den Empfänger-Link lässt du dann auf „keine".
        </p>
      </div>
    </>
  )
}

function PdfImport() {
  return (
    <>
      <p>
        Kontoauszüge von Postbank, ING und Sparkasse kannst du als PDF hochladen – die App erkennt
        automatisch die Bank und liest die enthaltenen Buchungen aus, bevor du sie übernimmst.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Upload" wert="Kontoauszug-PDF" />
        <HilfeVerzweigung
          label="Dispatcher"
          optionen={[
            { label: 'Postbank / ING / Sparkasse', schritte: [{ titel: 'Muster erkannt', wert: 'Bank-Parser', ton: 'gruen' }] },
            { label: 'unbekanntes Format', schritte: [{ titel: 'Fallback', wert: 'generic.py', ton: 'grau' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        In beiden Fällen landen die erkannten Buchungen anschließend zur Prüfung im Import-Bereich,
        bevor du sie übernimmst. Für jede Bank gibt es ein <span className="font-medium">Muster</span>
        {' '}(verwaltet unter „Einstellungen"), das beschreibt, woran die App das PDF erkennt und wie sie
        die Felder ausliest. Neue Bankformate lassen sich meist über ein neues Muster statt über
        zusätzlichen Programmcode abdecken.
      </p>
      <p>
        Bei PayPal, Klarna &amp; Co. steht auf dem Auszug oft nur der Zahlungsdienstleister, nicht der
        eigentliche Laden. Der Abgleich versucht deshalb zusätzlich, den Geschäftsnamen direkt im
        Verwendungszweck zu finden (siehe „Geschäfte &amp; Empfänger-Verknüpfung" oben).
      </p>
      <p>
        Sparkonten-Transfers und der Amazon-CSV-Abgleich laufen über denselben Import-Bereich wie der
        Kontoauszug-Import.
      </p>
      <p>
        Damit aus dem Bankrohtext beim Import gleich ein sauberer Empfänger, eine Kategorie und eine
        Notiz werden, gibt es die <span className="font-medium">Import-Regeln</span> – siehe eigenen
        Abschnitt weiter unten. Nicht zu verwechseln mit den Kontoauszug-Mustern hier: die erkennen
        die <em>Bank</em>, die Regeln normalisieren den <em>Text einer Buchung</em>.
      </p>
      <p>
        <span className="font-medium">Archiv:</span> Jedes PDF, aus dem du tatsächlich importierst,
        wird aufbewahrt – auch dann, wenn der Lauf nur Duplikate enthielt. Unter dem
        Upload-Formular stehen die gespeicherten Auszüge des gewählten Kontos mit Zeitraum, Bank
        und Zeilenzahl; ein Klick auf den Dateinamen zeigt das PDF direkt in der App. Lädst du
        dieselbe Datei erneut hoch, entsteht kein zweiter Eintrag. Die Liste ist nach Jahren
        gruppiert – nach dem Zeitraum des Auszugs, nicht nach dem Importdatum; ein Klick auf die
        Jahreszahl klappt das Jahr zu oder wieder auf.
      </p>
      <p>
        Die Auszüge liegen im Ordner <span className="font-mono text-xs">kontoauszuege/</span> und
        sind im Backup enthalten – eine Wiederherstellung bringt sie zusammen mit der Datenbank
        zurück. <span className="font-medium">Löschen</span> entfernt nur das Archiv: die
        importierten Buchungen bleiben erhalten und verlieren lediglich den Verweis auf den Auszug,
        aus dem sie stammen.
      </p>
    </>
  )
}

function ImportRegeln() {
  return (
    <>
      <p>
        Auf dem Kontoauszug steht selten das, was du später lesen willst. Aus
        „Paypal Europe S.A.R.L. Et Cie S.C.A . Getranke Nord Selbststand Iger" sollen
        Empfänger „PayPal", Kategorie „Lebensmittel" und Notiz „Getränke Nord" werden. Genau das machen die
        Import-Regeln, verwaltet unter „Einstellungen".
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Kontoauszug" wert="Bankrohtext" />
        <HilfeSchritt label="Stufe 1" titel="Anbieter" wert="Empfänger = PayPal" ton="blau" />
        <HilfeVerzweigung
          label="Stufe 2"
          optionen={[
            { label: 'Händler erkannt', schritte: [{ titel: 'Notiz + Kategorie', wert: 'Getränke Nord · Lebensmittel', ton: 'gruen' }] },
            { label: 'kein Treffer', schritte: [{ titel: 'Felder', wert: 'bleiben leer', ton: 'grau' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        <span className="font-medium">Stufe 1 (Anbieter)</span> sucht den Zahlungsdienstleister nur
        im Empfängerfeld der Bank – wahlweise über Schlüsselwörter oder über dessen feste IBAN, die
        der stabilste Treffer überhaupt ist. Sie setzt den Empfänger.
      </p>
      <p>
        <span className="font-medium">Stufe 2 (Händler)</span> sucht den eigentlichen Laden in
        Empfängerfeld <em>und</em> Verwendungszweck und setzt Notiz und Kategorie – und den
        Empfänger, falls Stufe 1 keinen gefunden hat (etwa bei einer Lastschrift direkt vom Laden).
        Deine <span className="font-medium">Geschäfte</span> wirken hier automatisch mit, du musst
        sie nicht doppelt pflegen; eine eigene Regel hat aber Vorrang.
      </p>
      <p>
        Den Empfänger setzt Stufe 2 allerdings nur, wenn ihr Schlüsselwort im
        <span className="font-medium"> Empfängerfeld der Bank</span> stand – nicht, wenn es bloß im
        Verwendungszweck vorkam. Sonst würde eine Überweisung von einer Person, die im
        Verwendungszweck „Streamflix" erwähnt, plötzlich Streamflix als Empfänger tragen. Notiz und
        Kategorie greifen dagegen auch bei einem Fund im Verwendungszweck – genau dafür ist Stufe 2
        bei PayPal &amp; Co. da.
      </p>
      <p>
        Treffen mehrere Regeln, gewinnt das längste Schlüsselwort. Bei der Kategorie gewinnt immer
        Stufe 2, denn der Laden ist die genauere Information – „Lebensmittel" sagt mehr als der
        Zahlweg. Beim Empfänger gewinnt umgekehrt Stufe 1.
      </p>
      <p>
        Groß-/Kleinschreibung, Punkte und Umlaute spielen beim Vergleich keine Rolle: „Getränke Nord"
        trifft auch „GETRANKE NORD.", und ein gepflegtes „Getränke Nord" trifft die im PDF übliche
        Schreibweise „Getranke Nord". Der Treffer muss aber ein ganzes Wort sein, damit kurze Namen nicht zufällig
        in längeren Wörtern anschlagen. Der Bankrohtext bleibt immer an der Buchung erhalten und
        steht in der blauen Box im Bearbeiten-Dialog – dort legst du mit einem Klick auch direkt eine
        Regel an, wahlweise aus dem markierten Textstück.
      </p>
      <p>
        <span className="font-medium">Bestehende Buchungen</span> lassen sich nachträglich
        nachziehen: Der Bestandslauf zeigt zuerst eine Vorschau, betrifft nur importierte Buchungen
        und lässt Handkorrekturen stehen – leere Felder werden gefüllt, der Empfänger nur ersetzt,
        solange er noch dem Bankrohtext entspricht. Wer wirklich alles überschreiben will, setzt
        dafür ein Häkchen.
      </p>
      <p>
        Das Notizfeld einer Buchung hat eine <span className="font-medium">Auswahlliste</span> aus
        den definierten Händlernamen und den bereits vergebenen Notizen. Freier Text bleibt
        jederzeit möglich.
      </p>
      <p>
        Die Regeln liegen in der aktiven Datenbank und werden mitgesichert. Spielst du ein Backup von
        vor dieser Funktion zurück, ist die Liste leer – dafür gibt es Export und Import als Datei.
        Empfänger und Kategorien werden dabei über den Namen zugeordnet; was in der Zieldatenbank
        fehlt, bleibt leer und wird gemeldet.
      </p>
    </>
  )
}

function ImportAbgleich() {
  return (
    <>
      <p>
        Jede Zeile aus dem Kontoauszug-PDF wird beim Import gegen die vorhandenen Buchungen des
        Kontos geprüft, bevor du sie auswählst. Vier Einstufungen sind möglich:
      </p>
      <HilfeFlow>
        <HilfeKasten titel="PDF-Zeile" wert="Kontoauszug" />
        <HilfeVerzweigung
          label="Einstufung"
          optionen={[
            { label: 'gleicher Hash', schritte: [{ titel: 'Dublette', wert: 'gesperrt', ton: 'grau' }] },
            { label: 'Betrag exakt, ±1 Tag', schritte: [{ titel: 'Verdacht', wert: 'nicht vorausgewählt', ton: 'gelb' }] },
            { label: 'in Toleranz', schritte: [{ titel: 'Ähnlich', wert: 'bleibt vorausgewählt', ton: 'blau' }] },
            { label: 'kein Treffer', schritte: [{ titel: 'Neu', wert: 'vorausgewählt', ton: 'gruen' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        <span className="font-medium">Dublette</span> heißt: identischer Fingerabdruck
        (<span className="font-medium">Hash</span> aus Datum, Betrag und Bankrohtext) wie eine schon
        vorhandene Buchung. Die Zeile ist gesperrt, ein Import würde sie exakt verdoppeln.
      </p>
      <p>
        <span className="font-medium">Verdacht</span> ist die schärfere der beiden weichen Prüfungen
        und <span className="font-medium">fest verdrahtet</span>, nicht einstellbar: Betrag exakt
        gleich und Datum höchstens einen Tag auseinander. Die Zeile bleibt importierbar, ist aber
        nicht vorausgewählt – du musst bewusst ein Häkchen setzen, wenn es doch zwei getrennte
        Buchungen sein sollen.
      </p>
      <p>
        <span className="font-medium">Ähnlich</span> nutzt die unter „Einstellungen" einstellbare
        Toleranz für Betrag und Tage. Anders als bei Verdacht ist das nur ein Hinweis – die Zeile
        bleibt vorausgewählt, denn die Toleranz ist bewusst weiter gefasst und würde sonst zu viele
        echte Neuzugänge aus der Vorauswahl werfen.
      </p>
      <p>
        Beim Betragsvergleich zählt zusätzlich das Vorzeichen: Ohne diese Prüfung läge eine Ausgabe
        von −2&nbsp;€ nur 4&nbsp;€ von einer Einnahme über +2&nbsp;€ entfernt und würde als Treffer
        durchgehen.
      </p>
      <p>
        Statt eine Zeile neu zu importieren, kannst du sie stattdessen mit einer bereits
        vorhandenen Buchung <span className="font-medium">verknüpfen</span> – etwa einer geplanten
        Buchung aus einer wiederkehrenden Vorlage (siehe „Wiederkehrend → Liquiditätsvorschau"
        unten). Die Verknüpfung überträgt Datum und Verwendungszweck vom Kontoauszug und setzt den
        Status von „geplant" auf „gebucht".
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Geplante Buchung" wert="Status geplant" />
        <HilfeSchritt label="Treffer wählen" titel="Verknüpfen" wert="Datum = Bankdatum" ton="blau" />
        <HilfeSchritt titel="Ergebnis" wert="Status gebucht" ton="gruen" />
      </HilfeFlow>
      <p>
        <span className="font-medium">CSV ist die Quelle, das PDF das Archiv.</span> Beim
        CSV-Import bestätigst du den Zeitraum des Auszugs. Lädst du später ein PDF hoch, dessen
        Zeilen in diesen Zeitraum fallen, sind sie <span className="font-medium">gesperrt</span>:
        sie lassen sich nur mit der vorhandenen Buchung verknüpfen oder überspringen, nicht
        importieren. Die CSV liefert zur selben Zahlung mehr Felder (IBAN, Umsatzart,
        Mandatsreferenz) und ist deshalb die bessere Quelle; das PDF bleibt nützlich – als Archiv
        mit lesbarer Tabelle und als Nachweis hinter der Buchung.
      </p>
      <p>
        Gesperrt ist eine Zeile aber nur, wenn es zu ihr auch eine{' '}
        <span className="font-medium">Gegenbuchung</span> gibt. Fehlt die, kann nichts doppelt
        gezählt werden und die Zeile bleibt importierbar – so füllt sich die Lücke, wenn der
        CSV-Export der Bank abgeschnitten war (90-Tage-Grenze, aktiver Filter). Zeilen, die zusammen
        eine vorhandene Sammelbuchung ergeben, gelten als gedeckt: einzeln trifft keine den Betrag,
        zusammen schon.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          label="PDF-Zeile im CSV-Zeitraum"
          optionen={[
            { label: 'Gegenbuchung da', schritte: [{ titel: 'gesperrt', wert: 'nur verknüpfen', ton: 'gelb' }] },
            { label: 'keine Gegenbuchung', schritte: [{ titel: 'frei', wert: 'importierbar', ton: 'gruen' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Der Zeitraum steht in der Liste „Gespeicherte Kontoauszüge" und ist dort über das
        Stift-Symbol änderbar, zusammen mit dem Format. Beim Altbestand ist beides geraten – der
        Zeitraum aus dem ersten und letzten Buchungsdatum (und damit eher zu eng), das Format aus
        der Dateiendung. Ein Auszug ohne erkanntes Format deckt nichts ab und sperrt nichts.
      </p>
      <p>
        Nur die Toleranz für „Ähnlich" ist einstellbar – unter „Einstellungen" als Betrags- und
        Datumstoleranz. Die Schwelle für „Verdacht" ist im Code fest hinterlegt und dort nicht zu
        finden.
      </p>
    </>
  )
}

function WiederkehrendLiquiditaet() {
  return (
    <>
      <p>
        Eine wiederkehrende Vorlage (Empfänger, Betrag, Konto, Kategorie, Rhythmus, Start- und
        optionales Enddatum) legt fest, was regelmäßig anfällt – etwa „Miete −500&nbsp;€ monatlich".
        Der Schalter <span className="font-medium">Aktiv</span> steuert, ob aus ihr überhaupt
        generiert wird; eine deaktivierte Vorlage bleibt erhalten, erzeugt aber nichts.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Vorlage" wert="Miete, −500 €/Monat" />
        <HilfeSchritt label="Generierung" titel="Buchungen" wert="Status geplant" ton="blau" />
        <HilfeSchritt titel="Liquidität" wert="Vorschau-Kurve" ton="gruen" />
      </HilfeFlow>
      <p>
        Die Generierung läuft nicht automatisch und auch nicht auf der Wiederkehrend-Seite selbst,
        sondern über die Schaltflächen „Geplante Buchungen prüfen" / „Buchungen erzeugen" auf der{' '}
        <span className="font-medium">Liquiditätsseite</span>. Deren Zeitraum- und Kontofilter
        bestimmt dabei zweierlei zugleich: wie weit die Kurve reicht <em>und</em> wie weit generiert
        wird.
      </p>
      <p>
        Generiert werden ausschließlich Termine <span className="font-medium">ab heute</span> – ein
        Startdatum in der Vergangenheit erzeugt nichts rückwirkend. Ein zweiter Klick auf „Buchungen
        erzeugen" legt auch keine Dubletten an: geprüft wird gegen den ursprünglichen Termin der
        Vorlage, nicht gegen das Buchungsdatum, das ein späterer PDF-Abgleich verschoben haben kann
        (siehe „Abgleich beim Import" oben).
      </p>
      <p>
        Die Kurve setzt sich aus zwei getrennten Quellen zusammen: Der Startpunkt „heute" ist
        Kontostartsaldo plus alle bereits <span className="font-medium">gebuchten</span> Buchungen,
        der weitere Verlauf addiert ausschließlich Buchungen mit Status{' '}
        <span className="font-medium">geplant</span> ab heute. Ohne Generierung bleibt die Kurve
        deshalb leer.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          optionen={[
            { label: 'Status geplant', schritte: [{ titel: 'Wirkung', wert: 'zählt in der Kurve', ton: 'blau' }] },
            { label: 'Termin vorbei', schritte: [{ titel: 'überfällig', wert: 'zählt nirgends', ton: 'gelb' }] },
            { label: 'Status gebucht', schritte: [{ titel: 'Wirkung', wert: 'steckt im Saldo', ton: 'gruen' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Wird eine geplante Buchung später per Kontoauszug-Import einer echten Kontobuchung zugeordnet,
        wechselt sie von „geplant" auf „gebucht" – sie wandert damit aus der Vorschau in den Saldo,
        ohne doppelt gezählt zu werden.
      </p>
      <p>
        „Alle Girokonten zusammen" berücksichtigt nur Konten vom <span className="font-medium">Typ
        Giro</span> – Sparkonten und Darlehen fließen dort nicht ein.
      </p>
    </>
  )
}

function KontenDarlehen() {
  return (
    <>
      <p>
        Ein Konto vom Typ „Darlehen" kann direkt mit Annuitäten-Parametern hinterlegt werden:
        Darlehensbetrag, Zinssatz, monatliche Rate, Tilgungsbeginn sowie optional Tag der
        Vollauszahlung und Zinsbindungszeitraum in Jahren.
      </p>
      <p>
        Die <span className="font-medium">Hochrechnung</span> berechnet daraus Restschuld-Verlauf,
        Laufzeit und Gesamtzinsen automatisch – es muss kein Tilgungsplan gepflegt werden.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Rate" wert="monatlich" />
        <HilfeSchritt label="− Zinsanteil" titel="Tilgungsanteil" wert="Restschuld sinkt" />
        <HilfeSchritt label="− Sondertilgung" titel="Hochrechnung" wert="Laufzeit, Gesamtzinsen" ton="gruen" />
      </HilfeFlow>
      <p>
        <span className="font-medium">Sondertilgungen</span> (beliebig viele, mit Datum, Betrag und
        Notiz) trägst du in der Darlehens-Detailansicht ein; ein Schalter steuert, ob sie in die
        Hochrechnung einfließen.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          optionen={[
            { label: 'Rate > Zins', schritte: [{ titel: 'Ergebnis', wert: 'Restschuld sinkt', ton: 'gruen' }] },
            { label: 'Rate ≤ Zins', schritte: [{ titel: 'Warnung', wert: 'nie getilgt', ton: 'gelb' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Ist die Rate niedriger als die anfallenden Zinsen, wird das Darlehen nie getilgt – die App
        zeigt dazu eine Warnung, statt sich in einer endlosen Berechnung zu verlieren.
      </p>
      <p>
        Ist ein Zinsbindungszeitraum hinterlegt, markiert eine gestrichelte senkrechte Linie im
        Chart das Jahr des Zinsbindungsendes (Vollauszahlung bzw. ersatzweise erste Buchung + Jahre),
        daneben steht die dann erwartete Restschuld – zum Vergleich auch für die
        Was-wäre-wenn-Simulation, sobald eine berechnet wurde.
      </p>
      <p className="font-medium">Endfälliges Darlehen (Zwischenfinanzierung)</p>
      <p>
        Über das Feld „Art" lässt sich ein Darlehenskonto auf <span className="font-medium">endfällig</span>{' '}
        umstellen. Dort gibt es weder Rate noch Tilgung: gezahlt werden nur Zinsen, die gesamte Schuld
        wird zum Laufzeitende in einer Summe abgelöst. Statt Anfangstilgung, Rate und Tilgungsbeginn
        pflegst du Kreditlinie, Zinssatz und die Laufzeit in Jahren; der Laufzeitbeginn ist der Tag des
        ersten Abrufs (erste Buchung) oder das manuell gesetzte Datum.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Abrufe" wert="Tranchen" />
        <HilfeSchritt label="× Zinssatz / 12" titel="Zins pro Monat" wert="keine Tilgung" />
        <HilfeSchritt label="zum Laufzeitende" titel="Ablösung" wert="in einer Summe" ton="gelb" />
      </HilfeFlow>
      <p>
        Der Zinsplan rechnet bis heute mit dem tatsächlichen Saldoverlauf (die Linie wird in Tranchen
        abgerufen) und schreibt danach den heutigen Stand bis zur Fälligkeit fort. Die Zinsen sind damit
        <span className="font-medium"> rechnerisch</span> – die Zahlungen laufen über das Girokonto und
        sind auf dem Darlehenskonto nicht sichtbar, Abweichungen zur Bankabrechnung sind möglich.
        Rückführungen erfasst du als normale Buchung auf dem Konto; Sondertilgungen und die
        Was-wäre-wenn-Simulation entfallen deshalb bei dieser Art.
      </p>
      <p>
        Projekte können auf ein Darlehenskonto verweisen (siehe „Projekte – Plan vs. Ist" unten), ohne
        die Zins- und Tilgungslogik zu duplizieren.
      </p>
    </>
  )
}

function ProjektePlanIst() {
  return (
    <>
      <p>
        Zu jedem Projekt lassen sich geplante Ausgabeposten anlegen, z. B. „Dach" oder „Fenster".
      </p>
      <p>
        Tatsächliche Buchungen kannst du mit einem Posten verknüpfen; die App vergleicht anschließend
        geplant vs. tatsächlich ausgegeben („Ist") und zeigt die Abweichung je Posten.
      </p>
      <p>
        Ein Posten kann mit mehreren Buchungen verknüpft sein, eine einzelne Buchung aber immer nur
        mit einem Posten gleichzeitig.
      </p>
      <p>
        Das Verknüpfen ist immer ein manueller Schritt: Ein Posten zieht sich keine Buchungen von
        selbst. Das Feld „Darlehenskonto" am Posten setzt lediglich die Konto-Vorauswahl im
        Verknüpfen-Dialog, damit du die passenden Buchungen schneller findest – zugerechnet werden
        sie erst, wenn du sie dort verknüpfst.
      </p>
      <p>
        Ein Projekt vom Typ „Darlehen" kann zusätzlich ein Darlehenskonto hinterlegt haben. Das ist
        ein reiner Merkposten zur Dokumentation und beeinflusst weder Plan vs. Ist noch die
        Buchungssuche. Die Zins- und Tilgungslogik lebt am Konto selbst – siehe „Konten – Darlehen"
        oben.
      </p>
    </>
  )
}

function Dashboard() {
  return (
    <>
      <p>
        Das Dashboard ist die Startseite: oben das <span className="font-medium">Vermögen</span> –
        die Summe aller Konten abzüglich der Restschulden. Sachwerte wie Immobilien sind nicht
        erfasst und fehlen dort bewusst.
      </p>
      <p>
        Darunter stehen die Konten in Gruppen (Girokonten, Sparkonten, Depots, Darlehen &amp;
        Kredite). Der Saldo eines Kontos ist Startsaldo plus alle{' '}
        <span className="font-medium">gebuchten</span> Buchungen – geplante zählen hier nicht mit,
        die stecken in der Liquiditätsvorschau (siehe „Wiederkehrend → Liquiditätsvorschau").
      </p>
      <p>
        <span className="font-medium text-gray-700">Erinnerungen:</span> Die Karte wird bei jedem
        Aufruf neu aus den vorhandenen Daten berechnet und nichts davon gespeichert. Eine Erinnerung
        verschwindet also genau dann, wenn ihre Ursache weg ist – dafür lässt sich ein einzelner
        Posten nicht zurückstellen. Abschalten kannst du nur eine ganze{' '}
        <span className="font-medium">Art</span> (unter „Einstellungen", je Datenbank): Konten ohne
        Kontoauszug-Import, wiederkehrende Buchungen ohne genug Vorlauf, überfällige geplante
        Buchungen und fehlende Jahresablesungen.
      </p>
      <p>
        Jede Erinnerung nennt nur eine Anzahl und verweist auf die Seite, auf der sich die Sache
        erledigen lässt – die Einzelheiten stehen dort, damit die Karte nicht mit jedem vergessenen
        Posten wächst.
      </p>
    </>
  )
}

function Buchungen() {
  return (
    <>
      <p>
        Die Buchungsliste ist der gemeinsame Bestand aller Erfassungswege – manuell, Kassenzettel
        oder Kontoauszug-Import. Über Suche, Konto, Kategorie, Status und Zeitraum schränkst du ein;
        die Suche greift auf Empfänger und Notiz.
      </p>
      <p>
        <span className="font-medium">Status:</span> „gebucht" wirkt im Kontosaldo, „geplant" nur in
        der Liquiditätsvorschau. Beim Import kannst du eine PDF-Zeile mit einer geplanten Buchung
        verknüpfen, die dadurch auf „gebucht" wechselt (siehe „Abgleich beim Import").
      </p>
      <p>
        <span className="font-medium">Überfällig</span> ist ein dritter Zustand, aber kein dritter
        Status: In der Datenbank steht weiter „geplant" – überfällig heißt nur, dass der Termin vor
        heute liegt. Der Schieber wird dann gelb und das Wort wechselt; ein Klick setzt die Buchung
        wie immer auf „gebucht". Über den Statusfilter „Überfällig" bekommst du genau diese Zeilen;
        dorthin verweist auch die Erinnerung auf dem Dashboard.
      </p>
      <p>
        Entweder ist die Zahlung tatsächlich gelaufen und nur nicht abgeglichen, oder die Vorlage
        dahinter ist tot. Überfällige Buchungen zählen deshalb nirgends mit: nicht im Kontosaldo,
        nicht in der Liquiditätskurve und auch nicht in der Monats- und Jahresübersicht.
      </p>
      <p>
        <span className="font-medium">Mehrfach bearbeiten:</span> Zeilen auswählen und für alle
        zusammen Kategorie, Empfänger oder Status setzen – gedacht für die Nacharbeit nach einem
        Import.
      </p>
      <p>
        <span className="font-medium">Transfer</span> ist die Umbuchung zwischen eigenen Konten. Du
        verknüpfst zwei vorhandene Buchungen oder lässt die Gegenbuchung direkt anlegen. Beide
        Buchungen gelten danach als Transfer und bleiben aus Statistik und Hochrechnung heraus –
        sonst würde ein Übertrag aufs Sparkonto als Ausgabe <em>und</em> Einnahme erscheinen und die
        Auswertung verfälschen. „Verknüpfung lösen" nimmt die Markierung an beiden Seiten zurück.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          label="Umbuchung"
          optionen={[
            { label: 'als Transfer verknüpft', schritte: [{ titel: 'Statistik', wert: 'zählt nicht', ton: 'gruen' }] },
            { label: 'nicht verknüpft', schritte: [{ titel: 'Statistik', wert: 'Ausgabe + Einnahme', ton: 'gelb' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Bei importierten Buchungen bleibt der <span className="font-medium">Bankrohtext</span> an der
        Buchung erhalten und steht in der blauen Box im Bearbeiten-Dialog. Von dort legst du mit
        einem Klick eine Import-Regel an – wahlweise aus einem markierten Textstück (siehe
        „Import-Regeln").
      </p>
    </>
  )
}

function Statistik() {
  return (
    <>
      <p>
        Die Statistik wertet den Buchungsbestand aus: Monats- und Jahresübersicht (Einnahmen,
        Ausgaben, Saldo), Ausgaben nach Kategorie und nach Gruppe, Soll/Ist-Vergleich, Hochrechnung,
        Sparkonten-Entwicklung und eine Beleg-Auswertung. Ein CSV-Export der Buchungen liegt
        daneben.
      </p>
      <p>
        <span className="font-medium">Welche Buchungen zählen</span>, hängt von der Auswertung ab –
        das erklärt die meisten Zahlen, die auf den ersten Blick nicht zusammenpassen:
      </p>
      <p>
        In Monats- und Jahresübersicht zählen geplante Buchungen mit, aber nur{' '}
        <span className="font-medium">ab heute</span>: ein künftiger Monat soll zeigen, was er
        kostet. Eine geplante Buchung, deren Termin vorbei ist, ist überfällig – das Geld ist nicht
        geflossen und sie ist nicht abgeglichen worden. Sie bleibt draußen, so wie sie auch im
        Kontosaldo und in der Liquiditätskurve draußen bleibt.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          label="Buchung"
          optionen={[
            { label: 'gebucht', schritte: [{ titel: 'überall', wert: 'zählt mit', ton: 'gruen' }] },
            { label: 'geplant ab heute', schritte: [{ titel: 'Monat/Jahr ja', wert: 'Soll/Ist nein', ton: 'blau' }] },
            { label: 'überfällig', schritte: [{ titel: 'nirgends', wert: 'zählt nie', ton: 'gelb' }] },
            { label: 'Transfer', schritte: [{ titel: 'nirgends', wert: 'zählt nie', ton: 'grau' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        <span className="font-medium">Soll/Ist-Vergleich:</span> Das Soll kommt aus der Planung je
        Kategorie und ist ein <span className="font-medium">Monatswert</span>, der für den
        Jahresvergleich mit zwölf multipliziert wird. Als Ist zählen nur gebuchte Buchungen des
        Jahres – geplante würden den Vergleich mit Zahlen füllen, die noch nicht passiert sind.
      </p>
      <p>
        <span className="font-medium">Hochrechnung (Ist vs. Prognose):</span> Bis heute die gebuchten
        Monatssummen, danach eine Prognose aus den wiederkehrenden Vorlagen bis Ende des Folgejahres.
        Die Prognose ist rein rechnerisch – es werden dafür keine geplanten Buchungen erzeugt, das
        passiert nur auf der Liquiditätsseite.
      </p>
      <p>
        <span className="font-medium">Belege:</span> Diese Auswertung kommt aus den Positionen der
        Haushaltsbuch-Belege, nicht aus den Kontobuchungen – damit sind auch Barbelege ohne
        Kontobuchung enthalten.
      </p>
      <p>
        <span className="font-medium">Sparkonten-Entwicklung</span> zeigt den Verlauf quartalsweise,
        weil Sparkonten selten bebucht werden und eine Monatskurve dort überwiegend aus Treppen
        besteht.
      </p>
    </>
  )
}

function Kategorien() {
  return (
    <>
      <p>
        Die Kategorien sind der Baum, nach dem alle Auswertungen laufen. Die Tiefe ist nicht
        begrenzt; in der Praxis sind drei Ebenen sinnvoll – Obergruppe, Kategorie, Detail.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Ebene 1" wert="Nebenkosten" />
        <HilfeSchritt titel="Ebene 2" wert="Musterweg 1" ton="blau" />
        <HilfeSchritt titel="Ebene 3" wert="Strom EG" ton="gruen" />
      </HilfeFlow>
      <p>
        Die dritte Ebene ist genau für solche Fälle da: Ein Zähler oder ein Vertrag bekommt eine
        eigene Kategorie, bleibt aber unter seiner Gruppe auswertbar. In Auswahllisten erscheint
        deshalb immer der volle Pfad.
      </p>
      <p>
        Die <span className="font-medium">Art</span> (Ausgabe, Einnahme, beides) steuert, wo eine
        Kategorie zur Auswahl steht. Jede Buchung trägt genau eine Kategorie; Auswertungen rollen
        die Beträge auf die Obergruppe auf.
      </p>
      <p>
        <span className="font-medium">Inaktiv statt löschen:</span> Eine inaktive Kategorie bleibt an
        den alten Buchungen hängen und verschwindet nur aus den Auswahllisten – die Geschichte bleibt
        damit auswertbar. Löschen passt nur, solange nichts darauf gebucht ist.
      </p>
      <p>
        Gebäude-Zähler verweisen auf eine Kategorie, um daraus ihre Kosten zu ziehen (siehe
        „Gebäude, Zähler &amp; Nebenkosten"), und Kassenzettel-Muster ordnen MwSt-Schlüssel auf
        Kategorien zu. Umbauen am Baum wirkt also auch dort – Pflegen ist Administratoren
        vorbehalten.
      </p>
    </>
  )
}

function Gebaeude() {
  return (
    <>
      <p>
        Zu einem Gebäude gehören Zähler (Strom, Wasser, Gas, Wärme …) mit Nummer, Seriennummer,
        Einheit und Richtung – <span className="font-medium">Bezug</span> oder{' '}
        <span className="font-medium">Einspeisung</span> bei einer PV-Anlage.
      </p>
      <p>
        Gespeichert werden immer nur <span className="font-medium">Zählerstände</span>, der Verbrauch
        wird daraus berechnet. Ein nachträglich korrigierter Stand kann deshalb nie zu einem
        widersprüchlichen Verbrauch führen.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Ablesung" wert="Zählerstand" />
        <HilfeSchritt label="Differenz" titel="Verbrauch" wert="berechnet" ton="blau" />
        <HilfeSchritt label="Kategorie am Zähler" titel="Kosten" wert="aus den Buchungen" ton="gruen" />
      </HilfeFlow>
      <p>
        <span className="font-medium">Kosten</span> kommen aus den Buchungen der Kategorie, die am
        Zähler oder am Gebäude hinterlegt ist. Es gibt keine zweite Buchführung daneben: was nicht
        gebucht ist, erscheint hier auch nicht.
      </p>
      <p>
        <span className="font-medium">Jahresablesung oder Zwischenablesung?</span> Nur die
        Jahresablesung geht in Jahresverbrauch, Diagramm und Kostenrechnung ein. Eine
        Zwischenablesung ist reine Information und verändert davon nichts. Das Abrechnungsjahr ist
        aus dem Datum vorbelegt, aber änderbar – für die Ablesung, die erst am 3. Januar gemacht
        wurde.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          label="Sonderfälle"
          optionen={[
            { label: 'Zählerwechsel', schritte: [{ titel: 'End- + Anfangsstand', wert: 'eine Reihe', ton: 'blau' }] },
            { label: 'Zwischenzähler', schritte: [{ titel: 'wird mitgemessen', wert: 'vom Hauptzähler ab', ton: 'blau' }] },
            { label: 'Einspeisung', schritte: [{ titel: 'verrechnet mit', wert: 'Bezugszähler, in Euro', ton: 'gruen' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Beim <span className="font-medium">Zählerwechsel</span> trägst du den Endstand des alten und
        den Anfangsstand des neuen Zählers ein; Tabelle und Diagramm zeigen die Kette danach als eine
        durchgehende Reihe.
      </p>
      <p>
        Ein <span className="font-medium">Zwischenzähler</span> („Zwischenzähler von") wird im
        Hauptzähler mitgemessen und von ihm abgezogen, damit der Verbrauch nicht doppelt zählt.
      </p>
      <p>
        Bei einer <span className="font-medium">Einspeisung</span> lässt sich der Zähler mit einem
        Bezugszähler verrechnen: Die Vergütung mindert die Stromkosten, statt als eigene Kostenart zu
        erscheinen. Verrechnet wird nur in Euro – bezogene und eingespeiste Kilowattstunden sind
        verschiedene Mengen zu verschiedenen Preisen und bleiben getrennt.
      </p>
      <p>
        Fehlt für ein Jahr eine Jahresablesung, erinnert das Dashboard daran (abschaltbar unter
        „Einstellungen").
      </p>
    </>
  )
}

function Empfaenger() {
  return (
    <>
      <p>
        Empfänger sind die Gegenseiten auf dem Kontoauszug – mit Name, IBAN und Notiz. Die Suche
        greift auf Name <em>und</em> IBAN.
      </p>
      <p>
        Die <span className="font-medium">IBAN</span> lohnt sich besonders: Für die Import-Regeln ist
        sie der stabilste Treffer überhaupt, weil sie sich nicht mit jeder Schreibweise im Rohtext
        ändert (siehe „Import-Regeln").
      </p>
      <p>
        <span className="font-medium">Zusammenführen:</span> Sind für dieselbe Gegenseite zwei
        Einträge entstanden – etwa einer aus dem Import und einer von Hand –, führst du sie zusammen.
        Die Buchungen des aufgegebenen Eintrags wandern auf den Ziel-Empfänger, danach wird er
        gelöscht. Das ist nicht umkehrbar, also vorher prüfen, welcher Eintrag bleiben soll.
      </p>
      <p>
        Wie Empfänger mit den <span className="font-medium">Geschäften</span> vom Kassenzettel
        zusammenhängen, steht unter „Geschäfte &amp; Empfänger-Verknüpfung".
      </p>
    </>
  )
}

function Benutzer() {
  return (
    <>
      <p>
        Die Benutzerverwaltung sehen nur <span className="font-medium">Administratoren</span>. Es gibt
        zwei Rollen: <span className="font-medium">Admin</span> darf alles, einschließlich Stammdaten,
        Einstellungen, Datenbanken und Benutzer; <span className="font-medium">Bearbeiter</span>{' '}
        erfasst und wertet aus.
      </p>
      <p>
        Ein <span className="font-medium">Passwort</span> setzt du zurück, indem du im
        Bearbeiten-Dialog ein neues einträgst – das alte wird nicht angezeigt und ist nicht
        auslesbar.
      </p>
      <p>
        <span className="font-medium">Inaktiv statt löschen:</span> Ein inaktiver Benutzer kann sich
        nicht mehr anmelden, bleibt aber als Urheber an seinen Daten erhalten.
      </p>
      <p>
        <span className="font-medium">Zwei-Faktor (MFA):</span> Jeder Benutzer kann für sich eine
        Authenticator-App hinterlegen und bekommt dazu Recovery-Codes. Aus dem Heimnetz wird kein
        Code verlangt, von außen schon – so bleibt die Anmeldung zu Hause bequem, ohne den Zugang
        von unterwegs offen zu lassen. Die Recovery-Codes gelten je einmal; wie viele noch offen
        sind, steht in der MFA-Ansicht.
      </p>
    </>
  )
}

function Einstellungen() {
  return (
    <>
      <p>Die Einstellungen sind Administratoren vorbehalten und in Abschnitte geteilt:</p>
      <ul className="list-disc list-inside space-y-1.5">
        <li><span className="font-medium">Darstellung</span> – hell oder dunkel.</li>
        <li>
          <span className="font-medium">Module ausblenden</span> – räumt die Navigation auf. Die
          Auswahl gilt nur in <em>diesem</em> Browser, nicht für andere Geräte oder Benutzer.
        </li>
        <li>
          <span className="font-medium">Dashboard</span> – welche Erinnerungs-Arten berechnet werden
          (je Datenbank, siehe „Dashboard").
        </li>
        <li>
          <span className="font-medium">Import-Abgleich</span> – Betrags- und Datumstoleranz für die
          Einstufung „Ähnlich". Die Schwelle für „Verdacht" ist fest und steht nicht hier (siehe
          „Abgleich beim Import").
        </li>
        <li>
          <span className="font-medium">Automatisches Backup</span> – Uhrzeit und Zielordner,
          darunter die vorhandenen Backups mit Datum und Größe zum Herunterladen oder
          Wiederherstellen.
        </li>
        <li>
          <span className="font-medium">Datenbanken</span> – mehrere Datenbestände nebeneinander
          (etwa der eigene und ein Testbestand), umschalten oder neu anlegen.
        </li>
        <li>
          <span className="font-medium">Muster und Regeln</span> – Kassenzettel-Muster samt
          MwSt-Zuordnung, Kontoauszug-Muster und Import-Regeln (siehe die eigenen Abschnitte).
        </li>
        <li>
          <span className="font-medium">Update</span> – ob eine neue Version vorliegt und woher die
          Pakete kommen.
        </li>
      </ul>
      <HilfeFlow>
        <HilfeVerzweigung
          label="Anderer Datenbestand"
          optionen={[
            { label: 'Datenbank wechseln', schritte: [{ titel: 'Wirkung', wert: 'beide Bestände bleiben', ton: 'blau' }] },
            { label: 'Backup wiederherstellen', schritte: [{ titel: 'Wirkung', wert: 'überschreibt den Bestand', ton: 'gelb' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Die beiden sind leicht zu verwechseln: Ein{' '}
        <span className="font-medium">Datenbankwechsel</span> lässt alle Bestände stehen und arbeitet
        nur in einem anderen weiter. Eine <span className="font-medium">Wiederherstellung</span>
        {' '}ersetzt den Inhalt des aktiven Bestands durch den Stand aus dem Backup – mit den Belegen,
        Kassenzettel-Bildern und Kontoauszügen, die im Paket liegen.
      </p>
      <p>
        Manche Einstellungen gehören zur Installation (Backup-Zielordner, Update-Herkunft), andere
        zur jeweiligen Datenbank (Erinnerungen, Toleranzen, Muster, Regeln) – ein Wechsel des
        Datenbestands bringt deshalb dessen eigene Muster und Regeln mit.
      </p>
    </>
  )
}

function Vertraege() {
  return (
    <>
      <p>
        Hier stehen die laufenden Verpflichtungen – Versicherungen, Strom, Mobilfunk, Abos – mit
        Laufzeit, Kündigungsfrist und stiller Verlängerung. Am Vertrag selbst steht{' '}
        <span className="font-medium">kein Betrag</span>: was er kosten soll, hängt als
        wiederkehrende Vorlage an ihm, was er gekostet hat, sind die Buchungen.
      </p>
      <p>
        Der <span className="font-medium">Kündigungstermin</span> wird bei jedem Aufruf gerechnet,
        nicht gespeichert. Ist er verstrichen und der Vertrag verlängert sich still, rückt er
        automatisch auf die nächste Laufzeit weiter.
      </p>
      <HilfeFlow>
        <HilfeKasten titel="Laufzeit bis" wert="31.12." />
        <HilfeSchritt label="minus Frist" titel="Kündigungstermin" wert="30.09." ton="blau" />
        <HilfeVerzweigung
          label="verstrichen?"
          optionen={[
            { label: 'mit Verlängerung', schritte: [{ titel: 'nächste Laufzeit', wert: 'neuer Termin', ton: 'gelb' }] },
            { label: 'ohne Verlängerung', schritte: [{ titel: 'läuft aus', wert: 'nichts zu kündigen', ton: 'grau' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        <span className="font-medium">Ohne Laufzeitende gibt es keinen Termin</span>, nur die Frist –
        der Vertrag ist jederzeit kündbar und nichts kann verfallen. Das ist der Normalfall bei Abos.
        Ein eingetragenes <span className="font-medium">Kündigungsdatum</span> schaltet den Termin
        ab: gekündigt ist gekündigt, auch wenn das Ende noch in der Zukunft liegt.
      </p>
      <p>
        Die Frist hat eine <span className="font-medium">Einheit</span> (Tage, Wochen, Monate).
        „Drei Monate vor dem 31.03." ist der 31.12. und kein 90-Tage-Stichtag.
      </p>

      <div className="border-t pt-2.5 space-y-1.5">
        <p>
          <span className="font-medium text-gray-700">Raten: Soll und Ist.</span> Eine Rate ist eine{' '}
          <span className="font-medium">wiederkehrende Vorlage</span>, die am Vertrag hängt – gern
          mehrere, etwa monatlicher Abschlag und Jahresabrechnung. <span className="font-medium">Soll</span>{' '}
          ist die Summe dieser Vorlagen aufs Jahr, <span className="font-medium">Ist</span> sind die
          echten Buchungen der letzten zwölf Monate.
        </p>
        <HilfeFlow>
          <HilfeKasten titel="Rate (Vorlage)" wert="Soll je Jahr" ton="blau" />
          <HilfeSchritt titel="Buchungen" wert="Ist, 12 Monate" ton="gruen" />
          <HilfeSchritt label="Abweichung" titel="Preis geändert" wert="Vorlage anpassen" ton="gelb" />
        </HilfeFlow>
        <p>
          Weicht beides auseinander, steht die Vorlage meist auf einem alten Preis. Geändert wird der
          Betrag <span className="font-medium">an der Vorlage</span> – rückwirkend wird dabei nichts
          umgeschrieben.
        </p>
      </div>

      <div className="border-t pt-2.5 space-y-1.5">
        <p>
          <span className="font-medium text-gray-700">Echte Zahlungen zuordnen.</span> Der Vertrag
          sammelt die Buchungen, die zu ihm gehören – auf zwei verschieden starken Wegen:
        </p>
        <HilfeFlow>
          <HilfeVerzweigung
            optionen={[
              { label: 'Mandatsreferenz', schritte: [{ titel: 'eindeutig', wert: 'ordnet still zu', ton: 'gruen' }] },
              { label: 'Empfänger, Betrag', schritte: [{ titel: 'Indiz', wert: 'fragt jedes Mal', ton: 'gelb' }] },
            ]}
          />
        </HilfeFlow>
        <p>
          Die <span className="font-medium">Mandatsreferenz</span> der Lastschrift ist pro Vertrag
          eindeutig; ist sie einmal gemerkt, ordnet schon der Import jede weitere Abbuchung
          selbstständig zu – auch rückwirkend für ältere Buchungen. Empfänger und Betrag sind nur
          ein Indiz und werden deshalb jedes Mal nachgefragt, ohne Vorauswahl. Der{' '}
          <span className="font-medium">Betrag</span> ist dabei Bestätigung, nie Bedingung: nach
          einer Preiserhöhung passt er nicht mehr, der Vertrag bleibt trotzdem zuordenbar.
        </p>
        <p>
          <span className="font-medium">PayPal und Klarna:</span> Dort läuft alles über ein einziges
          Mandat. Die Referenz lässt sich an solchen Buchungen bewusst <span className="font-medium">nicht</span>{' '}
          merken („Referenz nicht lernbar") – sonst bekäme jede künftige PayPal-Abbuchung denselben
          Vertrag. Die einzelne Zahlung kannst du trotzdem zuordnen.
        </p>
      </div>

      <p>
        Ein Vertrag kann einem <span className="font-medium">Fahrzeug</span> zugeordnet werden –
        Versicherung, Steuer, Leasing erscheinen dann dort bei den Kosten. Gepflegt wird er weiter
        hier.
      </p>
      <p>
        <span className="font-medium">Dokumente</span> (Police, Nachtrag, Preiserhöhung,
        Kündigungsschreiben) hängen direkt am Vertrag, mehrere je Vertrag.
      </p>
      <p>
        Rückt ein Kündigungstermin näher, erinnert das Dashboard daran; Vorlauf und Abschalten stehen
        unter „Einstellungen". Beim <span className="font-medium">Löschen</span> gehen die Dokumente
        mit, <span className="font-medium">Buchungen und Vorlagen bleiben</span> – sie verlieren nur
        ihre Verbindung zum Vertrag.
      </p>
    </>
  )
}

function Fahrzeuge() {
  return (
    <>
      <p>
        Ein Fahrzeug ist eine <span className="font-medium">Kostenstelle</span> wie ein Gebäude – nur
        mit einem einzigen Zähler: dem Kilometerstand. Gespeichert wird immer der{' '}
        <span className="font-medium">Stand</span>, nie die Fahrleistung; die ist die Differenz zweier
        Stände. Ein nachträglich korrigierter Stand kann so nie zu einer widersprüchlichen
        Fahrleistung führen.
      </p>
      <p>
        Stände kommen aus <span className="font-medium">drei Quellen</span>, und alle drei zählen
        gleich: ein Werkstattbesuch ist ebenso eine Ablesung wie der Zettel an der Zapfsäule.
      </p>
      <HilfeFlow>
        <HilfeVerzweigung
          optionen={[
            { label: 'Tankung', schritte: [{ titel: 'km-Stand', wert: 'eine Reihe', ton: 'blau' }] },
            { label: 'Ablesung', schritte: [{ titel: 'km-Stand', wert: 'z. B. 31.12.', ton: 'blau' }] },
            { label: 'erledigter Termin', schritte: [{ titel: 'km-Stand', wert: 'Werkstatt', ton: 'blau' }] },
          ]}
        />
      </HilfeFlow>
      <p>
        Für die Fahrleistung eines Jahres braucht es den letzten Stand des Vorjahres. Fehlt der{' '}
        <span className="font-medium">Jahresstand</span> zum 31.12., wird das Jahr zu kurz gerechnet –
        darum erinnert das Dashboard daran. Liegt der letzte Stand in den letzten 14 Dezembertagen,
        fehlt nichts Nennenswertes und es kommt keine Erinnerung.
      </p>

      <div className="border-t pt-2.5 space-y-1.5">
        <p>
          <span className="font-medium text-gray-700">Tankungen sind freiwillig.</span> Der Schalter
          steht in den Stammdaten; aus heißt kein Reiter, keine Mengen, kein Verbrauch. Fahrleistung
          und Kosten je Kilometer entstehen trotzdem, solange der Stand einmal im Jahr eingetragen
          wird.
        </p>
        <p>
          <span className="font-medium">Verbrauch nur zwischen zwei Volltankungen.</span> Erst bei
          vollem Tank ist bekannt, wie viel auf die gefahrenen Kilometer wirklich hineingegangen ist.
          Eine Teilbetankung bekommt deshalb keinen eigenen Wert – ihre Menge fließt in die nächste
          Volltankung ein.
        </p>
        <HilfeFlow>
          <HilfeKasten titel="voll" wert="Tankung" ton="gruen" />
          <HilfeSchritt label="Teiltankung" titel="Menge" wert="sammelt an" ton="grau" />
          <HilfeSchritt label="voll" titel="Verbrauch" wert="l/100 km" ton="gruen" />
        </HilfeFlow>
        <p>
          Beim Plug-in-Hybrid laufen <span className="font-medium">Liter und kWh getrennt</span>: zwei
          Verbräuche auf dieselbe Strecke, so werden sie auch angezeigt. Die Strecke wird nicht
          aufgeteilt, das ginge nicht ohne zu raten.
        </p>
      </div>

      <p>
        <span className="font-medium">Kosten</span> kommen aus den Buchungen der Kategorien, die am
        Fahrzeug als Kostenart hinterlegt sind – Kraftstoff, Werkstatt, Steuer, Versicherung. Eine
        Kategorie gehört immer nur <span className="font-medium">einer</span> Kostenstelle: ist
        „Kraftstoff" schon an einem anderen Fahrzeug, einem Gebäude oder einem Zähler hinterlegt,
        wird sie hier abgelehnt. Sonst zählte jede Tankstellenbuchung doppelt. Eine Erstattung bleibt
        eine negative Kostenposition und mindert das Jahr.
      </p>

      <div className="border-t pt-2.5 space-y-1.5">
        <p>
          <span className="font-medium text-gray-700">Termine</span> – HU, Ölwechsel, Zahnriemen,
          Reifenwechsel. Gespeichert wird nur das <span className="font-medium">Intervall</span>, in
          Monaten und/oder Kilometern. Gelten beide, ist fällig, was zuerst erreicht wird.
        </p>
        <HilfeFlow>
          <HilfeKasten titel="Intervall" wert="24 Monate / 30.000 km" />
          <HilfeSchritt label="ab letzter Durchführung" titel="fällig" wert="Datum oder km" ton="blau" />
          <HilfeSchritt label="km-Schnitt" titel="Prognose" wert="voraussichtl. Monat" ton="gelb" />
        </HilfeFlow>
        <p>
          Das Monatsintervall zählt ab der letzten Durchführung – ohne eine gibt es{' '}
          <span className="font-medium">kein Datum</span>. Das Kilometerintervall zählt ohne
          Durchführung <span className="font-medium">ab 0</span>: so trägst du absolute Ziele ein,
          „Zahnriemen alle 180.000 km" ist dann schlicht der Stand 180.000.
        </p>
        <p>
          Die <span className="font-medium">Prognose</span> rechnet den Kilometerrest gegen den
          Durchschnitt der letzten zwölf Monate. Aus weniger als zwei Ständen entsteht keine – das
          ist richtiger als eine erfundene.
        </p>
        <p>
          Erinnert wird mit <span className="font-medium">zwei Vorläufen</span>, Tagen und
          Kilometern, weil ein Termin zwei Maßstäbe hat (Vorgabe 60 Tage / 2.000 km, unter
          „Einstellungen").
        </p>
      </div>

      <p>
        <span className="font-medium">Verträge</span> – Versicherung, Steuer, Leasing – lassen sich
        dem Fahrzeug zuordnen und erscheinen hier mit Kündigungstermin und Jahresrate; gepflegt
        werden sie unter „Verträge". <span className="font-medium">Dokumente</span> wie
        Fahrzeugschein, HU-Bericht oder Werkstattrechnung hängen direkt am Fahrzeug.
      </p>
      <p>
        Beim <span className="font-medium">Löschen</span> gehen Stände, Tankungen, Termine und
        Dokumente mit. <span className="font-medium">Buchungen und Verträge bleiben</span> – sie
        gehören nicht dem Fahrzeug, es war nur ihre Kostenstelle.
      </p>
    </>
  )
}

export const HILFE_ABSCHNITTE = [
  // Gruppe "bereiche": ein Abschnitt je Menuepunkt.
  { id: 'dashboard', gruppe: 'bereiche', titel: 'Dashboard', Inhalt: Dashboard },
  { id: 'buchungen', gruppe: 'bereiche', titel: 'Buchungen', Inhalt: Buchungen },
  { id: 'haushaltsbuch', gruppe: 'bereiche', titel: 'Haushaltsbuch', Inhalt: Haushaltsbuch },
  { id: 'empfaenger-link', gruppe: 'bereiche', titel: 'Geschäfte & Empfänger-Verknüpfung', Inhalt: EmpfaengerLink },
  { id: 'statistik', gruppe: 'bereiche', titel: 'Statistik & Auswertungen', Inhalt: Statistik },
  { id: 'vertraege', gruppe: 'bereiche', titel: 'Verträge – Frist, Raten & Zuordnung', Inhalt: Vertraege },
  { id: 'pdf-import', gruppe: 'bereiche', titel: 'Kontoauszug-Import & Muster', Inhalt: PdfImport },
  { id: 'konten-darlehen', gruppe: 'bereiche', titel: 'Konten – Darlehen', Inhalt: KontenDarlehen },
  { id: 'kategorien', gruppe: 'bereiche', titel: 'Kategorien', Inhalt: Kategorien },
  { id: 'projekte-plan-ist', gruppe: 'bereiche', titel: 'Projekte – Plan vs. Ist', Inhalt: ProjektePlanIst },
  { id: 'gebaeude', gruppe: 'bereiche', titel: 'Gebäude, Zähler & Nebenkosten', Inhalt: Gebaeude },
  { id: 'fahrzeuge', gruppe: 'bereiche', titel: 'Fahrzeuge – Stände, Verbrauch & Termine', Inhalt: Fahrzeuge },
  { id: 'empfaenger', gruppe: 'bereiche', titel: 'Empfänger-Stammdaten', Inhalt: Empfaenger },
  { id: 'benutzer', gruppe: 'bereiche', titel: 'Benutzer & Anmeldung', Inhalt: Benutzer },
  { id: 'einstellungen', gruppe: 'bereiche', titel: 'Einstellungen', Inhalt: Einstellungen },

  // Gruppe "uebergreifend": Ketten und Regeln, die mehrere Seiten verbinden.
  { id: 'erste-schritte', gruppe: 'uebergreifend', titel: 'Erste Schritte', standardOffen: true, Inhalt: ErsteSchritte },
  { id: 'import-regeln', gruppe: 'uebergreifend', titel: 'Import-Regeln (Bankrohtext bereinigen)', Inhalt: ImportRegeln },
  { id: 'import-abgleich', gruppe: 'uebergreifend', titel: 'Abgleich beim Import – Dubletten & Treffer', Inhalt: ImportAbgleich },
  { id: 'wiederkehrend-liquiditaet', gruppe: 'uebergreifend', titel: 'Wiederkehrend → Liquiditätsvorschau', Inhalt: WiederkehrendLiquiditaet },
]

// Inhaltsverzeichnis der Gruppe "Bereiche", in Menuereihenfolge, damit jeder
// Menuepunkt auffindbar ist. Liquiditaet und Wiederkehrend zeigen bewusst auf
// denselben uebergreifenden Abschnitt: ihre Kette ist nur zusammen erklaerbar.
export const HILFE_BEREICHE = [
  { label: 'Dashboard', anker: 'dashboard' },
  { label: 'Buchungen', anker: 'buchungen' },
  { label: 'Haushaltsbuch', anker: 'haushaltsbuch' },
  { label: 'Geschäfte', anker: 'empfaenger-link' },
  { label: 'Statistik', anker: 'statistik' },
  { label: 'Liquidität', anker: 'wiederkehrend-liquiditaet' },
  { label: 'Wiederkehrend', anker: 'wiederkehrend-liquiditaet' },
  { label: 'Verträge', anker: 'vertraege' },
  { label: 'Kontoauszug-Import', anker: 'pdf-import' },
  { label: 'Konten', anker: 'konten-darlehen' },
  { label: 'Kategorien', anker: 'kategorien' },
  { label: 'Projekte', anker: 'projekte-plan-ist' },
  { label: 'Gebäude', anker: 'gebaeude' },
  { label: 'Fahrzeuge', anker: 'fahrzeuge' },
  { label: 'Empfänger', anker: 'empfaenger' },
  { label: 'Benutzer', anker: 'benutzer' },
  { label: 'Einstellungen', anker: 'einstellungen' },
]

// Route -> Hilfe-Anker fuer den Hilfe-Knopf im Rahmen. Eine Stelle, damit kein
// Bereich ohne Hilfe bleibt; '/' steht fuer das Dashboard.
export const HILFE_ROUTE_ANKER = {
  '/': 'dashboard',
  '/buchungen': 'buchungen',
  '/haushaltsbuch': 'haushaltsbuch',
  '/geschaefte': 'empfaenger-link',
  '/statistik': 'statistik',
  '/liquiditaet': 'wiederkehrend-liquiditaet',
  '/wiederkehrend': 'wiederkehrend-liquiditaet',
  '/vertraege': 'vertraege',
  '/import': 'pdf-import',
  '/konten': 'konten-darlehen',
  '/kategorien': 'kategorien',
  '/projekte': 'projekte-plan-ist',
  '/gebaeude': 'gebaeude',
  '/fahrzeuge': 'fahrzeuge',
  '/empfaenger': 'empfaenger',
  '/benutzer': 'benutzer',
  '/einstellungen': 'einstellungen',
}

export function ankerFuerPfad(pfad) {
  if (!pfad) return null
  if (HILFE_ROUTE_ANKER[pfad]) return HILFE_ROUTE_ANKER[pfad]
  // Unterseiten (z. B. /konten/7) auf ihren Bereich zurueckfuehren.
  const erstes = pfad.split('/').filter(Boolean)[0]
  return erstes ? HILFE_ROUTE_ANKER['/' + erstes] || null : null
}
