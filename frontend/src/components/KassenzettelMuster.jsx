import { useEffect, useRef, useState } from 'react'
import { einstellungenApi } from '../api'
import KategorieSelect from './KategorieSelect'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

// Rotierende Farbpalette für freie Bereichsmarkierungen (kein festes Ziel-Attribut wie
// bei Kontoauszug, daher keine attribut-basierte Farbzuordnung).
const MARKIERUNG_FARBEN = ['#2563eb', '#16a34a', '#9333ea', '#d97706', '#db2777', '#0891b2']
const markierungFarbe = (i) => MARKIERUNG_FARBEN[i % MARKIERUNG_FARBEN.length]

export default function KassenzettelMuster() {
  const [muster, setMuster] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [laden, setLaden] = useState(true)
  const [meldung, setMeldung] = useState(null) // {typ, text}
  const [aktivId, setAktivId] = useState(null)

  // Neues-Geschäft-Formular
  const [neuName, setNeuName] = useState('')
  const [neuKeywords, setNeuKeywords] = useState('')
  const [anlegen, setAnlegen] = useState(false)

  const lade = () => {
    setLaden(true)
    Promise.all([einstellungenApi.kzListe(), einstellungenApi.kzKategorien()])
      .then(([m, k]) => { setMuster(m.data); setKategorien(k.data) })
      .catch(() => setMeldung({ typ: 'fehler', text: 'Geschäfte konnten nicht geladen werden.' }))
      .finally(() => setLaden(false))
  }
  useEffect(lade, [])

  const onAnlegen = async () => {
    if (!neuName.trim()) return
    setAnlegen(true); setMeldung(null)
    try {
      const r = await einstellungenApi.kzAnlegen({
        name: neuName.trim(),
        erkennung_keywords: neuKeywords.split(',').map(s => s.trim()).filter(Boolean),
      })
      setNeuName(''); setNeuKeywords('')
      lade()
      setAktivId(r.data.id)
      setMeldung({ typ: 'ok', text: `Geschäft „${r.data.name}" angelegt – Beispielfoto hochladen und Felder einstellen.` })
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Anlegen fehlgeschlagen.' })
    } finally {
      setAnlegen(false)
    }
  }

  const onLoeschen = async (m) => {
    if (!window.confirm(`Geschäft „${m.name}" inkl. Beispielfoto löschen?`)) return
    try {
      await einstellungenApi.kzLoeschen(m.id)
      if (aktivId === m.id) setAktivId(null)
      lade()
    } catch {
      setMeldung({ typ: 'fehler', text: 'Löschen fehlgeschlagen.' })
    }
  }

  const onToggleAktiv = async (m) => {
    try {
      await einstellungenApi.kzUpdate(m.id, { aktiv: !m.aktiv })
      setMuster(prev => prev.map(x => x.id === m.id ? { ...x, aktiv: !x.aktiv } : x))
    } catch {
      setMeldung({ typ: 'fehler', text: 'Aktiv-Status konnte nicht geändert werden.' })
    }
  }

  if (laden) return <div className="text-sm text-gray-400">Lade Geschäfte…</div>

  return (
    <div className="space-y-5">
      <div>
        <h3 className="font-semibold text-gray-700">Kassenzettel-Muster (Foto-Import)</h3>
        <p className="text-xs text-gray-400 mt-1">
          Geschäfts-Erkennung und Parser-Einstellungen für den Kassenzettel-Import per Foto:
          Erkennung, Artikelbereich, Filter und Preis-Muster. Unbekannte Geschäfte
          werden generisch („Best-Effort") ausgelesen. Die <strong>MwSt→Kategorie-Zuordnung</strong> ist
          hier und – gleichwertig – auf der Seite <strong>Geschäfte</strong> pflegbar; beide bearbeiten
          dasselbe verknüpfte Muster.
        </p>
      </div>

      {meldung && (
        <div className={`rounded px-3 py-2 text-sm ${meldung.typ === 'ok' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {meldung.text}
        </div>
      )}

      {muster.length === 0 ? (
        <p className="text-sm text-gray-400">Noch keine Geschäfte.</p>
      ) : (
        <div className="space-y-2">
          {muster.map(m => (
            <div key={m.id} className="border border-gray-100 rounded">
              <div
                className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50"
                onClick={() => setAktivId(aktivId === m.id ? null : m.id)}
              >
                <span className="text-gray-400 text-xs w-4">{aktivId === m.id ? '▾' : '▸'}</span>
                <span className="font-medium text-sm">{m.name}</span>
                <span className="font-mono text-xs text-gray-400">{m.geschaeft_key}</span>
                {m.erkennung_keywords.length === 0 && <span className="badge bg-amber-100 text-amber-800 text-[10px]">keine Keywords</span>}
                {m.hat_bild && <span className="badge badge-gray text-[10px]">Beispiel</span>}
                {m.mwst_kategorie_map.length > 0 && <span className="badge badge-green text-[10px]">MwSt-Map</span>}
                <span className="ml-auto" onClick={e => e.stopPropagation()}>
                  <label className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-500">
                    <input type="checkbox" checked={m.aktiv} onChange={() => onToggleAktiv(m)} className="w-3.5 h-3.5 accent-blue-600" />
                    aktiv
                  </label>
                </span>
              </div>
              {aktivId === m.id && (
                <KzDetail
                  muster={m}
                  kategorien={kategorien}
                  onGeaendert={lade}
                  onLoeschen={() => onLoeschen(m)}
                  setMeldung={setMeldung}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Neues Geschäft */}
      <div className="border border-dashed border-gray-200 rounded p-4 space-y-3">
        <h4 className="font-medium text-sm text-gray-700">Neues Geschäft</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Name*</label>
            <input className="input w-full" value={neuName} onChange={e => setNeuName(e.target.value)} placeholder="z.B. Aldi Süd" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Erkennungs-Keywords (Komma-getrennt)</label>
            <input className="input w-full" value={neuKeywords} onChange={e => setNeuKeywords(e.target.value)} placeholder="z.B. aldi, aldi süd" />
          </div>
        </div>
        <button className="btn-primary" onClick={onAnlegen} disabled={!neuName.trim() || anlegen}>
          {anlegen ? 'Legt an…' : 'Geschäft anlegen'}
        </button>
      </div>
    </div>
  )
}

// ── Detail: Parser-Einstellungen + Beispielfoto + Probe ────────────────────────
function KzDetail({ muster, kategorien, onGeaendert, onLoeschen, setMeldung }) {
  const [name, setName] = useState(muster.name)
  const [keywords, setKeywords] = useState((muster.erkennung_keywords || []).join(', '))
  const [startMarker, setStartMarker] = useState(muster.start_marker || '')
  const [stopMarker, setStopMarker] = useState(muster.stop_marker || '')
  const [skip, setSkip] = useState((muster.skip_keywords || []).join(', '))
  const [preisRegex, setPreisRegex] = useState(muster.preis_regex || '')
  const [notiz, setNotiz] = useState(muster.notiz || '')
  const [map, setMap] = useState(muster.mwst_kategorie_map || []) // [{schluessel, kategorie_id}]
  const [markierungen, setMarkierungen] = useState(muster.feld_markierungen || []) // [{label, x, y, w, h}]
  const [pendingLabel, setPendingLabel] = useState('')
  const [pending, setPending] = useState(null)  // {x,y,w,h} während/nach dem Ziehen
  const [draw, setDraw] = useState(null)        // Startpunkt beim Ziehen
  const [speichern, setSpeichern] = useState(false)
  const [probe, setProbe] = useState(null)
  const [probeLaeuft, setProbeLaeuft] = useState(false)
  const [cacheBust, setCacheBust] = useState(Date.now())
  const [zeigeVorschau, setZeigeVorschau] = useState(false)
  const fotoRef = useRef()
  const vorschauBildRef = useRef()

  const setMapEintrag = (i, feld, wert) =>
    setMap(prev => prev.map((e, idx) => idx === i ? { ...e, [feld]: wert } : e))
  const entferneMap = (i) => setMap(prev => prev.filter((_, idx) => idx !== i))
  const addMap = (schluessel = '') => {
    if (schluessel && map.some(e => e.schluessel === schluessel)) return
    setMap(prev => [...prev, { schluessel, kategorie_id: kategorien[0]?.id ?? 0 }])
  }

  // Bereichsmarkierung auf dem verarbeiteten (entzerrten) Bild – rein dokumentarisch,
  // freie Rechtecke mit Freitext-Label statt eines festen Ziel-Attributs.
  const relPos = (e) => {
    const r = vorschauBildRef.current.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    }
  }
  const onMarkierungDown = (e) => { e.preventDefault(); const p = relPos(e); setDraw(p); setPending(null) }
  const onMarkierungMove = (e) => {
    if (!draw) return
    const p = relPos(e)
    setPending({ x: Math.min(draw.x, p.x), y: Math.min(draw.y, p.y), w: Math.abs(p.x - draw.x), h: Math.abs(p.y - draw.y) })
  }
  const onMarkierungUp = () => {
    setDraw(null)
    if (pending && (pending.w < 0.01 || pending.h < 0.01)) setPending(null)
  }
  const bestaetigeMarkierung = () => {
    if (!pending || !pendingLabel.trim()) return
    setMarkierungen(prev => [...prev, { ...pending, label: pendingLabel.trim() }])
    setPending(null); setPendingLabel('')
  }
  const entferneMarkierung = (i) => setMarkierungen(prev => prev.filter((_, idx) => idx !== i))

  // Ohne Vorschaubild ergeben Markierungen keinen Sinn – beim Öffnen der Markierungs-Ansicht
  // automatisch eine Probe anstoßen, falls noch keine (in dieser Sitzung bekannte) Vorschau existiert.
  const oeffneMarkierungen = async () => {
    if (zeigeVorschau) { setZeigeVorschau(false); return }
    if (!probe?.hat_vorschau) await onProbe()
    setZeigeVorschau(true)
  }

  const speichereAlles = async () => {
    // Duplikat-Schlüssel prüfen
    const gueltigeMap = map.filter(e => e.schluessel.trim())
    const schluessel = gueltigeMap.map(e => e.schluessel.trim().toUpperCase())
    const duplikate = schluessel.filter((s, i) => schluessel.indexOf(s) !== i)
    if (duplikate.length > 0) {
      setMeldung({ typ: 'fehler', text: `Doppelter MwSt-Schlüssel: „${[...new Set(duplikate)].join('", „')}" – bitte eindeutige Schlüssel verwenden.` })
      return
    }

    setSpeichern(true); setMeldung(null)
    try {
      await einstellungenApi.kzUpdate(muster.id, {
        name: name.trim(),
        erkennung_keywords: keywords.split(',').map(s => s.trim()).filter(Boolean),
        start_marker: startMarker,
        stop_marker: stopMarker,
        skip_keywords: skip.split(',').map(s => s.trim()).filter(Boolean),
        preis_regex: preisRegex,
        mwst_kategorie_map: gueltigeMap.map(e => ({
          schluessel: e.schluessel.trim(), kategorie_id: Number(e.kategorie_id),
        })),
        feld_markierungen: markierungen,
        notiz,
      })
      setMeldung({ typ: 'ok', text: 'Geschäft gespeichert.' })
      onGeaendert()
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Speichern fehlgeschlagen.' })
    } finally {
      setSpeichern(false)
    }
  }

  const onFoto = async (e) => {
    const f = e.target.files[0]
    if (!f) return
    setProbeLaeuft(true); setMeldung(null)
    try {
      const r = await einstellungenApi.kzBeispiel(muster.id, f)
      setProbe(r.data)
      // Neues Foto → alte Markierungen beziehen sich auf ein anderes Bild und
      // wurden serverseitig bereits verworfen (siehe muster.feld_markierungen).
      setMarkierungen(r.data.muster.feld_markierungen)
      setPending(null); setPendingLabel('')
      setCacheBust(Date.now())
      onGeaendert()
      setMeldung({ typ: 'ok', text: `Beispielfoto erkannt – ${r.data.positionen.length} Artikel.` })
    } catch (err) {
      setMeldung({ typ: 'fehler', text: err.response?.data?.detail ?? 'Upload fehlgeschlagen.' })
    } finally {
      setProbeLaeuft(false)
      if (fotoRef.current) fotoRef.current.value = ''
    }
  }

  // Probe mit aktuell GESPEICHERTEM Profil neu laufen lassen
  const onProbe = async () => {
    setProbeLaeuft(true); setMeldung(null)
    try {
      const r = await einstellungenApi.kzProbe(muster.id)
      setProbe(r.data)
    } catch (err) {
      setMeldung({ typ: 'fehler', text: err.response?.data?.detail ?? 'Probe fehlgeschlagen.' })
    } finally {
      setProbeLaeuft(false)
    }
  }

  const katName = (id) => kategorien.find(k => k.id === id)?.name ?? `#${id}`

  return (
    <div className="border-t border-gray-100 px-3 py-4">
      {/* Links Einstellungen, rechts Foto + Probe (Foto bekommt viel Raum) */}
      <div className="grid gap-6 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        {/* ── Einstellungen ── */}
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
            <input className="input w-full" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Erkennungs-Keywords (Komma-getrennt)</label>
            <input className="input w-full" value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="aldi, aldi süd" />
            <p className="text-[11px] text-gray-400 mt-0.5">Kommt eines davon im erkannten Text vor, wird dieses Geschäft verwendet.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Start-Marker</label>
              <input className="input w-full" value={startMarker} onChange={e => setStartMarker(e.target.value)} placeholder="optional" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Stop-Marker</label>
              <input className="input w-full" value={stopMarker} onChange={e => setStopMarker(e.target.value)} placeholder="z.B. Summe" />
            </div>
          </div>
          <p className="text-[11px] text-gray-400 -mt-1">Artikel werden nur zwischen Start- und Stop-Marker gelesen (Teiltext, Groß/Klein egal). Leer = ganzer Bon.</p>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Zusätzliche Filter-Begriffe (Komma-getrennt)</label>
            <input className="input w-full" value={skip} onChange={e => setSkip(e.target.value)} placeholder="pfand, coupon, rabatt" />
            <p className="text-[11px] text-gray-400 mt-0.5">Zeilen mit diesen Begriffen werden ignoriert (zusätzlich zu den Standard-Begriffen).</p>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Preis-Muster (Regex, optional)</label>
            <input className="input w-full font-mono text-xs" value={preisRegex} onChange={e => setPreisRegex(e.target.value)} placeholder="leer = Standard-Erkennung" />
            <p className="text-[11px] text-gray-400 mt-0.5">Nur für Sonderfälle. Gruppe 1 = Betrag, Gruppe 2 = MwSt-Schlüssel.</p>
          </div>

          {/* MwSt → Kategorie */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">MwSt-Schlüssel → Kategorie</label>
            <div className="space-y-1.5">
              {map.length === 0 && <p className="text-[11px] text-gray-400">Keine Zuordnung – Standard nach MwSt-Satz (7 % → Lebensmittel, sonst Haushaltswaren).</p>}
              {map.map((e, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    className="input w-16 text-center font-mono uppercase"
                    value={e.schluessel}
                    onChange={ev => setMapEintrag(i, 'schluessel', ev.target.value)}
                    placeholder="A"
                    maxLength={2}
                  />
                  <span className="text-gray-400">→</span>
                  <KategorieSelect
                    kategorien={kategorien}
                    value={e.kategorie_id}
                    onChange={id => setMapEintrag(i, 'kategorie_id', id ?? kategorien[0]?.id ?? 0)}
                    isClearable={false}
                    className="flex-1"
                  />
                  <button className="text-gray-400 hover:text-red-600 px-1" onClick={() => entferneMap(i)} title="Entfernen">×</button>
                </div>
              ))}
              <button className="text-xs text-blue-600 hover:underline" onClick={() => addMap()}>+ Zuordnung</button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Notiz</label>
            <textarea className="input w-full" rows={2} value={notiz} onChange={e => setNotiz(e.target.value)} />
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button className="btn-primary" onClick={speichereAlles} disabled={speichern}>
              {speichern ? 'Speichert…' : 'Speichern'}
            </button>
            <button className="btn-secondary text-red-600" onClick={onLoeschen}>Löschen</button>
          </div>
        </div>

        {/* ── Beispielfoto + Probe ── */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">Beispielfoto · Probe-Extraktion</span>
            <span className="flex items-center gap-3">
              {muster.hat_bild && (
                <button className="text-xs text-blue-600 hover:underline disabled:text-gray-400" onClick={onProbe} disabled={probeLaeuft}>
                  {probeLaeuft ? 'Prüft…' : 'Erneut prüfen'}
                </button>
              )}
              {muster.hat_bild && (
                <button className="text-xs text-blue-600 hover:underline disabled:text-gray-400" onClick={oeffneMarkierungen} disabled={probeLaeuft}>
                  {probeLaeuft ? 'Lädt…' : zeigeVorschau ? 'Bereichsmarkierung ausblenden' : `Bereichsmarkierung${markierungen.length ? ` (${markierungen.length})` : ''}`}
                </button>
              )}
              <label className="text-xs text-blue-600 hover:underline cursor-pointer">
                {muster.hat_bild ? 'Foto ersetzen' : 'Foto hochladen'}
                <input ref={fotoRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={onFoto} />
              </label>
            </span>
          </div>

          {muster.hat_bild ? (
            <div className="grid gap-3 md:grid-cols-2">
              <a href={`${einstellungenApi.kzScreenshotUrl(muster.id)}?t=${cacheBust}`} target="_blank" rel="noreferrer" title="In voller Größe öffnen">
                <img
                  src={`${einstellungenApi.kzScreenshotUrl(muster.id)}?t=${cacheBust}`}
                  alt="Beispiel-Kassenzettel"
                  className="w-full block rounded border border-gray-200"
                />
              </a>
              <div className="text-xs">
                {probe ? (
                  <>
                    {/* OCR-Qualitäts-Info */}
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mb-2 text-gray-500">
                      {probe.konfidenz != null && (
                        <span>Sicherheit: <strong>{probe.konfidenz.toFixed(0)} %</strong></span>
                      )}
                      {probe.ocr_preiszeilen != null && (
                        <span>Preiszeilen: <strong>{probe.ocr_preiszeilen}</strong></span>
                      )}
                      {probe.ocr_variante && (
                        <span className="font-mono text-[10px] bg-gray-100 rounded px-1 py-0.5 self-center">
                          {probe.ocr_variante}
                          {probe.ocr_segmentiert && <span className="ml-1 text-green-700" title="Beleg aus Foto freigestellt">✓ freigestellt</span>}
                        </span>
                      )}
                    </div>
                    {zeigeVorschau && !probe.hat_vorschau && (
                      <p className="text-amber-700 mb-2">Kein Vorschaubild verfügbar (Foto evtl. unlesbar).</p>
                    )}
                    {zeigeVorschau && probe.hat_vorschau && (
                      <div className="mb-2 space-y-1.5">
                        <div
                          ref={vorschauBildRef}
                          className="relative border border-gray-200 rounded overflow-hidden select-none cursor-crosshair"
                          onMouseDown={onMarkierungDown}
                          onMouseMove={onMarkierungMove}
                          onMouseUp={onMarkierungUp}
                          onMouseLeave={onMarkierungUp}
                        >
                          <img
                            src={`${einstellungenApi.kzVorschauUrl(muster.id)}?t=${cacheBust}`}
                            alt="Verarbeitetes Bild (OCR-Eingabe)"
                            className="w-full block pointer-events-none"
                            draggable={false}
                          />
                          {markierungen.map((m, i) => (
                            <div key={i} className="absolute" style={{
                              left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.w * 100}%`, height: `${m.h * 100}%`,
                              border: `2px solid ${markierungFarbe(i)}`, background: `${markierungFarbe(i)}22`,
                            }}>
                              <span className="absolute -top-4 left-0 text-[10px] px-1 rounded text-white whitespace-nowrap"
                                style={{ background: markierungFarbe(i) }}>{m.label}</span>
                            </div>
                          ))}
                          {pending && (
                            <div className="absolute border-2 border-dashed border-gray-700 bg-gray-700/10" style={{
                              left: `${pending.x * 100}%`, top: `${pending.y * 100}%`, width: `${pending.w * 100}%`, height: `${pending.h * 100}%`,
                            }} />
                          )}
                        </div>

                        {pending && pending.w >= 0.01 && (
                          <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                            <input
                              className="input py-0.5 flex-1"
                              placeholder="Beschriftung (z.B. Stop-Marker)"
                              value={pendingLabel}
                              onChange={e => setPendingLabel(e.target.value)}
                              autoFocus
                            />
                            <button className="btn-secondary btn-sm" onClick={bestaetigeMarkierung} disabled={!pendingLabel.trim()}>
                              Bestätigen
                            </button>
                            <button className="text-gray-500 hover:underline" onClick={() => { setPending(null); setPendingLabel('') }}>verwerfen</button>
                          </div>
                        )}

                        {markierungen.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {markierungen.map((m, i) => (
                              <span key={i}
                                className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border"
                                style={{ borderColor: markierungFarbe(i), color: markierungFarbe(i) }}>
                                <span className="w-2 h-2 rounded-sm inline-block" style={{ background: markierungFarbe(i) }} />
                                {m.label}
                                <button onClick={() => entferneMarkierung(i)} className="ml-0.5 hover:font-bold" title="Markierung entfernen">×</button>
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="text-[11px] text-gray-400">
                          Rein zur eigenen Dokumentation, ohne Effekt auf die Erkennung. Rechteck aufziehen, beschriften,
                          „Bestätigen" – „Speichern" sichert die Markierungen.
                        </p>
                      </div>
                    )}
                    {probe.erkannte_schluessel.length > 0 && (
                      <p className="text-gray-500 mb-2">
                        MwSt-Schlüssel:{' '}
                        {probe.erkannte_schluessel.map(s => (
                          <button key={s} className="badge badge-gray mr-1 hover:bg-blue-100" onClick={() => addMap(s)} title="Zur Zuordnung hinzufügen">
                            {s} +
                          </button>
                        ))}
                      </p>
                    )}
                    {probe.positionen.length > 0 ? (
                      <table className="w-full">
                        <thead><tr className="text-left text-gray-500"><th className="py-1">Artikel</th><th className="text-center">St.</th><th className="text-right">Preis</th></tr></thead>
                        <tbody>
                          {probe.positionen.map((p, i) => (
                            <tr key={i} className="border-t border-gray-100">
                              <td className="py-1 pr-2">{p.bezeichnung}{p.mwst_schluessel && <span className="text-gray-400 ml-1">[{p.mwst_schluessel}]</span>}</td>
                              <td className="text-center text-gray-500">{p.menge}</td>
                              <td className="text-right font-mono">{fmt(p.gesamtpreis)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <p className="text-amber-700">Keine Artikel erkannt – Marker/Filter anpassen und „Erneut prüfen".</p>
                    )}
                  </>
                ) : (
                  <p className="text-gray-400">„Erneut prüfen", um die Extraktion mit den gespeicherten Einstellungen zu testen.</p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400 border border-dashed border-gray-200 rounded p-4 text-center">
              Kein Beispielfoto. Über „Foto hochladen" einen Beispiel-Kassenzettel zum Testen hochladen.
            </p>
          )}
          <p className="text-[11px] text-gray-400">
            Reihenfolge: Einstellungen ändern → „Speichern" → „Erneut prüfen". So siehst du sofort, wie sich Marker/Filter auf die Artikelerkennung auswirken.
          </p>
        </div>
      </div>
    </div>
  )
}
