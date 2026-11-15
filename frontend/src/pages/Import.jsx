import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useHilfe } from '../HilfeContext'
import { haushaltsbuchApi, importPdfApi, kontenApi } from '../api'
import { auswaehlbareKonten } from '../kontoAuswahl'
import Modal from '../components/Modal'
import { useConfirm } from '../components/useConfirm'
import { EyeIcon } from '../components/icons'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

// Spiegelt _betrag_aehnlich im Backend (import_pdf.py): Beträge innerhalb der
// Toleranz, aber nur bei gleichem Vorzeichen.
function betragAehnlich(a, b, spanne) {
  if (!spanne) return false
  if ((a < 0) !== (b < 0)) return false
  return Math.abs(a - b) <= spanne
}

// Gruppiert das Archiv nach dem Jahr des Auszugs-Zeitraums, nicht nach dem
// Importzeitpunkt: ein im Januar hochgeladener Dezember-Auszug gehoert
// fachlich ins Vorjahr. Jahre absteigend, innerhalb absteigend nach Beginn
// des Zeitraums. Ein Auszug mit Zeitraum ueber die Jahresgrenze steht genau
// einmal in der Liste (im Jahr seines Beginns) - doppelt angezeigt waeren
// Zeilenzahl und Loeschen mehrdeutig.
const OHNE_ZEITRAUM = 'Ohne Zeitraum'

// zeitraum_von/bis sind min/max Buchungsdatum und bleiben bei 0 geparsten
// Zeilen leer (siehe ParseResult im Backend). Solche Auszuege bekommen eine
// eigene Gruppe am Ende, statt still nach Importdatum in ein Jahr zu rutschen,
// in das sie vielleicht nicht gehoeren.
function nachJahrGruppieren(auszuege) {
  const gruppen = new Map()
  for (const a of auszuege) {
    const jahr = a.zeitraum_von ? a.zeitraum_von.slice(0, 4) : OHNE_ZEITRAUM
    if (!gruppen.has(jahr)) gruppen.set(jahr, [])
    gruppen.get(jahr).push(a)
  }
  for (const liste of gruppen.values()) {
    liste.sort((x, y) =>
      (y.zeitraum_von || '').localeCompare(x.zeitraum_von || '')
      || (y.importiert_am || '').localeCompare(x.importiert_am || '')
      || y.id - x.id)
  }
  return [...gruppen.entries()]
    .sort(([a], [b]) => {
      if (a === OHNE_ZEITRAUM) return 1
      if (b === OHNE_ZEITRAUM) return -1
      return b.localeCompare(a)
    })
    .map(([jahr, liste]) => ({ jahr, liste }))
}

export default function Import() {
  const { openHilfe } = useHilfe()
  const [konten, setKonten] = useState([])
  const [kontoId, setKontoId] = useState('')
  const [datei, setDatei] = useState(null)
  const [vorschau, setVorschau] = useState(null)
  const [ausgewaehlt, setAusgewaehlt] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [ergebnis, setErgebnis] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [abgleichVorschlaege, setAbgleichVorschlaege] = useState([])
  const [verknuepfenLaden, setVerknuepfenLaden] = useState(null)
  const [expandiert, setExpandiert] = useState(new Set())
  const [gewaehlteTreffer, setGewaehlteTreffer] = useState({}) // import_hash → booking_id
  const [auffrischen, setAuffrischen] = useState(false)
  // Archiv der bereits importierten Auszuege zum gewaehlten Konto
  const [auszuege, setAuszuege] = useState([])
  const [auszugAnsicht, setAuszugAnsicht] = useState(null)
  const fileRef = useRef()
  const { confirm, dialog } = useConfirm()
  const auszugJahre = useMemo(() => nachJahrGruppieren(auszuege), [auszuege])

  useEffect(() => {
    kontenApi.list(false).then(r => setKonten(r.data))
  }, [])

  // Bewusst ohne useEffect auf kontoId: das Archiv haengt allein an der
  // Kontoauswahl, und die aendert sich nur durch einen Klick im Formular.
  const ladeAuszuege = (id) => {
    if (!id) { setAuszuege([]); return }
    importPdfApi.auszuege(+id).then(r => setAuszuege(r.data)).catch(() => setAuszuege([]))
  }

  const zeigeVorschau = async () => {
    if (!kontoId || !datei) return
    setLoading(true)
    setFehler(null)
    setVorschau(null)
    setErgebnis(null)
    setAusgewaehlt(new Set())
    try {
      const r = await importPdfApi.vorschau(+kontoId, datei)
      setVorschau(r.data)
      // Standardmäßig alle Nicht-Duplikate angehakt
      setAusgewaehlt(new Set(
        r.data.buchungen.filter(b => !b.duplikat && !b.duplikat_verdacht).map(b => b.import_hash)
      ))
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Fehler beim Parsen')
    } finally {
      setLoading(false)
    }
  }

  const commit = async () => {
    const hatTreffer = Object.keys(gewaehlteTreffer).length > 0
    const hatAuffrischen = auffrischen && (vorschau?.duplikate ?? 0) > 0
    if (!kontoId || !datei || (ausgewaehlt.size === 0 && !hatTreffer && !hatAuffrischen)) return
    setCommitting(true)
    setFehler(null)
    try {
      const r = await importPdfApi.commit(+kontoId, datei, [...ausgewaehlt], gewaehlteTreffer, auffrischen)
      setErgebnis(r.data)
      setAbgleichVorschlaege(r.data.abgleich_vorschlaege || [])
      setVorschau(null)
      setAusgewaehlt(new Set())
      setGewaehlteTreffer({})
      setAuffrischen(false)
      setDatei(null)
      if (fileRef.current) fileRef.current.value = ''
      // Der Commit hat das PDF archiviert (oder einen vorhandenen Eintrag
      // wiederverwendet) - Liste nachziehen.
      ladeAuszuege(kontoId)
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Fehler beim Import')
    } finally {
      setCommitting(false)
    }
  }

  const auszugLoeschen = async (a) => {
    const frage = a.anzahl_buchungen > 0
      ? `Auszug „${a.dateiname}“ aus dem Archiv löschen? Die importierten Buchungen bleiben erhalten, sie verlieren nur den Verweis auf diesen Auszug.`
      : `Auszug „${a.dateiname}“ aus dem Archiv löschen?`
    if (!await confirm(frage)) return
    await importPdfApi.auszugLoeschen(a.id)
    if (auszugAnsicht?.id === a.id) setAuszugAnsicht(null)
    ladeAuszuege(kontoId)
  }

  const toggleRow = (hash) => {
    setAusgewaehlt(prev => {
      const next = new Set(prev)
      next.has(hash) ? next.delete(hash) : next.add(hash)
      return next
    })
  }

  const toggleExpandiert = (hash, e) => {
    e.stopPropagation()
    setExpandiert(prev => {
      const next = new Set(prev)
      next.has(hash) ? next.delete(hash) : next.add(hash)
      return next
    })
  }

  const waehleNaheBuchung = (importHash, buchungId, e) => {
    e.stopPropagation()
    setGewaehlteTreffer(prev => {
      const istBereitsGewählt = prev[importHash] === buchungId
      const next = { ...prev }
      if (istBereitsGewählt) {
        delete next[importHash]
        // Auswahl aufheben → PDF-Eintrag wieder zum Import vormerken
        setAusgewaehlt(p => { const s = new Set(p); s.add(importHash); return s })
      } else {
        next[importHash] = buchungId
        // Treffer gewählt → PDF-Eintrag nicht importieren
        setAusgewaehlt(p => { const s = new Set(p); s.delete(importHash); return s })
      }
      return next
    })
  }

  const toggleAlle = () => {
    if (!vorschau) return
    const waehlbar = vorschau.buchungen.filter(b => !b.duplikat && !b.duplikat_verdacht).map(b => b.import_hash)
    const alleAn = waehlbar.every(h => ausgewaehlt.has(h))
    setAusgewaehlt(alleAn ? new Set() : new Set(waehlbar))
  }

  const autoTreffer = () => {
    if (!vorschau) return
    const neueGewählt = { ...gewaehlteTreffer }
    const neueAusgewaehlt = new Set(ausgewaehlt)
    let anzahl = 0
    for (const b of vorschau.buchungen) {
      if (b.duplikat) continue
      if (neueGewählt[b.import_hash]) continue
      const treffer = (b.nahe_buchungen ?? []).find(nb => nb.datum === b.datum && nb.betrag === b.betrag)
      if (treffer) {
        neueGewählt[b.import_hash] = treffer.id
        neueAusgewaehlt.delete(b.import_hash)
        anzahl++
      }
    }
    setGewaehlteTreffer(neueGewählt)
    setAusgewaehlt(neueAusgewaehlt)
    return anzahl
  }

  const resetErgebnisse = () => {
    setVorschau(null)
    setErgebnis(null)
    setFehler(null)
    setAusgewaehlt(new Set())
    setExpandiert(new Set())
    setGewaehlteTreffer({})
    setAuffrischen(false)
    setAbgleichVorschlaege([])
  }

  const verknuepfen = async (buchungId, eintragId) => {
    setVerknuepfenLaden(eintragId)
    try {
      await haushaltsbuchApi.verknuepfen(eintragId, buchungId)
      setAbgleichVorschlaege(prev =>
        prev
          .map(v => v.buchung_id === buchungId
            ? { ...v, kandidaten: v.kandidaten.filter(k => k.id !== eintragId) }
            : v)
          .filter(v => v.kandidaten.length > 0)
      )
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Fehler beim Verknüpfen')
    } finally {
      setVerknuepfenLaden(null)
    }
  }

  const reset = () => {
    resetErgebnisse()
    setDatei(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const waehlbar = vorschau ? vorschau.buchungen.filter(b => !b.duplikat && !b.duplikat_verdacht) : []
  const alleAn = waehlbar.length > 0 && waehlbar.every(b => ausgewaehlt.has(b.import_hash))
  const teilweiseAn = !alleAn && waehlbar.some(b => ausgewaehlt.has(b.import_hash))

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-xl font-bold">Kontoauszug importieren</h2>
        <button type="button" onClick={() => openHilfe('pdf-import')} className="text-sm text-blue-600 hover:underline">Hilfe dazu</button>
      </div>

      {/* Upload-Formular */}
      <div className="card space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="label">Konto*</label>
            <select className="input" value={kontoId} onChange={e => { setKontoId(e.target.value); resetErgebnisse(); ladeAuszuege(e.target.value) }}>
              <option value="">– wählen –</option>
              {auswaehlbareKonten(konten, kontoId).map(k => (
                <option key={k.id} value={k.id}>{k.name} ({k.bank || k.typ}){k.aktiv ? '' : ' – inaktiv'}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">PDF-Datei*</label>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf"
              className="input py-1.5"
              onChange={e => { setDatei(e.target.files[0] || null); resetErgebnisse() }}
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-primary"
            onClick={zeigeVorschau}
            disabled={!kontoId || !datei || loading}
          >
            {loading ? 'Analysiere…' : 'Vorschau anzeigen'}
          </button>
          {vorschau && (
            <button
              className="btn-primary bg-green-600 hover:bg-green-700"
              onClick={commit}
              disabled={committing || (
                ausgewaehlt.size === 0
                && Object.keys(gewaehlteTreffer).length === 0
                && !(auffrischen && vorschau.duplikate > 0)
              )}
            >
              {committing ? 'Importiert…' : [
                ausgewaehlt.size > 0 && `${ausgewaehlt.size} Buchungen importieren`,
                Object.keys(gewaehlteTreffer).length > 0 && `${Object.keys(gewaehlteTreffer).length} Treffer verknüpfen`,
                auffrischen && vorschau.duplikate > 0 && `${vorschau.duplikate} Duplikate auffrischen`,
              ].filter(Boolean).join(' · ') || 'Übernehmen'}
            </button>
          )}
        </div>
      </div>

      {/* Fehler */}
      {fehler && <div className="card border-red-200 bg-red-50 text-red-700 text-sm">{fehler}</div>}

      {/* Ergebnis */}
      {ergebnis && (
        <div className="card border-green-200 bg-green-50">
          <p className="text-green-800 font-medium">
            Import abgeschlossen: {ergebnis.importiert} neue Buchungen · {ergebnis.duplikate} Duplikate übersprungen
            {ergebnis.verknuepft > 0 && ` · ${ergebnis.verknuepft} Treffer verknüpft`}
            {ergebnis.gebucht_gesetzt > 0 && ` · ${ergebnis.gebucht_gesetzt} auf "gebucht" gesetzt`}
            {ergebnis.aufgefrischt > 0 && ` · ${ergebnis.aufgefrischt} Duplikate aufgefrischt`}
          </p>
        </div>
      )}

      {/* Abgleich-Vorschläge: importierte Buchungen <-> offene Haushaltsbuch-Einträge */}
      {abgleichVorschlaege.length > 0 && (
        <div className="card border-blue-200 bg-blue-50 space-y-3">
          <p className="text-blue-800 font-medium">
            {abgleichVorschlaege.length} importierte Buchung(en) passen evtl. zu offenen Haushaltsbuch-Einträgen
          </p>
          {abgleichVorschlaege.map(v => (
            <div key={v.buchung_id} className="space-y-1">
              <p className="text-sm text-gray-600">
                Buchung: <span className="font-medium">{v.buchung_empfaenger || '–'}</span> · {v.buchung_datum} · {fmt(v.buchung_betrag)}
              </p>
              <ul className="space-y-1">
                {v.kandidaten.map(k => (
                  <li key={k.id} className="flex items-center justify-between bg-white rounded px-3 py-1.5 text-sm">
                    <span>
                      {k.geschaeft?.name || 'Ohne Geschäft'} · {k.datum} · {fmt(-k.betrag_gesamt)}
                      {k.notiz && <span className="text-gray-400"> · {k.notiz}</span>}
                    </span>
                    <button
                      className="text-blue-600 hover:underline text-xs disabled:opacity-50"
                      disabled={verknuepfenLaden === k.id}
                      onClick={() => verknuepfen(v.buchung_id, k.id)}
                    >
                      {verknuepfenLaden === k.id ? 'Verknüpfe…' : 'Verknüpfen'}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* Vorschau-Tabelle */}
      {vorschau && (
        <div className="space-y-2">
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span>Bank: <strong>{vorschau.bank}</strong></span>
            {vorschau.konto_hinweis && <span>Konto: <span className="font-mono">{vorschau.konto_hinweis}</span></span>}
            <span className="text-green-700 font-medium">{ausgewaehlt.size} ausgewählt</span>
            <span className="text-gray-400">{vorschau.duplikate} Duplikate</span>
            {vorschau.verdaechtigt > 0 && <span className="text-orange-600">{vorschau.verdaechtigt} Verdacht</span>}
            {vorschau.aehnlich > 0 && <span className="text-amber-600">{vorschau.aehnlich} ähnlich</span>}
            <button type="button" onClick={() => openHilfe('import-abgleich')} className="text-xs text-blue-600 hover:underline">Was bedeutet das?</button>
            {waehlbar.length > 0 && (
              <button className="text-blue-600 hover:underline text-xs" onClick={toggleAlle}>
                {alleAn ? 'Alle abwählen' : 'Alle auswählen'}
              </button>
            )}
            {vorschau.buchungen.some(b => !b.duplikat && (b.nahe_buchungen ?? []).some(nb => nb.datum === b.datum && nb.betrag === b.betrag) && !gewaehlteTreffer[b.import_hash]) && (
              <button className="btn-secondary btn-sm h-9 text-purple-700" onClick={autoTreffer}>
                ⚡ Datum &amp; Betrag auto-verknüpfen
              </button>
            )}
            {vorschau.duplikate > 0 && (
              <label className="btn-secondary btn-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="haken"
                  checked={auffrischen}
                  onChange={e => setAuffrischen(e.target.checked)}
                />
                Duplikate mit PDF-Werten auffrischen
              </label>
            )}
          </div>

          <div className="card p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
                  <th className="px-3 py-2 w-8">
                    <input
                      type="checkbox"
                      checked={alleAn}
                      ref={el => { if (el) el.indeterminate = teilweiseAn }}
                      onChange={toggleAlle}
                      className="haken"
                      title="Alle auswählen / abwählen"
                    />
                  </th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Datum</th>
                  <th className="px-3 py-2">Empfänger</th>
                  <th className="px-3 py-2">Verwendung</th>
                  <th className="px-3 py-2 text-right">Betrag</th>
                  <th className="px-3 py-2">Kategorie (Match)</th>
                </tr>
              </thead>
              <tbody>
                {vorschau.buchungen.map((b, i) => {
                  const istAusgewaehlt = ausgewaehlt.has(b.import_hash)
                  const gewählterTreffer = gewaehlteTreffer[b.import_hash] ?? null
                  const istWaehlbar = !b.duplikat && !gewählterTreffer
                  const hatTreffer = b.duplikat ? !!b.vorhandene_buchung : (b.nahe_buchungen?.length > 0)
                  const istExpandiert = expandiert.has(b.import_hash)
                  return (
                    <React.Fragment key={i}>
                      <tr
                        onClick={() => istWaehlbar && toggleRow(b.import_hash)}
                        className={[
                          'border-b transition-colors',
                          b.duplikat
                            ? 'opacity-40 bg-gray-50'
                            : istAusgewaehlt
                              ? 'bg-blue-50 hover:bg-blue-100 cursor-pointer'
                              : 'bg-white hover:bg-gray-50 cursor-pointer opacity-60',
                        ].join(' ')}
                      >
                        <td className="px-3 py-1.5" onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={istAusgewaehlt}
                            disabled={!istWaehlbar}
                            onChange={() => toggleRow(b.import_hash)}
                            className={istWaehlbar ? 'haken' : 'haken opacity-30'}
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <span className="flex items-center gap-1 flex-wrap">
                            {b.duplikat
                              ? <span className="badge badge-gray">Duplikat</span>
                              : b.duplikat_verdacht
                                ? <span className="badge bg-orange-100 text-orange-800">Verdacht</span>
                                : b.duplikat_aehnlich
                                  ? <span
                                      className="badge bg-amber-50 text-amber-700 border border-amber-200"
                                      title="Ähnliche Buchung im Toleranzfenster – nur ein Hinweis, die Zeile wird importiert"
                                    >ähnlich</span>
                                  : <span className="badge badge-green">Neu</span>}
                            {gewählterTreffer && (
                              <span className="badge bg-green-100 text-green-800">✓ Treffer</span>
                            )}
                            {hatTreffer && (
                              <button
                                type="button"
                                title="Vorhandene Buchungen anzeigen"
                                onClick={e => toggleExpandiert(b.import_hash, e)}
                                className="btn-secondary btn-icon-sm"
                              >
                                {istExpandiert ? '▲' : '▼'}
                              </button>
                            )}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 tabular-nums">{b.datum}</td>
                        <td className="px-3 py-1.5 max-w-[180px] truncate">{b.empfaenger || '–'}</td>
                        <td className="px-3 py-1.5 text-gray-400 text-xs max-w-[200px] truncate">{b.verwendungszweck || ''}</td>
                        <td className={`px-3 py-1.5 text-right font-mono font-medium ${b.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                          {fmt(b.betrag)}
                        </td>
                        <td className="px-3 py-1.5 text-gray-500 text-xs">
                          {b.empfaenger_name ? <span>{b.empfaenger_name}</span> : '–'}
                          {/* Sichtbar machen, was eine Import-Regel umgeschrieben hat –
                              sonst ändert der Import still Felder. */}
                          {b.regel_hinweis && (
                            <div className="text-blue-600" title="Import-Regel hat gegriffen">
                              {b.regel_hinweis}
                              {b.notiz && <span className="text-amber-600 ml-1">· Notiz: {b.notiz}</span>}
                            </div>
                          )}
                        </td>
                      </tr>
                      {istExpandiert && hatTreffer && (
                        <tr className="border-b bg-amber-50">
                          <td />
                          <td colSpan={6} className="px-4 py-2 space-y-1">
                            {b.duplikat ? (
                              /* Hard-Duplikat: Einzeleintrag */
                              <div className="flex items-center gap-4 text-xs text-amber-900">
                                <span className="font-medium text-amber-700">Vorhandene Buchung:</span>
                                <span className="tabular-nums">{b.vorhandene_buchung.datum}</span>
                                <span className="truncate max-w-[200px]">{b.vorhandene_buchung.empfaenger || '–'}</span>
                                {b.vorhandene_buchung.notiz && (
                                  <span className="text-amber-600 truncate max-w-[200px]">{b.vorhandene_buchung.notiz}</span>
                                )}
                                <span className={`font-mono font-medium ${b.vorhandene_buchung.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                                  {fmt(b.vorhandene_buchung.betrag)}
                                </span>
                              </div>
                            ) : (
                              /* Verdacht / Neu: alle Buchungen im Toleranzfenster */
                              <>
                                <div className="text-xs font-medium text-amber-700 mb-1">
                                  Buchungen im ±{vorschau.tage_toleranz}-Tage-Fenster ({b.nahe_buchungen.length}):
                                </div>
                                {b.nahe_buchungen.map(nb => {
                                  const istSoftMatch = nb.betrag === b.betrag
                                  const istAehnlich = !istSoftMatch && betragAehnlich(nb.betrag, b.betrag, vorschau.betrag_toleranz)
                                  const istGewählt = gewählterTreffer === nb.id
                                  return (
                                    <div
                                      key={nb.id}
                                      className={[
                                        'flex items-center gap-3 text-xs rounded px-2 py-1 cursor-pointer border transition-colors',
                                        istGewählt
                                          ? 'bg-green-100 border-green-400 text-green-900'
                                          : istSoftMatch
                                            ? 'bg-orange-100 border-orange-200 text-orange-900 hover:bg-orange-200'
                                            : istAehnlich
                                              ? 'bg-amber-50 border-amber-200 text-amber-900 hover:bg-amber-100'
                                              : 'border-transparent text-amber-900 hover:bg-amber-100',
                                      ].join(' ')}
                                      onClick={e => waehleNaheBuchung(b.import_hash, nb.id, e)}
                                    >
                                      <span className="tabular-nums w-24 shrink-0">{nb.datum}</span>
                                      <span className="truncate max-w-[200px]">{nb.empfaenger || '–'}</span>
                                      {nb.notiz && <span className="truncate max-w-[180px] opacity-70">{nb.notiz}</span>}
                                      <span className={`font-mono font-medium shrink-0 ${nb.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                                        {fmt(nb.betrag)}
                                      </span>
                                      {istSoftMatch && !istGewählt && <span className="badge bg-orange-200 text-orange-800 shrink-0">Betrag gleich</span>}
                                      {istAehnlich && !istGewählt && (
                                        <span className="badge bg-amber-100 text-amber-800 shrink-0">
                                          {fmt(Math.abs(nb.betrag - b.betrag))} Differenz
                                        </span>
                                      )}
                                      <span className="ml-auto shrink-0 font-medium">
                                        {istGewählt ? '✓ Gewählt – klicken zum Aufheben' : 'Als Treffer wählen'}
                                      </span>
                                    </div>
                                  )
                                })}
                              </>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Archiv: die PDFs, aus denen importiert wurde. Nachweis hinter jeder
          Buchung - deshalb liegt die Liste hier und nicht in den Einstellungen. */}
      {kontoId && (
        <div className="card space-y-2">
          <div className="flex items-baseline justify-between gap-2 flex-wrap">
            <h3 className="font-semibold">Gespeicherte Kontoauszüge</h3>
            <span className="text-xs text-gray-500">
              Werden beim Import abgelegt und sind im Backup enthalten.
            </span>
          </div>
          {auszuege.length === 0 ? (
            <p className="text-sm text-gray-500">
              Noch kein Auszug für dieses Konto archiviert.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 pr-3">Zeitraum</th>
                    <th className="text-left py-2 pr-3">Datei</th>
                    <th className="text-left py-2 pr-3">Bank</th>
                    <th className="text-right py-2 pr-3">Zeilen</th>
                    <th className="text-left py-2 pr-3">Importiert</th>
                    <th className="py-2"></th>
                  </tr>
                </thead>
                {auszugJahre.map(g => (
                <tbody key={g.jahr}>
                  <tr>
                    <th
                      colSpan={4}
                      className="text-left pt-3 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500"
                    >
                      {g.jahr}
                    </th>
                    <th colSpan={2} className="text-right pt-3 pb-1 text-xs font-normal text-gray-500">
                      {g.liste.length === 1 ? '1 Auszug' : `${g.liste.length} Auszüge`}
                    </th>
                  </tr>
                  {g.liste.map(a => (
                    <tr key={a.id} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="py-2 pr-3 tabular-nums whitespace-nowrap">
                        {a.zeitraum_von ? `${a.zeitraum_von} – ${a.zeitraum_bis}` : '–'}
                      </td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          className="text-blue-600 hover:underline text-left"
                          onClick={() => setAuszugAnsicht(a)}
                        >
                          {a.dateiname}
                        </button>
                      </td>
                      <td className="py-2 pr-3">{a.bank || '–'}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{a.anzahl_buchungen}</td>
                      <td className="py-2 pr-3 whitespace-nowrap text-gray-500">
                        {a.importiert_am.slice(0, 10)}
                        {a.importiert_von ? ` · ${a.importiert_von}` : ''}
                      </td>
                      <td className="py-2 text-right whitespace-nowrap">
                        <button
                          type="button"
                          className="btn-secondary btn-icon mr-1"
                          title="Anzeigen"
                          aria-label="Anzeigen"
                          onClick={() => setAuszugAnsicht(a)}
                        >
                          <EyeIcon className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          className="btn-danger btn-icon"
                          title="Löschen"
                          aria-label="Löschen"
                          onClick={() => auszugLoeschen(a)}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                ))}
              </table>
            </div>
          )}
        </div>
      )}

      {/* Anzeige im eingebetteten PDF-Viewer des Browsers. Der Endpunkt liefert
          Content-Disposition "inline", sonst würde stattdessen ein Download
          starten. */}
      {auszugAnsicht && (
        <Modal
          onClose={() => setAuszugAnsicht(null)}
          title={auszugAnsicht.dateiname}
          maxWidth="max-w-5xl"
          footer={
            <div className="flex justify-between items-center gap-3">
              <span className="text-xs text-gray-500">
                {auszugAnsicht.zeitraum_von
                  ? `${auszugAnsicht.zeitraum_von} – ${auszugAnsicht.zeitraum_bis}`
                  : 'Kein Zeitraum erkannt'}
                {auszugAnsicht.bank ? ` · ${auszugAnsicht.bank}` : ''}
                {` · ${auszugAnsicht.anzahl_buchungen} Zeilen`}
              </span>
              <a
                href={importPdfApi.auszugDateiUrl(auszugAnsicht.id)}
                download={auszugAnsicht.dateiname}
                className="btn-secondary"
              >
                Herunterladen
              </a>
            </div>
          }
        >
          <iframe
            src={importPdfApi.auszugDateiUrl(auszugAnsicht.id)}
            title={auszugAnsicht.dateiname}
            className="w-full h-[70vh] border rounded"
          />
        </Modal>
      )}

      {dialog}
    </div>
  )
}
