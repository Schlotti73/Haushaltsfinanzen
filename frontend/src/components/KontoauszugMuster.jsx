import { useEffect, useRef, useState } from 'react'
import { einstellungenApi } from '../api'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

// Feste Farbe je Ziel-Attribut für Markierungen/Legende
const FARBEN = {
  datum: '#2563eb',
  betrag: '#16a34a',
  empfaenger: '#9333ea',
  verwendungszweck: '#d97706',
  iban_empfaenger: '#db2777',
  konto_hinweis: '#0891b2',
}
const farbe = (attr) => FARBEN[attr] || '#6b7280'

export default function KontoauszugMuster() {
  const [muster, setMuster] = useState([])
  const [zielAttribute, setZielAttribute] = useState([])
  const [laden, setLaden] = useState(true)
  const [meldung, setMeldung] = useState(null) // {typ, text}
  const [aktivId, setAktivId] = useState(null)  // aufgeklapptes Muster
  const [probe, setProbe] = useState(null)      // {bank, konto_hinweis, probe[], fehler[]}

  // Neues-Muster-Formular
  const [neuName, setNeuName] = useState('')
  const [neuKeywords, setNeuKeywords] = useState('')
  const [neuDatei, setNeuDatei] = useState(null)
  const [uploadLaeuft, setUploadLaeuft] = useState(false)
  const neuFileRef = useRef()

  const lade = () => {
    setLaden(true)
    Promise.all([einstellungenApi.musterListe(), einstellungenApi.musterZielAttribute()])
      .then(([m, z]) => { setMuster(m.data); setZielAttribute(z.data) })
      .catch(() => setMeldung({ typ: 'fehler', text: 'Muster konnten nicht geladen werden.' }))
      .finally(() => setLaden(false))
  }
  useEffect(lade, [])

  const onUpload = async () => {
    if (!neuName.trim() || !neuDatei) return
    setUploadLaeuft(true); setMeldung(null); setProbe(null)
    try {
      const r = await einstellungenApi.musterUpload(neuName.trim(), neuKeywords.trim(), neuDatei)
      setProbe(r.data)
      setNeuName(''); setNeuKeywords(''); setNeuDatei(null)
      if (neuFileRef.current) neuFileRef.current.value = ''
      lade()
      setAktivId(r.data.muster.id)
      setMeldung({ typ: 'ok', text: `Muster „${r.data.muster.name}" angelegt – ${r.data.probe.length} Probe-Buchung(en) erkannt.` })
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Upload fehlgeschlagen.' })
    } finally {
      setUploadLaeuft(false)
    }
  }

  const onLoeschen = async (m) => {
    if (!window.confirm(`Muster „${m.name}" inkl. Beispiel löschen?`)) return
    try {
      await einstellungenApi.musterLoeschen(m.id)
      if (aktivId === m.id) setAktivId(null)
      lade()
    } catch {
      setMeldung({ typ: 'fehler', text: 'Löschen fehlgeschlagen.' })
    }
  }

  const onToggleAktiv = async (m) => {
    try {
      await einstellungenApi.musterUpdate(m.id, { aktiv: !m.aktiv })
      setMuster(prev => prev.map(x => x.id === m.id ? { ...x, aktiv: !x.aktiv } : x))
    } catch {
      setMeldung({ typ: 'fehler', text: 'Aktiv-Status konnte nicht geändert werden.' })
    }
  }

  if (laden) return <div className="text-sm text-gray-400">Lade Muster…</div>

  return (
    <div className="space-y-5">
      <div>
        <h3 className="font-semibold text-gray-700">Kontoauszug-Muster</h3>
        <p className="text-xs text-gray-400 mt-1">
          Banken-Erkennung und Feld-Zuordnung für den Kontoauszug-Import. Beispiel-Kontoauszug hochladen,
          um ein neues Muster bereitzustellen und die Ziel-Attribute am Beispiel zu markieren.
        </p>
      </div>

      {meldung && (
        <div className={`rounded px-3 py-2 text-sm ${meldung.typ === 'ok' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {meldung.text}
        </div>
      )}

      {/* Muster-Liste */}
      {muster.length === 0 ? (
        <p className="text-sm text-gray-400">Noch keine Muster.</p>
      ) : (
        <div className="space-y-2">
          {muster.map(m => (
            <div key={m.id} className="border border-gray-100 rounded">
              <div
                className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50"
                onClick={() => { setAktivId(aktivId === m.id ? null : m.id); setProbe(null) }}
              >
                <span className="text-gray-400 text-xs w-4">{aktivId === m.id ? '▾' : '▸'}</span>
                <span className="font-medium text-sm">{m.name}</span>
                <span className="font-mono text-xs text-gray-400">{m.bank_key}</span>
                {m.parser_key
                  ? <span className="badge badge-green text-[10px]">Parser: {m.parser_key}</span>
                  : <span className="badge bg-amber-100 text-amber-800 text-[10px]">ungemappt</span>}
                {m.hat_screenshot && <span className="badge badge-gray text-[10px]">Beispiel</span>}
                <span className="ml-auto" onClick={e => e.stopPropagation()}>
                  <label className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-500">
                    <input type="checkbox" checked={m.aktiv} onChange={() => onToggleAktiv(m)} className="w-3.5 h-3.5 accent-blue-600" />
                    aktiv
                  </label>
                </span>
              </div>
              {aktivId === m.id && (
                <MusterDetail
                  muster={m}
                  zielAttribute={zielAttribute}
                  onGeaendert={lade}
                  onLoeschen={() => onLoeschen(m)}
                  setMeldung={setMeldung}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Neues Muster */}
      <div className="border border-dashed border-gray-200 rounded p-4 space-y-3">
        <h4 className="font-medium text-sm text-gray-700">Neues Muster aus Beispiel-Kontoauszug</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Name*</label>
            <input className="input w-full" value={neuName} onChange={e => setNeuName(e.target.value)} placeholder="z.B. Volksbank Giro" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Erkennungs-Keywords (Komma-getrennt)</label>
            <input className="input w-full" value={neuKeywords} onChange={e => setNeuKeywords(e.target.value)} placeholder="z.B. volksbank, vr-bank" />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Beispiel-PDF*</label>
          <input ref={neuFileRef} type="file" accept=".pdf,application/pdf" className="input py-1.5" onChange={e => setNeuDatei(e.target.files[0] || null)} />
        </div>
        <button className="btn-primary" onClick={onUpload} disabled={!neuName.trim() || !neuDatei || uploadLaeuft}>
          {uploadLaeuft ? 'Lädt hoch…' : 'Muster anlegen'}
        </button>

        {probe && (
          <div className="mt-2 rounded border border-blue-200 bg-blue-50 p-3 space-y-2">
            <p className="text-sm text-blue-800">
              Probe-Extraktion (Bank: <strong>{probe.bank}</strong>
              {probe.konto_hinweis && <> · Konto: <span className="font-mono">{probe.konto_hinweis}</span></>}):
            </p>
            {probe.fehler?.length > 0 && (
              <p className="text-xs text-amber-700">{probe.fehler.join(' · ')}</p>
            )}
            {probe.probe.length > 0 && (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-gray-500"><th className="py-1">Datum</th><th>Empfänger</th><th className="text-right">Betrag</th></tr></thead>
                <tbody>
                  {probe.probe.map((b, i) => (
                    <tr key={i} className="border-t border-blue-100">
                      <td className="py-1 tabular-nums">{b.datum}</td>
                      <td className="truncate max-w-[260px]">{b.empfaenger || '–'}</td>
                      <td className={`text-right font-mono ${b.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>{fmt(b.betrag)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Detail: Felder bearbeiten + Screenshot mit Markierungs-Editor ──────────────
function MusterDetail({ muster, zielAttribute, onGeaendert, onLoeschen, setMeldung }) {
  const [name, setName] = useState(muster.name)
  const [keywords, setKeywords] = useState((muster.erkennung_keywords || []).join(', '))
  const [parserKey, setParserKey] = useState(muster.parser_key || '')
  const [notiz, setNotiz] = useState(muster.notiz || '')
  const [markierungen, setMarkierungen] = useState(muster.feld_markierungen || [])
  const [pending, setPending] = useState(null)     // {x,y,w,h} während/nach dem Ziehen
  const [draw, setDraw] = useState(null)           // Startpunkt beim Ziehen
  const [speichern, setSpeichern] = useState(false)
  const [cacheBust, setCacheBust] = useState(Date.now())
  const bildRef = useRef()
  const beispielRef = useRef()

  const relPos = (e) => {
    const r = bildRef.current.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    }
  }
  const onDown = (e) => { e.preventDefault(); const p = relPos(e); setDraw(p); setPending(null) }
  const onMove = (e) => {
    if (!draw) return
    const p = relPos(e)
    setPending({ x: Math.min(draw.x, p.x), y: Math.min(draw.y, p.y), w: Math.abs(p.x - draw.x), h: Math.abs(p.y - draw.y) })
  }
  const onUp = () => {
    setDraw(null)
    if (pending && (pending.w < 0.01 || pending.h < 0.01)) setPending(null)
  }

  const bestaetigeMarkierung = (attribut) => {
    if (!pending || !attribut) return
    const ziel = zielAttribute.find(z => z.attribut === attribut)
    setMarkierungen(prev => [...prev.filter(m => m.attribut !== attribut), { ...pending, attribut, label: ziel?.label || attribut }])
    setPending(null)
  }
  const entferne = (attr) => setMarkierungen(prev => prev.filter(m => m.attribut !== attr))

  const speichereAlles = async () => {
    setSpeichern(true); setMeldung(null)
    try {
      await einstellungenApi.musterUpdate(muster.id, {
        name: name.trim(),
        parser_key: parserKey.trim() || null,
        erkennung_keywords: keywords.split(',').map(s => s.trim()).filter(Boolean),
        feld_markierungen: markierungen,
        notiz,
      })
      setMeldung({ typ: 'ok', text: 'Muster gespeichert.' })
      onGeaendert()
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Speichern fehlgeschlagen.' })
    } finally {
      setSpeichern(false)
    }
  }

  const onBeispielErsetzen = async (e) => {
    const f = e.target.files[0]
    if (!f) return
    try {
      await einstellungenApi.musterBeispiel(muster.id, f)
      setCacheBust(Date.now())
      onGeaendert()
      setMeldung({ typ: 'ok', text: 'Beispiel aktualisiert.' })
    } catch (err) {
      setMeldung({ typ: 'fehler', text: err.response?.data?.detail ?? 'Upload fehlgeschlagen.' })
    } finally {
      if (beispielRef.current) beispielRef.current.value = ''
    }
  }

  return (
    <div className="border-t border-gray-100 px-3 py-4 space-y-5">
      {/* Felder + Screenshot nebeneinander, Screenshot bekommt mehr Raum */}
      <div className={`grid gap-5 ${muster.hat_screenshot ? 'grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.2fr)]' : 'grid-cols-1 lg:grid-cols-2'}`}>
      {/* Felder */}
      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
          <input className="input w-full" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Erkennungs-Keywords (Komma-getrennt)</label>
          <input className="input w-full" value={keywords} onChange={e => setKeywords(e.target.value)} />
          <p className="text-[11px] text-gray-400 mt-0.5">Kommt eines davon im PDF-Text vor, wird dieses Muster verwendet.</p>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Code-Parser (parser_key)</label>
          <input className="input w-full font-mono text-sm" value={parserKey} onChange={e => setParserKey(e.target.value)} placeholder="leer = generischer Parser" />
          <p className="text-[11px] text-gray-400 mt-0.5">Verfügbar: postbank, ing, sparkasse. Leer = generischer Best-Effort-Parser.</p>
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

      {/* Screenshot + Markierungen */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-600">Beispiel-Screenshot · Felder markieren</span>
          <label className="text-xs text-blue-600 hover:underline cursor-pointer">
            Beispiel ersetzen
            <input ref={beispielRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={onBeispielErsetzen} />
          </label>
        </div>

        {muster.hat_screenshot ? (
          <>
            <div
              ref={bildRef}
              className="relative border border-gray-200 rounded overflow-hidden select-none cursor-crosshair"
              onMouseDown={onDown}
              onMouseMove={onMove}
              onMouseUp={onUp}
              onMouseLeave={onUp}
            >
              <img
                src={`${einstellungenApi.musterScreenshotUrl(muster.id)}?t=${cacheBust}`}
                alt="Beispiel-Kontoauszug"
                className="w-full block pointer-events-none"
                draggable={false}
              />
              {markierungen.map((m, i) => (
                <div key={i} className="absolute" style={{
                  left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.w * 100}%`, height: `${m.h * 100}%`,
                  border: `2px solid ${farbe(m.attribut)}`, background: `${farbe(m.attribut)}22`,
                }}>
                  <span className="absolute -top-4 left-0 text-[10px] px-1 rounded text-white whitespace-nowrap"
                    style={{ background: farbe(m.attribut) }}>{m.label || m.attribut}</span>
                </div>
              ))}
              {pending && (
                <div className="absolute border-2 border-dashed border-gray-700 bg-gray-700/10" style={{
                  left: `${pending.x * 100}%`, top: `${pending.y * 100}%`, width: `${pending.w * 100}%`, height: `${pending.h * 100}%`,
                }} />
              )}
            </div>

            {pending && pending.w >= 0.01 && (
              <div className="flex items-center gap-2 text-xs bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                <span className="text-amber-800">Bereich → Attribut:</span>
                <select className="input py-0.5 text-xs" defaultValue="" onChange={e => bestaetigeMarkierung(e.target.value)}>
                  <option value="" disabled>– wählen –</option>
                  {zielAttribute.map(z => <option key={z.attribut} value={z.attribut}>{z.label}</option>)}
                </select>
                <button className="text-gray-500 hover:underline" onClick={() => setPending(null)}>verwerfen</button>
              </div>
            )}

            {/* Legende der gesetzten Markierungen */}
            <div className="flex flex-wrap gap-1.5">
              {zielAttribute.map(z => {
                const gesetzt = markierungen.some(m => m.attribut === z.attribut)
                return (
                  <span key={z.attribut}
                    className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded border"
                    style={{ borderColor: farbe(z.attribut), color: farbe(z.attribut), opacity: gesetzt ? 1 : 0.4 }}>
                    <span className="w-2 h-2 rounded-sm inline-block" style={{ background: farbe(z.attribut) }} />
                    {z.label}
                    {gesetzt && <button onClick={() => entferne(z.attribut)} className="ml-0.5 hover:font-bold" title="Markierung entfernen">×</button>}
                  </span>
                )
              })}
            </div>
            <p className="text-[11px] text-gray-400">Rechteck über dem Feld aufziehen, dann Ziel-Attribut wählen. „Speichern" sichert die Markierungen.</p>
          </>
        ) : (
          <p className="text-sm text-gray-400 border border-dashed border-gray-200 rounded p-4 text-center">
            Kein Beispiel-Screenshot. Über „Beispiel ersetzen" ein PDF hochladen.
          </p>
        )}
      </div>
      </div>{/* end grid */}
    </div>
  )
}
