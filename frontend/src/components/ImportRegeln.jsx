import { useEffect, useRef, useState } from 'react'
import { importRegelApi, kategorienApi } from '../api'
import { useHilfe } from '../HilfeContext'
import ImportRegelForm from './ImportRegelForm'

const woerterAlsText = (liste) => (liste || []).join(', ')

function fmtBetrag(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

export default function ImportRegeln() {
  const { openHilfe } = useHilfe()
  const [regeln, setRegeln] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [laden, setLaden] = useState(true)
  const [meldung, setMeldung] = useState(null)      // {typ, text}
  const [form, setForm] = useState(null)            // null = Formular zu

  const [vorschlaege, setVorschlaege] = useState(null)
  const [lauf, setLauf] = useState(null)            // Bestandslauf-Vorschau
  const [ueberschreiben, setUeberschreiben] = useState(false)
  const [laufLaeuft, setLaufLaeuft] = useState(false)
  const dateiRef = useRef()

  const lade = () => {
    setLaden(true)
    Promise.all([importRegelApi.list(), kategorienApi.flat()])
      .then(([r, k]) => { setRegeln(r.data); setKategorien(k.data) })
      .catch(() => setMeldung({ typ: 'fehler', text: 'Regeln konnten nicht geladen werden.' }))
      .finally(() => setLaden(false))
  }
  useEffect(lade, [])

  const oeffneNeu = (vorgabe = {}) => {
    setForm(vorgabe)
    setMeldung(null)
  }

  const oeffneBearbeiten = (r) => {
    setForm({
      id: r.id, name: r.name, stufe: r.stufe,
      schluesselwoerter: woerterAlsText(r.schluesselwoerter),
      iban_muster: r.iban_muster || '',
      empfaenger_id: r.empfaenger_id ?? '',
      kategorie_id: r.kategorie_id ?? null,
      notiz_text: r.notiz_text || '',
      aktiv: r.aktiv, notiz: r.notiz || '',
    })
    setMeldung(null)
  }

  const nachSpeichern = (regel) => {
    setForm(null)
    lade()
    setMeldung({ typ: 'ok', text: `Regel „${regel.name}“ gespeichert.` })
  }

  const onLoeschen = async (r) => {
    if (!window.confirm(`Regel „${r.name}“ löschen?`)) return
    try {
      await importRegelApi.delete(r.id)
      if (form?.id === r.id) setForm(null)
      lade()
    } catch {
      setMeldung({ typ: 'fehler', text: 'Löschen fehlgeschlagen.' })
    }
  }

  const onToggleAktiv = async (r) => {
    try {
      await importRegelApi.update(r.id, { aktiv: !r.aktiv })
      setRegeln(prev => prev.map(x => x.id === r.id ? { ...x, aktiv: !x.aktiv } : x))
    } catch {
      setMeldung({ typ: 'fehler', text: 'Aktiv-Status konnte nicht geändert werden.' })
    }
  }

  const ladeVorschlaege = async () => {
    setMeldung(null)
    try {
      const r = await importRegelApi.vorschlaege()
      setVorschlaege(r.data)
    } catch {
      setMeldung({ typ: 'fehler', text: 'Vorschläge konnten nicht geladen werden.' })
    }
  }

  // Bestandslauf: erst Vorschau, erst danach schreiben.
  const starteLauf = async (anwenden) => {
    setLaufLaeuft(true); setMeldung(null)
    try {
      const r = await importRegelApi.bestandslauf({ ueberschreiben, anwenden })
      setLauf(r.data)
      if (anwenden) {
        setMeldung({ typ: 'ok', text: `${r.data.geaendert} Buchung(en) angepasst.` })
        setLauf(null)
      }
    } catch (err) {
      setMeldung({ typ: 'fehler', text: err.response?.data?.detail ?? 'Bestandslauf fehlgeschlagen.' })
    } finally {
      setLaufLaeuft(false)
    }
  }

  const onExport = async () => {
    try {
      const r = await importRegelApi.export()
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `import-regeln-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setMeldung({ typ: 'fehler', text: 'Export fehlgeschlagen.' })
    }
  }

  const onImportDatei = async (datei) => {
    if (!datei) return
    try {
      const daten = JSON.parse(await datei.text())
      const r = await importRegelApi.import(daten)
      lade()
      const kern = `${r.data.angelegt} neu, ${r.data.aktualisiert} aktualisiert.`
      setMeldung({
        typ: r.data.hinweise.length ? 'fehler' : 'ok',
        text: r.data.hinweise.length ? `${kern} ${r.data.hinweise.join(' · ')}` : kern,
      })
    } catch (err) {
      setMeldung({ typ: 'fehler', text: err.response?.data?.detail ?? 'Datei konnte nicht gelesen werden.' })
    } finally {
      if (dateiRef.current) dateiRef.current.value = ''
    }
  }

  const katName = (id) => kategorien.find(k => k.id === id)?.name ?? null

  if (laden) return <div className="text-sm text-gray-400">Lade Import-Regeln…</div>

  const anbieter = regeln.filter(r => r.stufe === 'anbieter')
  const haendler = regeln.filter(r => r.stufe === 'haendler')

  const RegelZeile = (r) => (
    <div key={r.id} className="flex items-center gap-3 border border-gray-100 rounded px-3 py-2 text-sm">
      <span className={`font-medium ${r.aktiv ? '' : 'text-gray-400 line-through'}`}>{r.name}</span>
      <span className="text-xs text-gray-400 flex-1 truncate">
        {r.schluesselwoerter.join(', ')}
        {r.iban_muster && <span className="ml-2 font-mono">{r.iban_muster}</span>}
      </span>
      {r.empfaenger_name && <span className="text-xs text-purple-600">→ {r.empfaenger_name}</span>}
      {r.kategorie_id && <span className="text-xs text-green-600">→ {katName(r.kategorie_id)}</span>}
      {r.stufe === 'haendler' && (
        <span className="text-xs text-amber-600">Notiz: {r.notiz_text || r.name}</span>
      )}
      {/* Aktiv ist ein Dauerzustand, kein Vorgang - dafuer der Schieber, wie bei
          den Kassenzettel-Mustern eine Karte weiter. Ein Knopf, dessen
          Beschriftung zwischen "Aktivieren" und "Deaktivieren" wechselt, laesst
          ausserdem offen, ob er den Zustand nennt oder das, was er tut. */}
      <label className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-500">
        <input type="checkbox" role="switch" checked={r.aktiv} onChange={() => onToggleAktiv(r)}
               className="schieber schieber-sm" />
        aktiv
      </label>
      <button type="button" className="btn-secondary btn-sm" onClick={() => oeffneBearbeiten(r)}>
        Bearbeiten
      </button>
      {/* Symbol statt Wort: die Liste wird lang, und ein Dutzend ausgeschriebener
          roter Knoepfe untereinander ist eine Spalte Rot. Dieselbe Machart wie
          das Loeschen in Buchungen, Empfaenger und Geschaeften. */}
      <button type="button" className="btn-danger btn-icon-sm" title="Löschen" aria-label="Löschen"
              onClick={() => onLoeschen(r)}>
        ×
      </button>
    </div>
  )

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold text-gray-700">Import-Regeln (Bankrohtext → definierte Werte)</h3>
          <button type="button" onClick={() => openHilfe('import-regeln')} className="text-xs text-blue-600 hover:underline shrink-0">Hilfe dazu</button>
        </div>
        <p className="text-xs text-gray-400 mt-1">
          Zwei Stufen: <strong>Anbieter</strong> erkennt den Zahlungsdienstleister im Bankempfänger
          und setzt den Empfänger. <strong>Händler</strong> erkennt den Laden in Bankempfänger und
          Verwendungszweck und setzt Notiz und Kategorie – und den Empfänger, wenn Stufe 1 keinen
          gefunden hat. Geschäfte wirken automatisch als Händler-Regel mit; eine eigene Regel hat
          Vorrang. Der Bankrohtext bleibt in jedem Fall an der Buchung erhalten.
        </p>
      </div>

      {meldung && (
        <div className={`rounded px-3 py-2 text-sm ${meldung.typ === 'ok'
          ? 'bg-green-50 text-green-800 border border-green-200'
          : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {meldung.text}
        </div>
      )}

      {/* Regel-Listen */}
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-600">Stufe 1 – Anbieter</h4>
            <button type="button" className="btn-secondary btn-sm"
                    onClick={() => oeffneNeu({ stufe: 'anbieter' })}>
              + Anbieter-Regel
            </button>
          </div>
          {anbieter.length ? anbieter.map(RegelZeile)
            : <p className="text-sm text-gray-400">Noch keine Anbieter-Regel.</p>}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-600">Stufe 2 – Händler</h4>
            <button type="button" className="btn-secondary btn-sm"
                    onClick={() => oeffneNeu({ stufe: 'haendler' })}>
              + Händler-Regel
            </button>
          </div>
          {haendler.length ? haendler.map(RegelZeile)
            : <p className="text-sm text-gray-400">Noch keine Händler-Regel – Geschäfte greifen trotzdem.</p>}
        </div>
      </div>

      {/* Formular – geteilt mit der Inline-Anlage aus der Buchungsmaske */}
      {form && (
        <ImportRegelForm
          initial={form}
          onGespeichert={nachSpeichern}
          onAbbrechen={() => setForm(null)}
        />
      )}

      {/* Vorschläge aus dem Bestand */}
      <div className="border-t border-gray-100 pt-4 space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-gray-600">Vorschläge aus dem Bestand</h4>
          <button type="button" className="btn-secondary btn-sm" onClick={ladeVorschlaege}>
            Bankempfänger auswerten
          </button>
        </div>
        <p className="text-xs text-gray-400">
          Häufige Bankempfänger, für die noch keine Regel greift.
        </p>
        {vorschlaege && (vorschlaege.length ? (
          <div className="space-y-1">
            {vorschlaege.map(v => (
              <div key={v.schluesselwort} className="flex items-center gap-3 text-sm px-3 py-1.5 bg-gray-50 rounded">
                <span className="w-12 text-right text-gray-500">{v.anzahl}×</span>
                <span className="font-medium">{v.schluesselwort}</span>
                <span className="text-xs text-gray-400 flex-1 truncate">{v.beispiel}</span>
                <button type="button" className="btn-secondary btn-sm"
                        onClick={() => oeffneNeu({ name: v.schluesselwort, schluesselwoerter: v.schluesselwort })}>
                  Regel anlegen
                </button>
              </div>
            ))}
          </div>
        ) : <p className="text-sm text-gray-400">Alles abgedeckt.</p>)}
      </div>

      {/* Bestandslauf */}
      <div className="border-t border-gray-100 pt-4 space-y-2">
        <h4 className="text-sm font-semibold text-gray-600">Regeln auf bestehende Buchungen anwenden</h4>
        <p className="text-xs text-gray-400">
          Betrifft nur importierte Buchungen. Handkorrekturen bleiben stehen: leere Felder werden
          gefüllt, der Empfänger nur ersetzt, solange er noch dem Bankrohtext entspricht.
        </p>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" className="haken" checked={ueberschreiben}
                 onChange={e => { setUeberschreiben(e.target.checked); setLauf(null) }} />
          Bereits gefüllte Felder überschreiben
        </label>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary" disabled={laufLaeuft}
                  onClick={() => starteLauf(false)}>
            {laufLaeuft ? 'Prüfe…' : 'Vorschau'}
          </button>
          {lauf && lauf.betroffen > 0 && (
            <button type="button" className="btn-primary" disabled={laufLaeuft}
                    onClick={() => starteLauf(true)}>
              {lauf.betroffen} Buchung(en) anpassen
            </button>
          )}
        </div>

        {lauf && (
          <div className="space-y-1">
            <p className="text-sm text-gray-600">
              {lauf.geprueft} importierte Buchungen geprüft, {lauf.betroffen} würden sich ändern.
            </p>
            <div className="max-h-64 overflow-y-auto space-y-1">
              {lauf.zeilen.map(z => (
                <div key={z.buchung_id} className="text-xs bg-gray-50 rounded px-3 py-1.5">
                  <div className="flex gap-3">
                    <span className="text-gray-500">{z.datum}</span>
                    <span className="w-20 text-right">{fmtBetrag(z.betrag)}</span>
                    <span className="text-blue-600">{z.regel_hinweis}</span>
                  </div>
                  <div className="text-gray-400 truncate">{z.bank_empfaenger}</div>
                  <div className="text-gray-600">
                    {z.alt_empfaenger !== z.neu_empfaenger && <span className="mr-3">Empfänger → {z.neu_empfaenger}</span>}
                    {z.alt_kategorie_id !== z.neu_kategorie_id && <span className="mr-3">Kategorie → {katName(z.neu_kategorie_id)}</span>}
                    {z.alt_notiz !== z.neu_notiz && <span className="mr-3">Notiz → {z.neu_notiz}</span>}
                    {z.alt_empfaenger_id !== z.neu_empfaenger_id && (
                      <span className="text-purple-600">Verknüpfung gesetzt</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Export / Import */}
      <div className="border-t border-gray-100 pt-4 space-y-2">
        <h4 className="text-sm font-semibold text-gray-600">Regeln sichern</h4>
        <p className="text-xs text-gray-400">
          Die Regeln liegen in der aktiven Datenbank. Spielst du ein Backup von vor dieser Funktion
          zurück, ist die Liste leer – ein Export davor bringt sie zurück. Empfänger und Kategorien
          werden über den Namen aufgelöst; was in der Zieldatenbank fehlt, bleibt leer.
        </p>
        <div className="flex gap-2 items-center">
          <button type="button" className="btn-secondary" onClick={onExport}>Exportieren</button>
          <input ref={dateiRef} type="file" accept="application/json" className="text-xs"
                 onChange={e => onImportDatei(e.target.files?.[0])} />
        </div>
      </div>
    </div>
  )
}
