import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { buchungenApi, kontenApi, kategorienApi, projekteApi, empfaengerApi } from '../api'
import { auswaehlbareKonten } from '../kontoAuswahl'
import BuchungForm from '../components/BuchungForm'
import Modal from '../components/Modal'
import KategorieSelect from '../components/KategorieSelect'
import { useConfirm } from '../components/useConfirm'
import { PencilIcon } from '../components/icons'

function TransferDialog({ buchung, konten, kategorien, onClose, onDone }) {
  const [kandidaten, setKandidaten] = useState([])
  const [zielkontoId, setZielkontoId] = useState('')
  const [kategorieId, setKategorieId] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    buchungenApi.transferKandidaten(buchung.id).then(r => setKandidaten(r.data))
  }, [buchung.id])
  const verknuepfe = async (gegId) => {
    const r = await buchungenApi.transferVerknuepfen(buchung.id, gegId)
    onDone([
      { ...r.data },
      { id: gegId, ist_transfer: true, gegenbuchung_id: buchung.id },
    ])
    onClose()
  }
  const loese = async () => {
    const partnerId = buchung.gegenbuchung_id
    const r = await buchungenApi.transferLoesen(buchung.id)
    const patches = [{ ...r.data }]
    if (partnerId) patches.push({ id: partnerId, ist_transfer: false, gegenbuchung_id: null })
    onDone(patches)
    onClose()
  }
  const erstelleNeu = async () => {
    if (!zielkontoId) return
    setSaving(true)
    try {
      const r = await buchungenApi.transferNeu(buchung.id, zielkontoId, kategorieId || null)
      onDone([{ ...r.data }])
      onClose()
    } finally {
      setSaving(false)
    }
  }
  const fmt = (b) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(b)
  const kontoName = (id) => konten.find(k => k.id === id)?.name ?? '–'
  // Zielkonto wird neu gewählt -> nur aktive anbieten (das eigene Konto nie).
  const andereKonten = auswaehlbareKonten(konten, zielkontoId).filter(k => k.id !== buchung.konto_id)
  return (
    <Modal onClose={onClose} title={`Transfer – ${buchung.empfaenger}`} maxWidth="max-w-lg">
      <div className="space-y-4">
        {buchung.ist_transfer && (
          <button className="btn-danger w-full" onClick={loese}>Transfer-Verknüpfung lösen</button>
        )}

        {!buchung.ist_transfer && (
          <>
            {/* Neue Gegenbuchung erstellen */}
            <div className="rounded-lg border border-gray-200 p-4 space-y-3">
              <p className="text-sm font-medium text-gray-700">Neue Gegenbuchung erstellen</p>
              <p className="text-xs text-gray-400">
                Erstellt automatisch eine Buchung über {fmt(-buchung.betrag)} auf dem Zielkonto.
              </p>
              <div className="flex gap-2">
                <select
                  className="input flex-1"
                  value={zielkontoId}
                  onChange={e => setZielkontoId(e.target.value)}
                >
                  <option value="">Zielkonto wählen…</option>
                  {andereKonten.map(k => (
                    <option key={k.id} value={k.id}>{k.name}</option>
                  ))}
                </select>
              </div>
              <KategorieSelect
                kategorien={kategorien}
                value={kategorieId}
                onChange={id => setKategorieId(id)}
                placeholder="Keine Kategorie"
              />
              <button
                className="btn-primary w-full justify-center"
                disabled={!zielkontoId || saving}
                onClick={erstelleNeu}
              >
                {saving ? '…' : 'Gegenbuchung erstellen'}
              </button>
            </div>

            {/* Vorhandene Buchung verknüpfen */}
            {kandidaten.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-gray-700">Vorhandene Buchung verknüpfen</p>
                {kandidaten.map(k => (
                  <button key={k.id} className="w-full text-left card hover:border-blue-300 p-3" onClick={() => verknuepfe(k.id)}>
                    <div className="flex justify-between">
                      <span className="font-medium">{k.empfaenger || '–'}</span>
                      <span className={`font-mono font-medium ${k.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                        {fmt(k.betrag)}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">{k.datum} · {kontoName(k.konto_id)}</div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}

const ABGLEICH_LABEL = {
  bar_ohne_konto: { label: 'Bar (kein Konto)', cls: 'badge-gray' },
  offen: { label: 'Offen – warte auf Bank', cls: 'badge-blue' },
  verknuepft: { label: 'Abgeglichen', cls: 'badge-green' },
}

function HHDialog({ buchung, onClose, onDone }) {
  const istHHBuchung = buchung.quelle === 'haushaltsbuch'

  // ── Für HH-eigene Buchungen: zeige verknüpften HHB-Eintrag ─────────────────
  const [hhEintrag, setHhEintrag] = useState(null)
  useEffect(() => {
    if (istHHBuchung) buchungenApi.hhEintrag(buchung.id).then(r => setHhEintrag(r.data)).catch(() => {})
  }, [buchung.id, istHHBuchung])

  const bestaetigen = async () => {
    await buchungenApi.hhSelbstBestaetigen(buchung.id)
    onDone([{ id: buchung.id, hh_abgleich_status: 'verknuepft' }])
    onClose()
  }

  // ── Für Nicht-HH-Buchungen: suche passende HHB-Buchungen ──────────────────
  const [kandidaten, setKandidaten] = useState([])
  const [verknuepft, setVerknuepft] = useState(null)
  const [suchText, setSuchText] = useState('')
  const [suchErgebnisse, setSuchErgebnisse] = useState([])

  useEffect(() => {
    if (istHHBuchung) return
    buchungenApi.hhKandidaten(buchung.id).then(r => setKandidaten(r.data))
    if (buchung.verknuepft_mit_id) {
      buchungenApi.get(buchung.verknuepft_mit_id).then(r => setVerknuepft(r.data)).catch(() => {})
    } else {
      setVerknuepft(null)
    }
  }, [buchung.id, buchung.verknuepft_mit_id, istHHBuchung])

  useEffect(() => {
    if (istHHBuchung || !suchText.trim()) { setSuchErgebnisse([]); return }
    const t = setTimeout(() => {
      buchungenApi.list({ suche: suchText.trim(), pro_seite: 10 })
        .then(r => setSuchErgebnisse(
          r.data.items.filter(b => b.id !== buchung.id && !b.verknuepft_mit_id)
        ))
    }, 300)
    return () => clearTimeout(t)
  }, [suchText, buchung.id, istHHBuchung])

  const verknuepfe = async (zielId) => {
    const r = await buchungenApi.hhVerknuepfen(buchung.id, zielId)
    onDone([
      { ...r.data },
      { id: zielId, verknuepft_mit_id: buchung.id, verknuepfung_typ: 'kontoauszug', hh_abgleich_status: 'verknuepft' },
    ])
    onClose()
  }
  const loese = async () => {
    const partnerId = buchung.verknuepft_mit_id
    const r = await buchungenApi.hhLoesen(buchung.id)
    const patches = [{ ...r.data }]
    if (partnerId) patches.push({ id: partnerId, verknuepft_mit_id: null, verknuepfung_typ: null })
    onDone(patches)
    onClose()
  }

  const KandidatButton = ({ k }) => (
    <button className="w-full text-left card hover:border-blue-300 p-3" onClick={() => verknuepfe(k.id)}>
      <div className="flex justify-between">
        <span className="font-medium">{k.empfaenger || '–'}</span>
        <span className={`font-mono font-medium ${k.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>{fmt(k.betrag)}</span>
      </div>
      <div className="text-xs text-gray-400 mt-0.5">{k.datum}</div>
    </button>
  )

  return (
    <Modal onClose={onClose} title={istHHBuchung ? 'Haushaltsbuch-Eintrag' : 'HHB verknüpfen'} maxWidth="max-w-lg">

      {/* HH-eigene Buchung → zeige den zugehörigen HHB-Eintrag */}
      {istHHBuchung && (
        hhEintrag ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-gray-200 p-3 space-y-1">
              <div className="flex justify-between items-center">
                <span className="font-medium">{hhEintrag.geschaeft?.name || buchung.empfaenger || '–'}</span>
                <span className="font-mono font-medium text-red-600">{fmt(-hhEintrag.betrag_gesamt)}</span>
              </div>
              <div className="text-xs text-gray-400">{hhEintrag.datum} · {hhEintrag.bezahlart}</div>
              <div className="flex gap-2 mt-1">
                {(() => { const s = ABGLEICH_LABEL[hhEintrag.abgleich_status]; return s ? <span className={`badge ${s.cls}`}>{s.label}</span> : null })()}
              </div>
            </div>
            {hhEintrag.abgleich_status === 'offen' && (
              <button className="btn-primary w-full justify-center" onClick={bestaetigen}>
                Als abgeglichen markieren
              </button>
            )}
            {hhEintrag.abgleich_status === 'verknuepft' && (
              <p className="text-sm text-green-700">Dieser Eintrag ist bereits abgeglichen.</p>
            )}
          </div>
        ) : (
          <p className="text-gray-400 text-sm">Lädt…</p>
        )
      )}

      {/* Nicht-HH-Buchung → suche passende HHB-Einträge */}
      {!istHHBuchung && (
        <>
          {buchung.verknuepft_mit_id && (
            <div className="rounded-lg border border-teal-200 bg-teal-50 p-3 space-y-2">
              <div className="text-xs font-medium text-teal-700">Aktuell verknüpft</div>
              {verknuepft ? (
                <div className="flex justify-between items-center">
                  <div>
                    <div className="font-medium">{verknuepft.empfaenger || '–'}</div>
                    <div className="text-xs text-gray-400 mt-0.5">{verknuepft.datum}</div>
                  </div>
                  <span className={`font-mono font-medium ${verknuepft.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>{fmt(verknuepft.betrag)}</span>
                </div>
              ) : (
                <div className="text-sm text-gray-400">Lädt…</div>
              )}
              <button className="btn-danger w-full justify-center" onClick={loese}>Verknüpfung lösen</button>
            </div>
          )}
          {!buchung.verknuepft_mit_id && (
            <>
              {kandidaten.length > 0 && (
                <div className="text-xs text-gray-400 font-medium uppercase tracking-wide">Automatische Vorschläge</div>
              )}
              {kandidaten.map(k => <KandidatButton key={k.id} k={k} />)}
              <div>
                <div className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-1">
                  {kandidaten.length === 0 ? 'Keine Vorschläge – manuell suchen' : 'Oder manuell suchen'}
                </div>
                <input
                  className="input"
                  placeholder="Empfänger suchen…"
                  value={suchText}
                  onChange={e => setSuchText(e.target.value)}
                  autoFocus={kandidaten.length === 0}
                />
              </div>
              {suchErgebnisse.map(k => <KandidatButton key={k.id} k={k} />)}
              {suchText.trim() && suchErgebnisse.length === 0 && (
                <p className="text-gray-400 text-sm">Keine Buchungen gefunden</p>
              )}
            </>
          )}
        </>
      )}

    </Modal>
  )
}

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

function fmtDatum(s) {
  if (!s) return '–'
  // ISO yyyy-MM-dd: identisch zur serverseitigen Sortierung, keine Format-Diskrepanz
  return s
}

// Der Status "gebucht + geplant bis Monatsende" ist eine Frontend-Abkuerzung und
// wird hier in die Filterfelder uebersetzt, die das Backend kennt. Liste und
// Mehrfachaenderung nutzen dieselbe Aufloesung, damit "alle gefilterten" genau
// die Buchungen trifft, die auch angezeigt werden.
function resolveFilter(filter) {
  const m = filter.status?.match(/^gebucht_geplant_m(\d)$/)
  if (!m) return filter
  const now = new Date()
  const bis = new Date(now.getFullYear(), now.getMonth() + Number(m[1]) + 1, 0)
  const pad = (n) => String(n).padStart(2, '0')
  return {
    ...filter,
    status: '',
    datum_von: '',
    geplant_ab: new Date().toISOString().slice(0, 10),
    datum_bis: `${bis.getFullYear()}-${pad(bis.getMonth() + 1)}-${pad(bis.getDate())}`,
  }
}

// Setzt Kategorie, Empfaenger oder Status fuer viele Buchungen auf einmal.
// Nur angehakte Felder werden uebertragen - alles andere bleibt unangetastet.
// Ein Knopf statt drei: die Typ-Auswahl klappt darunter auf.
// CSV und Excel laedt der Browser direkt, PDF entsteht aus der Druckansicht.
const EXPORT_TYPEN = [
  { typ: 'csv', text: 'CSV', hinweis: 'Trennzeichen-Datei' },
  { typ: 'xlsx', text: 'Excel', hinweis: 'Arbeitsmappe .xlsx' },
  { typ: 'html', text: 'PDF', hinweis: 'Druckansicht – dort als PDF speichern' },
]

function ExportMenu({ url }) {
  const [offen, setOffen] = useState(false)
  const bereich = useRef(null)

  useEffect(() => {
    if (!offen) return
    const beiKlickAussen = (e) => {
      if (bereich.current && !bereich.current.contains(e.target)) setOffen(false)
    }
    const beiEscape = (e) => { if (e.key === 'Escape') setOffen(false) }
    document.addEventListener('mousedown', beiKlickAussen)
    document.addEventListener('keydown', beiEscape)
    return () => {
      document.removeEventListener('mousedown', beiKlickAussen)
      document.removeEventListener('keydown', beiEscape)
    }
  }, [offen])

  const waehlen = (typ) => {
    setOffen(false)
    if (typ === 'html') window.open(url(typ), '_blank')
    else window.location.href = url(typ)
  }

  return (
    <div className="relative" ref={bereich}>
      <button
        className="btn-secondary"
        title="Alle gefilterten Zeilen exportieren"
        onClick={() => setOffen((o) => !o)}
      >
        Export <span className="text-xs">▾</span>
      </button>
      {offen && (
        <div className="absolute left-0 sm:left-auto sm:right-0 mt-1 z-20 w-56 rounded border border-gray-200 bg-white shadow-lg py-1">
          {EXPORT_TYPEN.map((e) => (
            <button
              key={e.typ}
              className="block w-full text-left px-3 py-2 hover:bg-gray-50"
              onClick={() => waehlen(e.typ)}
            >
              <span className="font-medium">{e.text}</span>
              <span className="block text-xs text-gray-500">{e.hinweis}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MehrfachAendernDialog({ anzahl, kategorien, empfaenger, onClose, onSave }) {
  const [aktiv, setAktiv] = useState({ kategorie_id: false, empfaenger_id: false, status: false })
  const [werte, setWerte] = useState({ kategorie_id: null, empfaenger_id: null, status: 'gebucht' })
  const [laeuft, setLaeuft] = useState(false)

  const umschalten = (f) => setAktiv((a) => ({ ...a, [f]: !a[f] }))
  const gewaehlt = Object.entries(aktiv).filter(([, v]) => v).map(([k]) => k)

  const speichern = async () => {
    const felder = {}
    for (const f of gewaehlt) {
      felder[f] = werte[f]
      // Der Empfaengername steht als Text an der Buchung und muss mitgezogen
      // werden, sonst zeigt die Liste weiter den alten Namen.
      if (f === 'empfaenger_id') felder.empfaenger = empfaenger.find((e) => e.id === werte.empfaenger_id)?.name ?? null
    }
    setLaeuft(true)
    try { await onSave(felder) } finally { setLaeuft(false) }
  }

  return (
    <Modal onClose={onClose} title={`${anzahl} Buchung${anzahl !== 1 ? 'en' : ''} ändern`}>
      <div className="space-y-3">
        <div>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="haken" checked={aktiv.kategorie_id} onChange={() => umschalten('kategorie_id')} />
            <span className="label mb-0">Kategorie setzen</span>
          </label>
          {aktiv.kategorie_id && (
            <div className="mt-1">
              <KategorieSelect
                kategorien={kategorien}
                value={werte.kategorie_id}
                onChange={(id) => setWerte((w) => ({ ...w, kategorie_id: id }))}
              />
            </div>
          )}
        </div>
        <div>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="haken" checked={aktiv.empfaenger_id} onChange={() => umschalten('empfaenger_id')} />
            <span className="label mb-0">Empfänger setzen</span>
          </label>
          {aktiv.empfaenger_id && (
            <select
              className="input mt-1"
              value={werte.empfaenger_id ?? ''}
              onChange={(e) => setWerte((w) => ({ ...w, empfaenger_id: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">– keiner –</option>
              {empfaenger.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          )}
        </div>
        <div>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="haken" checked={aktiv.status} onChange={() => umschalten('status')} />
            <span className="label mb-0">Status setzen</span>
          </label>
          {aktiv.status && (
            <select className="input mt-1" value={werte.status} onChange={(e) => setWerte((w) => ({ ...w, status: e.target.value }))}>
              <option value="gebucht">gebucht</option>
              <option value="geplant">geplant</option>
            </select>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-secondary" onClick={onClose}>Abbrechen</button>
          <button className="btn-primary" disabled={gewaehlt.length === 0 || laeuft} onClick={speichern}>
            {laeuft ? 'Ändert…' : 'Ändern'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// Status- und Herkunfts-Badges. Von Tabelle und Karte gemeinsam genutzt, damit
// beide Darstellungen nicht auseinanderlaufen.
function StatusBadges({ b, hhbAktiv, onJetztBuchen, onTransfer, onHhb }) {
  return (
    <div className="flex gap-1 flex-wrap">
      {b.status === 'geplant'
        ? <span className="badge badge-blue cursor-pointer" title="Doppelklick: jetzt buchen" onDoubleClick={() => onJetztBuchen(b)}>geplant</span>
        : <span className="badge badge-green">gebucht</span>}
      {b.quelle === 'import' && <span className="badge bg-sky-100 text-sky-800" title="Via Kontoauszug importiert">↓ Import</span>}
      {b.ist_transfer && <span className="badge bg-purple-100 text-purple-800 cursor-pointer" onClick={() => onTransfer(b)}>Transfer</span>}
      {hhbAktiv && b.verknuepft_mit_id && <span className="badge bg-teal-100 text-teal-800 cursor-pointer" onClick={() => onHhb(b)}>HHB ✓</span>}
      {hhbAktiv && b.quelle === 'haushaltsbuch' && (() => {
        const s = b.hh_abgleich_status
        if (s === 'verknuepft') return <span className="badge bg-green-100 text-green-800 cursor-pointer" onClick={() => onHhb(b)}>HHB ✓</span>
        if (s === 'offen') return <span className="badge bg-orange-100 text-orange-800 cursor-pointer" onClick={() => onHhb(b)}>HHB offen</span>
        if (s === 'bar_ohne_konto') return <span className="badge bg-gray-100 text-gray-600 cursor-pointer" onClick={() => onHhb(b)}>HHB bar</span>
        return <span className="badge bg-orange-100 text-orange-800 cursor-pointer" onClick={() => onHhb(b)}>HHB</span>
      })()}
    </div>
  )
}

function ZeilenAktionen({ b, hhbAktiv, onEdit, onTransfer, onHhb, onDelete }) {
  return (
    <>
      <button className="btn-secondary btn-icon mr-1" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => onEdit(b)}><PencilIcon /></button>
      <button className="btn-secondary btn-sm h-9 mr-1" title="Transfer verknüpfen" onClick={() => onTransfer(b)}>⇄</button>
      {hhbAktiv && <button className="btn-secondary btn-sm h-9 mr-1" title="Haushaltsbuch verknüpfen" onClick={() => onHhb(b)}>HH</button>}
      <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => onDelete(b.id)}>×</button>
    </>
  )
}

// Mobile Darstellung einer Buchung: alles Entscheidungsrelevante ohne
// horizontales Scrollen und ohne Aufklappen sichtbar.
function BuchungKarte({ b, katName, kontoName, ausgewaehlt, mehrfachModus, onToggle, ...rest }) {
  return (
    <div className={`border-b px-3 py-2.5 ${ausgewaehlt ? 'bg-blue-100' : 'odd:bg-white even:bg-gray-50'}`}>
      <div className="flex items-start gap-2">
        {mehrfachModus && (
          <input type="checkbox" checked={ausgewaehlt} onChange={() => onToggle(b.id)} className="haken mt-1" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-medium truncate">{b.empfaenger ?? <span className="text-gray-400">–</span>}</span>
            <span className={`font-mono font-semibold whitespace-nowrap ${b.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
              {fmt(b.betrag)}
            </span>
          </div>
          <div className="mt-0.5 text-xs text-gray-500">
            <span className="tabular-nums">{fmtDatum(b.datum)}</span>
            <span> · {katName ?? '–'}</span>
            <span> · {kontoName ?? '–'}</span>
          </div>
          {b.notiz && <div className="mt-0.5 text-xs text-gray-400 truncate">{b.notiz}</div>}
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <StatusBadges b={b} {...rest} />
            <div className="flex shrink-0 items-center">
              <ZeilenAktionen b={b} {...rest} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Buchungen() {
  const { confirm, dialog } = useConfirm()
  const [items, setItems] = useState([])
  const [gesamt, setGesamt] = useState(0)
  const [kontostand, setKontostand] = useState(null)
  // { saldo, stichtag }: der rein gebuchte Stand zum Filter-Enddatum, fuer den
  // Abgleich mit dem Kontoauszug. Der Stichtag gehoert in den State, weil er in
  // der Beschriftung steht und nur load() ihn aufloesen kann.
  const [standGebucht, setStandGebucht] = useState(null)
  const [standFilterEnde, setStandFilterEnde] = useState(null)
  const [standJahresende, setStandJahresende] = useState(null)
  const [prognose, setPrognose] = useState(null)
  const [seite, setSeite] = useState(1)
  const proSeite = 50

  const FILTER_STORAGE_KEY = 'buchungen_filter'
  const filterDefault = { konto_id: '', kategorie_id: '', nur_diese_kategorie: '', datum_von: '', datum_bis: '', suche: '', status: '' }
  const [filter, setFilter] = useState(() => {
    try { return { ...filterDefault, ...JSON.parse(sessionStorage.getItem(FILTER_STORAGE_KEY) || '{}') } }
    catch { return filterDefault }
  })
  const [konten, setKonten] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [empfaengerListe, setEmpfaengerListe] = useState([])
  const [projekte, setProjekte] = useState([])

  const [showForm, setShowForm] = useState(false)
  const [editItem, setEditItem] = useState(null)
  const [transferItem, setTransferItem] = useState(null)
  const [hhItem, setHhItem] = useState(null)
  const [loading, setLoading] = useState(false)
  const hhbAktiv = !(() => { try { return JSON.parse(localStorage.getItem('versteckte_module') || '[]') } catch { return [] } })().includes('/haushaltsbuch')
  const [auswahl, setAuswahl] = useState(new Set())
  const [mehrfachModus, setMehrfachModus] = useState(false)
  // true = nicht die angehakten Zeilen, sondern alle Treffer des aktuellen Filters
  const [alleGefiltert, setAlleGefiltert] = useState(false)
  const [aendernOffen, setAendernOffen] = useState(false)

  useEffect(() => {
    sessionStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filter))
  }, [filter])

  // Filter aus der URL, damit eine Erinnerung auf dem Dashboard direkt auf die
  // gemeinten Buchungen zeigen kann. Der gemerkte Filter wird dabei ersetzt,
  // nicht ergaenzt - sonst schraenkt ein alter Kontofilter das Ergebnis ein,
  // ohne dass man es dem Link ansieht. Danach die Parameter aus der Adresse
  // nehmen, sonst kaemen sie beim Zuruecksetzen wieder.
  const [suchParams, setSuchParams] = useSearchParams()
  useEffect(() => {
    const uebernommen = Object.fromEntries(
      [...suchParams].filter(([k]) => k in filterDefault),
    )
    if (Object.keys(uebernommen).length === 0) return
    setFilter({ ...filterDefault, ...uebernommen })
    setSeite(1)
    setSuchParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    kontenApi.list(false).then((r) => setKonten(r.data))
    kategorienApi.flat().then((r) => setKategorien(r.data))
    projekteApi.list().then((r) => setProjekte(r.data))
    empfaengerApi.list().then((r) => setEmpfaengerListe(r.data))
  }, [])

  // Laufende Nummer gegen ueberholende Antworten: aendert sich der Filter,
  // waehrend die vorige Abfrage noch laeuft, darf deren spaeter eintreffendes
  // Ergebnis die Liste nicht mehr ueberschreiben.
  const ladeNr = useRef(0)

  const load = useCallback(() => {
    const nr = ++ladeNr.current
    const aktuell = () => nr === ladeNr.current
    setLoading(true)
    setAuswahl(new Set())
    const heute = new Date().toISOString().slice(0, 10)
    const monatBis = (offset) => {
      const now = new Date()
      const bis = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0)
      const pad = (n) => String(n).padStart(2, '0')
      return `${bis.getFullYear()}-${pad(bis.getMonth() + 1)}-${bis.getDate()}`
    }
    const kombiniertMatch = filter.status?.match(/^gebucht_geplant_m(\d)$/)
    const resolvedFilter = resolveFilter(filter)
    const params = { seite, pro_seite: proSeite, ...Object.fromEntries(Object.entries(resolvedFilter).filter(([, v]) => v !== '')) }
    buchungenApi.list(params)
      .then((r) => {
        if (!aktuell()) return
        setItems(r.data.items); setGesamt(r.data.gesamt)
      })
      .finally(() => { if (aktuell()) setLoading(false) })

    if (filter.konto_id) {
      kontenApi.saldo(filter.konto_id).then((r) => {
        if (!aktuell()) return
        const stand = r.data.saldo
        setKontostand(stand)
        if (kombiniertMatch) {
          buchungenApi.list({ konto_id: filter.konto_id, status: 'geplant', datum_von: heute, datum_bis: monatBis(Number(kombiniertMatch[1])), pro_seite: 1 })
            .then((rg) => { if (aktuell()) setPrognose(Math.round((stand + rg.data.summe) * 100) / 100) })
        } else {
          setPrognose(null)
        }
      })
      // Geplante ab heute: ueberfaellige, nie gebuchte Planposten bleiben aussen vor
      if (resolvedFilter.datum_bis) {
        // Ohne geplant_ab zaehlen nur gebuchte Buchungen - genau das steht auch
        // auf dem Kontoauszug. Kategorie-, Such-, Projekt- und Statusfilter
        // gehen bewusst nicht ein: abgeglichen wird das ganze Konto.
        const stichtag = resolvedFilter.datum_bis
        kontenApi.saldo(filter.konto_id, stichtag)
          .then((r) => { if (aktuell()) setStandGebucht({ saldo: r.data.saldo, stichtag }) })
        kontenApi.saldo(filter.konto_id, resolvedFilter.datum_bis, heute)
          .then((r) => { if (aktuell()) setStandFilterEnde(r.data.saldo) })
      } else {
        setStandGebucht(null)
        setStandFilterEnde(null)
      }
      const jahresende = `${new Date().getFullYear()}-12-31`
      kontenApi.saldo(filter.konto_id, jahresende, heute)
        .then((r) => { if (aktuell()) setStandJahresende(r.data.saldo) })
    } else {
      setKontostand(null)
      setStandGebucht(null)
      setStandFilterEnde(null)
      setStandJahresende(null)
      setPrognose(null)
    }
  }, [seite, filter])

  const patchItems = (patches) => setItems(prev => prev.map(b => {
    const p = patches.find(u => u.id === b.id)
    return p ? { ...b, ...p } : b
  }))

  const beendeMehrfachModus = () => { setMehrfachModus(false); setAuswahl(new Set()); setAlleGefiltert(false) }

  const handleJetztBuchen = async (b) => {
    const r = await buchungenApi.update(b.id, { status: 'gebucht' })
    patchItems([r.data])
  }

  useEffect(() => { load() }, [load])

  const handleSave = (updatedBuchung) => {
    setShowForm(false)
    setEditItem(null)
    if (updatedBuchung?.id) patchItems([updatedBuchung])
    else load()
  }
  const handleEdit = (b) => { setEditItem(b); setShowForm(true) }
  const handleDelete = async (id) => {
    if (!await confirm('Buchung löschen?')) return
    await buchungenApi.delete(id)
    load()
  }
  const handleDeleteBulk = async () => {
    const ids = [...auswahl]
    if (!await confirm(`${ids.length} Buchung${ids.length !== 1 ? 'en' : ''} löschen?`)) return
    await buchungenApi.deleteBulk(ids)
    beendeMehrfachModus()
    load()
  }

  const handleAendernBulk = async (felder) => {
    const anzahl = alleGefiltert ? gesamt : auswahl.size
    const was = Object.keys(felder).length === 1 ? 'Feld' : 'Felder'
    if (!await confirm(`${anzahl} Buchung${anzahl !== 1 ? 'en' : ''}: ${Object.keys(felder).length} ${was} ändern?`, { knopf: 'Ändern', gefahr: false })) return
    const body = alleGefiltert
      ? { alle_gefilterten: true, filter: Object.fromEntries(Object.entries(resolveFilter(filter)).filter(([, v]) => v !== '')) }
      : { ids: [...auswahl] }
    const r = await buchungenApi.updateBulk({ ...body, ...felder })
    setAendernOffen(false)
    beendeMehrfachModus()
    load()
    return r.data.geaendert
  }

  const toggleAuswahl = (id) => setAuswahl(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  // Gemeinsame Handler fuer Tabellenzeile und Karte
  const zeilenProps = {
    hhbAktiv,
    onJetztBuchen: handleJetztBuchen,
    onTransfer: setTransferItem,
    onHhb: setHhItem,
    onEdit: handleEdit,
    onDelete: handleDelete,
  }

  const alleAusgewaehlt = items.length > 0 && items.every(b => auswahl.has(b.id))
  const toggleAlle = () => setAuswahl(alleAusgewaehlt ? new Set() : new Set(items.map(b => b.id)))

  const setF = (k, v) => { setFilter((f) => ({ ...f, [k]: v })); setSeite(1) }

  // Hat die gewaehlte Kategorie Kinder? Nur dann ist "nur diese Kategorie"
  // ueberhaupt eine Einschraenkung. Die Liste enthaelt nur aktive Kategorien;
  // hat ein Knoten ausschliesslich deaktivierte Kinder, bleibt der Haken
  // verborgen und es gilt die Vorgabe - die Buchungen zaehlen also mit.
  const hatUnterkategorien = useMemo(
    () => filter.kategorie_id !== ''
      && kategorien.some((k) => String(k.uebergeordnet_id) === String(filter.kategorie_id)),
    [filter.kategorie_id, kategorien],
  )
  const pages = Math.ceil(gesamt / proSeite)

  const monate = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
  const aktiverMonat = (() => {
    if (!filter.datum_von || !filter.datum_bis) return null
    const von = new Date(filter.datum_von)
    const bis = new Date(filter.datum_bis)
    const letzterTag = new Date(von.getFullYear(), von.getMonth() + 1, 0).getDate()
    if (von.getDate() === 1 && bis.getDate() === letzterTag && von.getMonth() === bis.getMonth() && von.getFullYear() === bis.getFullYear())
      return `${von.getFullYear()}-${von.getMonth()}`
    return null
  })()
  const aktivesJahr = filter.datum_von ? new Date(filter.datum_von).getFullYear() : new Date().getFullYear()

  const waehleMonat = (monatIdx, jahr) => {
    const von = `${jahr}-${String(monatIdx + 1).padStart(2, '0')}-01`
    const letzterTag = new Date(jahr, monatIdx + 1, 0).getDate()
    const bis = `${jahr}-${String(monatIdx + 1).padStart(2, '0')}-${letzterTag}`
    setFilter((f) => ({ ...f, datum_von: von, datum_bis: bis }))
    setSeite(1)
  }

  return (
    <div className="p-4 md:p-6 space-y-4">
      {/* Auf dem Handy stehen die Schaltflaechen unter dem Titel: nebeneinander
          passten sie nicht auf die Breite, "+ Neu" lag ausserhalb des Bildes. */}
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-xl font-bold">
            Buchungen <span className="text-gray-400 text-base font-normal">({gesamt})</span>
          </h2>
          <div className="mt-1 space-y-0.5">
            {kontostand !== null && (
              <div className="text-sm">
                <span className="text-gray-500">Kontostand (inkl. Startsaldo): </span>
                <span className="font-semibold text-blue-700">{fmt(kontostand)}</span>
              </div>
            )}
            {standGebucht !== null && (
              <div className="text-sm">
                <span className="text-gray-500">Kontostand (gebucht) am {fmtDatum(standGebucht.stichtag)}: </span>
                <span className="font-semibold text-blue-700">{fmt(standGebucht.saldo)}</span>
              </div>
            )}
            {standFilterEnde !== null && (
              <div className="text-sm">
                <span className="text-gray-500">inkl. geplanter Buchungen bis Filter-Enddatum: </span>
                <span className="font-semibold text-blue-700">{fmt(standFilterEnde)}</span>
              </div>
            )}
            {standJahresende !== null && (
              <div className="text-sm">
                <span className="text-gray-500">inkl. geplanter Buchungen bis Jahresende: </span>
                <span className="font-semibold text-blue-700">{fmt(standJahresende)}</span>
              </div>
            )}
            {prognose !== null && (
              <div className="text-sm">
                <span className="text-gray-500">Prognose (Kontostand + geplante Buchungen des Monats): </span>
                <span className="font-semibold text-violet-700">{fmt(prognose)}</span>
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 items-center shrink-0">
          {mehrfachModus ? (
            <>
              {(auswahl.size > 0 || alleGefiltert) && (
                <>
                  <button className="btn-secondary" onClick={() => setAendernOffen(true)}>
                    {alleGefiltert ? `alle ${gesamt}` : auswahl.size} ändern
                  </button>
                  <button className="btn-danger" onClick={handleDeleteBulk} disabled={alleGefiltert}>
                    {alleGefiltert ? 'löschen' : `${auswahl.size} löschen`}
                  </button>
                </>
              )}
              <button className="btn-secondary" onClick={beendeMehrfachModus}>Abbrechen</button>
            </>
          ) : (
            <>
              <ExportMenu url={(typ) => buchungenApi.exportUrl(typ, resolveFilter(filter))} />
              <button className="btn-secondary" onClick={() => setMehrfachModus(true)}>Mehrfach bearbeiten</button>
              <button className="btn-primary" onClick={() => { setEditItem(filter.konto_id ? { konto_id: Number(filter.konto_id) } : null); setShowForm(true) }}>+ Neu</button>
            </>
          )}
        </div>
      </div>

      {/* Monats-Schnellauswahl */}
      <div className="card py-2 px-3 flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1">
          <button className="text-gray-400 hover:text-gray-700 px-1 font-bold" onClick={() => waehleMonat(aktiverMonat ? new Date(filter.datum_von).getMonth() : new Date().getMonth(), aktivesJahr - 1)}>‹</button>
          <span className="text-sm font-semibold text-gray-600 w-10 text-center">{aktivesJahr}</span>
          <button className="text-gray-400 hover:text-gray-700 px-1 font-bold" onClick={() => waehleMonat(aktiverMonat ? new Date(filter.datum_von).getMonth() : new Date().getMonth(), aktivesJahr + 1)}>›</button>
        </div>
        <div className="flex gap-1 flex-wrap">
          {monate.map((m, i) => {
            const key = `${aktivesJahr}-${i}`
            return (
              <button
                key={key}
                onClick={() => waehleMonat(i, aktivesJahr)}
                className={`px-2 py-0.5 rounded text-sm font-medium transition-colors ${aktiverMonat === key ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
              >{m}</button>
            )
          })}
        </div>
      </div>

      {/* Filter */}
      <div className="card grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className="label">Suche</label>
          <input className="input" placeholder="Empfänger, Notiz…" value={filter.suche} onChange={(e) => setF('suche', e.target.value)} />
        </div>
        <div>
          <label className="label">Konto</label>
          {/* Filter zeigt bewusst auch inaktive Konten – die Historie muss durchsuchbar bleiben. */}
          <select className="input" value={filter.konto_id} onChange={(e) => setF('konto_id', e.target.value)}>
            <option value="">Alle</option>
            {konten.map((k) => (
              <option key={k.id} value={k.id}>{k.name}{k.aktiv ? '' : ' (inaktiv)'}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Kategorie</label>
          <KategorieSelect
            kategorien={kategorien}
            value={filter.kategorie_id}
            onChange={(id) => {
              setFilter((f) => ({ ...f, kategorie_id: id ?? '', nur_diese_kategorie: '' }))
              setSeite(1)
            }}
            placeholder="Alle"
          />
          {/* Nur zeigen, wenn es etwas einzuschraenken gibt. Ohne Haken zaehlen
              die Unterkategorien mit - an einem Knoten mit Kindern haengen
              meist keine Buchungen direkt, der Filter liefe sonst ins Leere. */}
          {hatUnterkategorien && (
            <label className="flex items-center gap-2 mt-1 text-sm text-gray-600">
              <input
                type="checkbox"
                role="switch"
                className="schieber schieber-sm"
                checked={filter.nur_diese_kategorie === '1'}
                onChange={(e) => setF('nur_diese_kategorie', e.target.checked ? '1' : '')}
              />
              nur diese Kategorie
            </label>
          )}
        </div>
        <div>
          <label className="label">Status</label>
          <select className="input" value={filter.status} onChange={(e) => setF('status', e.target.value)}>
            <option value="">Alle</option>
            <option value="gebucht">Gebucht</option>
            <option value="geplant">Geplant</option>
            <option value="gebucht_geplant_m0">Gebucht + Geplant (dieser Monat)</option>
            <option value="gebucht_geplant_m1">Gebucht + Geplant (nächster Monat)</option>
            <option value="gebucht_geplant_m2">Gebucht + Geplant (+2 Monate)</option>
            <option value="gebucht_geplant_m3">Gebucht + Geplant (+3 Monate)</option>
          </select>
        </div>
        <div>
          <label className="label">Von</label>
          <input className="input" type="date" value={filter.datum_von} onChange={(e) => setF('datum_von', e.target.value)} />
        </div>
        <div>
          <label className="label">Bis</label>
          <input className="input" type="date" value={filter.datum_bis} onChange={(e) => setF('datum_bis', e.target.value)} />
        </div>
        <div className="col-span-2 md:col-span-1 flex items-end">
          <button className="btn-secondary w-full justify-center" onClick={() => { setFilter(filterDefault); setSeite(1) }}>
            Filter zurücksetzen
          </button>
        </div>
      </div>

      {/* Auswahl-Hinweis im Mehrfach-Modus */}
      {mehrfachModus && (
        <div className="card py-2 px-3 text-sm flex flex-wrap items-center gap-x-3 gap-y-1">
          {alleGefiltert ? (
            <>
              <span>Alle <b>{gesamt}</b> gefilterten Buchungen sind ausgewählt.</span>
              <button className="text-blue-700 hover:underline" onClick={() => setAlleGefiltert(false)}>Auswahl aufheben</button>
            </>
          ) : (
            <>
              <span><b>{auswahl.size}</b> auf dieser Seite ausgewählt.</span>
              {gesamt > items.length && (
                <button className="text-blue-700 hover:underline" onClick={() => setAlleGefiltert(true)}>
                  Alle {gesamt} gefilterten auswählen
                </button>
              )}
              {auswahl.size > 0 && (
                <button className="text-blue-700 hover:underline" onClick={() => setAuswahl(new Set())}>Auswahl aufheben</button>
              )}
            </>
          )}
        </div>
      )}

      {/* Tabelle (ab md) */}
      <div className="card p-0 overflow-x-auto hidden md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b bg-gray-50 text-xs uppercase tracking-wide">
              {mehrfachModus && (
                <th className="px-3 py-2">
                  <input type="checkbox" checked={alleAusgewaehlt} onChange={toggleAlle} className="haken" />
                </th>
              )}
              <th className="px-3 py-2 font-medium">Datum ↓</th>
              <th className="px-3 py-2 font-medium">Empfänger ↑</th>
              <th className="px-3 py-2 font-medium">Kategorie</th>
              <th className="px-3 py-2 font-medium">Konto</th>
              <th className="px-3 py-2 font-medium text-right">Betrag</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={mehrfachModus ? 8 : 7} className="px-3 py-6 text-center text-gray-400">Lädt…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={mehrfachModus ? 8 : 7} className="px-3 py-6 text-center text-gray-400">Keine Buchungen gefunden</td></tr>
            )}
            {!loading && items.map((b) => {
              const kat = kategorien.find((k) => k.id === b.kategorie_id)
              const konto = konten.find((k) => k.id === b.konto_id)
              return (
                <tr key={b.id} className={`border-b hover:bg-blue-50 ${auswahl.has(b.id) ? 'bg-blue-100' : 'odd:bg-white even:bg-gray-50'}`}>
                  {mehrfachModus && (
                    <td className="px-3 py-2">
                      <input type="checkbox" checked={auswahl.has(b.id)} onChange={() => toggleAuswahl(b.id)} className="haken" />
                    </td>
                  )}
                  <td className="px-3 py-2 text-gray-500 tabular-nums whitespace-nowrap">{fmtDatum(b.datum)}</td>
                  <td className="px-3 py-2 max-w-[200px] truncate">
                    {b.empfaenger ?? <span className="text-gray-400">–</span>}
                    {b.notiz && <span className="ml-1 text-gray-400 text-xs">· {b.notiz}</span>}
                  </td>
                  <td className="px-3 py-2 text-gray-500">{kat?.name ?? '–'}</td>
                  <td className="px-3 py-2 text-gray-500">{konto?.name ?? '–'}</td>
                  <td className={`px-3 py-2 text-right font-mono font-medium ${b.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                    {fmt(b.betrag)}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadges b={b} {...zeilenProps} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-right">
                    <ZeilenAktionen b={b} {...zeilenProps} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Karten (unter md) */}
      <div className="card p-0 md:hidden">
        {mehrfachModus && (
          <label className="flex items-center gap-2 border-b bg-gray-50 px-3 py-2 text-xs uppercase tracking-wide text-gray-500">
            <input type="checkbox" checked={alleAusgewaehlt} onChange={toggleAlle} className="haken" />
            Alle auf dieser Seite
          </label>
        )}
        {loading && <div className="px-3 py-6 text-center text-gray-400">Lädt…</div>}
        {!loading && items.length === 0 && (
          <div className="px-3 py-6 text-center text-gray-400">Keine Buchungen gefunden</div>
        )}
        {!loading && items.map((b) => (
          <BuchungKarte
            key={b.id}
            b={b}
            katName={kategorien.find((k) => k.id === b.kategorie_id)?.name}
            kontoName={konten.find((k) => k.id === b.konto_id)?.name}
            ausgewaehlt={auswahl.has(b.id)}
            mehrfachModus={mehrfachModus}
            onToggle={toggleAuswahl}
            {...zeilenProps}
          />
        ))}
      </div>

      {/* Paginierung */}
      {pages > 1 && (
        <div className="flex gap-2 items-center justify-center">
          <button className="btn-secondary btn-sm" disabled={seite === 1} onClick={() => setSeite(1)} title="Erste Seite">«</button>
          <button className="btn-secondary btn-sm" disabled={seite === 1} onClick={() => setSeite((p) => p - 1)}>‹</button>
          <span className="text-sm text-gray-600">{seite} / {pages}</span>
          <button className="btn-secondary btn-sm" disabled={seite === pages} onClick={() => setSeite((p) => p + 1)}>›</button>
          <button className="btn-secondary btn-sm" disabled={seite === pages} onClick={() => setSeite(pages)} title="Letzte Seite">»</button>
        </div>
      )}

      {/* Dialoge */}
      {aendernOffen && (
        <MehrfachAendernDialog
          anzahl={alleGefiltert ? gesamt : auswahl.size}
          kategorien={kategorien}
          empfaenger={empfaengerListe}
          onClose={() => setAendernOffen(false)}
          onSave={handleAendernBulk}
        />
      )}
      {transferItem && (
        <TransferDialog
          buchung={transferItem}
          konten={konten}
          kategorien={kategorien}
          onClose={() => setTransferItem(null)}
          onDone={patchItems}
        />
      )}
      {hhItem && (
        <HHDialog
          buchung={hhItem}
          onClose={() => setHhItem(null)}
          onDone={patchItems}
        />
      )}
      {dialog}
      {showForm && (
        <BuchungForm
          initial={editItem}
          konten={konten}
          kategorien={kategorien}
          projekte={projekte}
          onSave={handleSave}
          onClose={() => { setShowForm(false); setEditItem(null) }}
        />
      )}
    </div>
  )
}
