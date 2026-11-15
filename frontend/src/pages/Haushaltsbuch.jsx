import { useState, useEffect, useRef } from 'react'
import { useHilfe } from '../HilfeContext'
import { haushaltsbuchApi, geschaefteApi, kontenApi, kategorienApi, belegeApi } from '../api'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'
import CurrencyInput from '../components/CurrencyInput'
import Modal from '../components/Modal'
import { PencilIcon } from '../components/icons'
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, arrayMove,
  useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

// Kombobox mit früher erfassten Artikel-Bezeichnungen (gleiches Muster wie das
// Geschäft-Feld) + Hinweis/Rückgängig, falls die OCR-Bezeichnung automatisch
// korrigiert wurde (gelernte Korrektur oder Fuzzy-Treffer, siehe Backend).
function ArtikelBezeichnungFeld({ value, onChange, vorschlaege = [], className, placeholder = 'Bezeichnung', inputRef, ocrBezeichnung, onRevert }) {
  const [offen, setOffen] = useState(false)
  const gefiltert = vorschlaege
    .filter(v => v.toLowerCase().includes((value || '').toLowerCase()))
    .slice(0, 20)
  const automatischKorrigiert = ocrBezeichnung && ocrBezeichnung.trim().toLowerCase() !== (value || '').trim().toLowerCase()

  return (
    <div className="flex-1 min-w-[8rem] relative">
      <input
        ref={inputRef}
        className={className}
        placeholder={placeholder}
        value={value}
        autoComplete="off"
        onChange={e => onChange(e.target.value)}
        onFocus={() => setOffen(true)}
        onBlur={() => setTimeout(() => setOffen(false), 150)}
      />
      {offen && gefiltert.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-20 mt-1 bg-white border border-gray-300 rounded shadow-lg max-h-48 overflow-y-auto">
          {gefiltert.map(v => (
            <button
              key={v}
              type="button"
              className="w-full text-left px-2 py-1 text-sm hover:bg-blue-50"
              onMouseDown={e => e.preventDefault()}
              onClick={() => { onChange(v); setOffen(false) }}
            >
              {v}
            </button>
          ))}
        </div>
      )}
      {automatischKorrigiert && (
        <p className="text-[10px] text-amber-600 mt-0.5 leading-tight">
          automatisch korrigiert (war „{ocrBezeichnung}") ·{' '}
          <button type="button" className="underline hover:no-underline" onClick={onRevert}>zurücksetzen</button>
        </p>
      )}
    </div>
  )
}

function SortableArtikelZeile({ id, p, idx, kategorien, focusNeuIdx, setPosition, removePosition, vorschlaege }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const rowBg = idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }
  return (
    <div ref={setNodeRef} style={style} className={`flex gap-2 items-start rounded px-1 py-0.5 ${rowBg}`}>
      <button
        type="button"
        className="mt-1.5 cursor-grab text-gray-300 hover:text-gray-500 shrink-0"
        {...attributes}
        {...listeners}
        tabIndex={-1}
        aria-label="Reihenfolge ändern"
      >
        ⠿
      </button>
      <ArtikelBezeichnungFeld
        inputRef={el => { if (focusNeuIdx.current === idx && el) { el.focus(); focusNeuIdx.current = null } }}
        className={`input flex-1 ${rowBg}`}
        placeholder="Bezeichnung"
        value={p.bezeichnung}
        onChange={v => setPosition(idx, 'bezeichnung', v)}
        vorschlaege={vorschlaege}
        ocrBezeichnung={p.ocr_bezeichnung}
        onRevert={() => setPosition(idx, 'bezeichnung', p.ocr_bezeichnung)}
      />
      <input
        className={`input w-16 ${rowBg}`}
        type="number"
        step="0.01"
        placeholder="Menge"
        value={p.menge}
        onChange={e => setPosition(idx, 'menge', e.target.value)}
      />
      <input
        className={`input w-24 ${rowBg}`}
        type="number"
        step="0.01"
        placeholder="EP"
        value={p.einzelpreis !== '' && p.einzelpreis != null ? p.einzelpreis : p.gesamtpreis}
        onChange={e => setPosition(idx, 'einzelpreis', e.target.value)}
      />
      <KategorieSelect
        kategorien={kategorien}
        value={p.kategorie_id}
        onChange={id => setPosition(idx, 'kategorie_id', id)}
        placeholder="Kategorie"
        className="w-32"
        menuAlign="right"
        rowBg={rowBg}
      />
      <button type="button" className="btn-danger btn-sm" onClick={() => removePosition(idx)}>×</button>
    </div>
  )
}

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

const LEERE_POSITION = { bezeichnung: '', menge: 1, einzelpreis: '', gesamtpreis: '', kategorie_id: '' }

const LEER = {
  datum: new Date().toISOString().slice(0, 10),
  geschaeft_name: '',
  betrag_gesamt: '',
  bezahlart: 'bar',
  konto_id: '',
  notiz: '',
  positionen: [],
}

const STATUS_BADGE = {
  bar_ohne_konto: { label: 'Bar', cls: 'badge-gray' },
  offen: { label: 'Offen', cls: 'bg-orange-100 text-orange-800 badge' },
  verknuepft: { label: '✓ Abgeglichen', cls: 'badge-green' },
}

export default function Haushaltsbuch() {
  const { openHilfe } = useHilfe()
  const { confirm, dialog } = useConfirm()
  const [konten, setKonten] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [geschaefte, setGeschaefte] = useState([])
  const [formular, setFormular] = useState(LEER)
  const [foto, setFoto] = useState(null)
  const [fotoVorschau, setFotoVorschau] = useState(null)
  const [letzte, setLetzte] = useState([])
  const [status, setStatus] = useState(null) // 'ok' | 'error' | null
  const [laden, setLaden] = useState(false)
  const [editId, setEditId] = useState(null)
  const [galerie, setGalerie] = useState(null) // { eintragId, belege: [] }
  const [galerieModalOffen, setGalerieModalOffen] = useState(false)
  const [formBelege, setFormBelege] = useState([])
  const [formOcrAn, setFormOcrAn] = useState(false)
  const [zoomBeleg, setZoomBeleg] = useState(null)
  const [ocrLaden, setOcrLaden] = useState(false)
  const [ocrFehler, setOcrFehler] = useState(false)
  const [ocrVorschau, setOcrVorschau] = useState(null) // [{ ausgewaehlt, bezeichnung, menge, einzelpreis, gesamtpreis, kategorie_id }]
  const [ocrHinweis, setOcrHinweis] = useState(null) // { text, fotoWiederholenEmpfohlen }
  const [ocrInfo, setOcrInfo] = useState(null) // { variante, segmentiert, preiszeilen, hatVorschau, eintragId }
  const [ocrKategorieAlle, setOcrKategorieAlle] = useState('')
  const [ocrRohtext, setOcrRohtext] = useState('')
  const [ocrRohtextAn, setOcrRohtextAn] = useState(false)
  const [belegBildHoehe, setBelegBildHoehe] = useState(null)
  const [geschaeftDropdownOffen, setGeschaeftDropdownOffen] = useState(false)
  const [artikelVorschlaege, setArtikelVorschlaege] = useState([]) // bekannte Bezeichnungen des gewählten Geschäfts
  const belegBildRef = useRef(null)
  const geschaeftInputRef = useRef(null)
  const geschaeftDropdownRef = useRef(null)
  const kameraRef = useRef(null)
  const focusNeuIdx = useRef(null)
  const idCounter = useRef(0)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  useEffect(() => {
    kontenApi.list().then(r => setKonten(r.data))
    kategorienApi.flat().then(r => setKategorien(r.data.filter(k => k.art !== 'einnahme')))
    geschaefteApi.list().then(r => setGeschaefte(r.data))
    ladeLetzte()
  }, [])

  useEffect(() => {
    const el = belegBildRef.current
    if (!ocrRohtextAn || !el) {
      setBelegBildHoehe(null)
      return
    }
    const messen = () => setBelegBildHoehe(el.clientHeight)
    messen()
    const observer = new ResizeObserver(messen)
    observer.observe(el)
    return () => observer.disconnect()
  }, [ocrRohtextAn, ocrInfo])

  useEffect(() => {
    if (!geschaeftDropdownOffen) return
    const handleClickOutside = (e) => {
      if (geschaeftDropdownRef.current && !geschaeftDropdownRef.current.contains(e.target)) {
        setGeschaeftDropdownOffen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [geschaeftDropdownOffen])

  // Bekannte Artikel-Bezeichnungen des gewählten Geschäfts für die Kombobox
  // bei manuell hinzugefügten Artikel-Zeilen (OCR-Vorschau bekommt ihre eigene
  // Liste direkt aus der /ocr-Antwort, siehe ocrInfo.bekannteArtikel).
  useEffect(() => {
    const g = geschaefte.find(
      x => x.name.toLowerCase() === (formular.geschaeft_name || '').trim().toLowerCase()
    )
    if (!g) { setArtikelVorschlaege([]); return }
    haushaltsbuchApi.artikelVorschlaege(g.id).then(r => setArtikelVorschlaege(r.data)).catch(() => setArtikelVorschlaege([]))
  }, [formular.geschaeft_name, geschaefte])

  const ladeLetzte = () => {
    haushaltsbuchApi.list({ limit: 20 }).then(r => setLetzte(r.data))
  }

  const set = (k, v) => setFormular(prev => ({ ...prev, [k]: v }))

  const setPosition = (idx, k, v) => {
    setFormular(prev => {
      const positionen = prev.positionen.map((p, i) => {
        if (i !== idx) return p
        const updated = { ...p, [k]: v }
        if (k === 'einzelpreis') {
          const ep = Number(v)
          const m = Number(p.menge) || 1
          if (ep > 0 && m > 0)
            updated.gesamtpreis = String(Math.round(ep * m * 100) / 100)
        } else if (k === 'menge') {
          const newMenge = Number(v) || 1
          const hasEP = p.einzelpreis !== '' && p.einzelpreis != null && Number(p.einzelpreis) > 0
          const prevMengeWar1 = (Number(p.menge) || 1) === 1
          const ep = hasEP
            ? Number(p.einzelpreis)
            : prevMengeWar1 && p.gesamtpreis !== '' ? Number(p.gesamtpreis) : null
          if (ep !== null && ep > 0) {
            if (!hasEP) updated.einzelpreis = String(ep)
            updated.gesamtpreis = String(Math.round(ep * newMenge * 100) / 100)
          }
        }
        return updated
      })
      return { ...prev, positionen }
    })
  }

  const addPosition = () => {
    focusNeuIdx.current = formular.positionen.length
    setFormular(prev => ({ ...prev, positionen: [...prev.positionen, { ...LEERE_POSITION, _id: ++idCounter.current }] }))
  }
  const removePosition = (idx) => setFormular(prev => ({ ...prev, positionen: prev.positionen.filter((_, i) => i !== idx) }))

  const handleDragEnd = ({ active, over }) => {
    if (!over || active.id === over.id) return
    setFormular(prev => {
      const oldIdx = prev.positionen.findIndex(p => p._id === active.id)
      const newIdx = prev.positionen.findIndex(p => p._id === over.id)
      return { ...prev, positionen: arrayMove(prev.positionen, oldIdx, newIdx) }
    })
  }

  const handleFoto = e => {
    const datei = e.target.files[0]
    if (!datei) return
    setFoto(datei)
    setFotoVorschau(URL.createObjectURL(datei))
  }

  const resetOcrState = () => {
    setOcrVorschau(null)
    setOcrFehler(false)
    setOcrHinweis(null)
    setOcrInfo(null)
    setOcrRohtext('')
    setOcrRohtextAn(false)
    setOcrKategorieAlle('')
  }

  const resetForm = () => {
    setFormular(LEER)
    setFoto(null)
    setFotoVorschau(null)
    setEditId(null)
    setFormBelege([])
    setFormOcrAn(false)
    resetOcrState()
  }

  const startEdit = (e) => {
    setEditId(e.id)
    setFormular({
      datum: e.datum,
      geschaeft_name: e.geschaeft?.name ?? '',
      betrag_gesamt: e.betrag_gesamt,
      bezahlart: e.bezahlart,
      konto_id: e.konto_id ?? '',
      notiz: e.notiz ?? '',
      positionen: e.positionen.map(p => ({ ...p, kategorie_id: p.kategorie_id ?? '', _id: ++idCounter.current })),
    })
    setFoto(null)
    setFotoVorschau(null)
    resetOcrState()
    setFormOcrAn(false)
    belegeApi.listEintrag(e.id).then(r => setFormBelege(r.data))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = async (id) => {
    if (!await confirm('Haushaltsbuch-Eintrag löschen?')) return
    await haushaltsbuchApi.delete(id)
    if (editId === id) resetForm()
    ladeLetzte()
  }

  const handleSubmit = async e => {
    e.preventDefault()
    setLaden(true)
    setStatus(null)
    try {
      const bestehendesGeschaeft = geschaefte.find(g => g.name.toLowerCase() === formular.geschaeft_name.trim().toLowerCase())
      const positionen = formular.positionen
        .filter(p => p.bezeichnung.trim())
        .map(p => ({
          bezeichnung: p.bezeichnung,
          menge: Number(p.menge) || 1,
          einzelpreis: p.einzelpreis !== '' ? Number(p.einzelpreis) : null,
          gesamtpreis: Number(p.gesamtpreis) || 0,
          kategorie_id: p.kategorie_id ? Number(p.kategorie_id) : null,
          ocr_bezeichnung: p.ocr_bezeichnung || null,
        }))

      const daten = {
        datum: formular.datum,
        geschaeft_id: bestehendesGeschaeft?.id ?? null,
        geschaeft_name: bestehendesGeschaeft ? null : (formular.geschaeft_name.trim() || null),
        betrag_gesamt: Math.abs(Number(formular.betrag_gesamt)),
        bezahlart: formular.bezahlart,
        konto_id: formular.bezahlart !== 'bar' && formular.konto_id ? Number(formular.konto_id) : null,
        notiz: formular.notiz || null,
        positionen,
      }

      let eintragId
      if (editId) {
        await haushaltsbuchApi.update(editId, daten)
        eintragId = editId
      } else {
        const r = await haushaltsbuchApi.create(daten)
        eintragId = r.data.id
      }

      if (foto) {
        await belegeApi.uploadEintrag(eintragId, foto)
      }

      setStatus('ok')
      resetForm()
      geschaefteApi.list().then(r => setGeschaefte(r.data))
      ladeLetzte()
      setTimeout(() => setStatus(null), 3000)
    } catch {
      setStatus('error')
    } finally {
      setLaden(false)
    }
  }

  const oeffneGalerie = (eintragId) => {
    resetOcrState()
    setGalerieModalOffen(true)
    belegeApi.listEintrag(eintragId).then(r => setGalerie({ eintragId, belege: r.data }))
  }

  const schliesseGalerie = () => {
    setGalerie(null)
    setGalerieModalOffen(false)
  }

  const texterkennung = async (eintragIdParam) => {
    const eintragId = eintragIdParam ?? galerie?.eintragId
    if (!eintragId) return
    setOcrLaden(true)
    setOcrFehler(false)
    setOcrHinweis(null)
    setOcrInfo(null)
    try {
      const r = await haushaltsbuchApi.ocr(eintragId)
      setOcrKategorieAlle('')
      setOcrRohtext(r.data.rohtext || '')
      setOcrVorschau(r.data.positionen.map(p => ({ ...p, ausgewaehlt: true })))
      if (r.data.hinweis) {
        setOcrHinweis({ text: r.data.hinweis, fotoWiederholenEmpfohlen: r.data.foto_wiederholen_empfohlen })
      }
      setOcrInfo({
        variante: r.data.ocr_variante,
        segmentiert: r.data.ocr_segmentiert,
        preiszeilen: r.data.ocr_preiszeilen,
        hatVorschau: r.data.hat_vorschau,
        eintragId,
        bekannteArtikel: r.data.bekannte_artikel || [],
      })
    } catch {
      setOcrFehler(true)
    } finally {
      setOcrLaden(false)
    }
  }

  // Heuristik: Preis am Zeilenende extrahieren (z.B. "Bio Milch 1,15 A")
  const fuegeRohtextZeileHinzu = (zeile) => {
    const preisMatch = zeile.match(/(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*[€e]?\s*[A-Z1-9]?\s*$/)
    const gesamtpreis = preisMatch ? parseFloat(preisMatch[1].replace('.', '').replace(',', '.')) : ''
    const bezeichnung = preisMatch
      ? zeile.slice(0, preisMatch.index).trim().replace(/^[-*\s]+|[-*\s]+$/g, '')
      : zeile.trim()
    if (!bezeichnung && !gesamtpreis) return
    setOcrVorschau(prev => [
      ...(prev || []),
      { bezeichnung, menge: 1, einzelpreis: gesamtpreis, gesamtpreis, kategorie_id: '', ausgewaehlt: true, _id: ++idCounter.current },
    ])
  }

  const setOcrPosition = (idx, k, v) => {
    setOcrVorschau(prev => prev.map((p, i) => i === idx ? { ...p, [k]: v } : p))
  }

  const setOcrKategorieFuerAlle = (kategorieId) => {
    setOcrKategorieAlle(kategorieId)
    setOcrVorschau(prev => prev.map(p => p.kategorie_id ? p : { ...p, kategorie_id: kategorieId }))
  }

  const ocrUebernehmen = async () => {
    const ausgewaehlt = ocrVorschau
      .filter(p => p.ausgewaehlt && p.bezeichnung.trim())
      .map(({ ausgewaehlt: _a, ...p }) => ({ ...p, kategorie_id: p.kategorie_id || '', _id: ++idCounter.current }))

    if (galerie && editId !== galerie.eintragId) {
      const r = await haushaltsbuchApi.get(galerie.eintragId)
      startEdit(r.data)
    }
    setFormular(prev => ({ ...prev, positionen: [...prev.positionen, ...ausgewaehlt] }))
    schliesseGalerie()
    resetOcrState()
  }

  const deleteBeleg = async (belegId) => {
    if (!await confirm('Foto löschen?')) return
    await belegeApi.deleteEintrag(galerie.eintragId, belegId)
    const r = await belegeApi.listEintrag(galerie.eintragId)
    setGalerie({ eintragId: galerie.eintragId, belege: r.data })
  }

  const girokonten = konten.filter(k => k.typ === 'giro' || k.typ === 'spar')
  const positionenSumme = formular.positionen.reduce((s, p) => s + (Number(p.gesamtpreis) || 0), 0)
  // Rest eines teil-erfassten Belegs zählt in der Statistik automatisch auf die
  // Standard-Kategorie des Geschäfts – hier zur Transparenz anzeigen.
  const gewaehltesGeschaeft = geschaefte.find(
    g => g.name.toLowerCase() === (formular.geschaeft_name || '').trim().toLowerCase()
  )
  const oeffneGeschaeftsListe = () => {
    const el = geschaeftInputRef.current
    if (!el) return
    el.focus()
    setGeschaeftDropdownOffen(true)
    try { el.showPicker?.() } catch { /* ignoriert */ }
  }

  const geschaeftGefiltert = geschaefte.filter(g =>
    g.name.toLowerCase().includes((formular.geschaeft_name || '').toLowerCase())
  )

  const standardKatName = kategorien.find(k => k.id === gewaehltesGeschaeft?.standard_kategorie_id)?.name
  const restBetrag = Math.round(((Number(formular.betrag_gesamt) || 0) - positionenSumme) * 100) / 100

  return (
    <div className="p-3 sm:p-6 max-w-full sm:max-w-2xl lg:max-w-5xl xl:max-w-7xl mx-auto">
      <h1 className="text-xl font-bold text-gray-900 mb-4">Haushaltsbuch</h1>
      <p className="text-sm text-gray-500 mb-4">Einkäufe erfassen – mit Geschäft, Artikeln und Kassenzettel-Foto.</p>

      <div className="card p-3 sm:p-5 mb-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Datum + Betrag */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">Datum</label>
              <input
                className="input"
                type="date"
                required
                value={formular.datum}
                onChange={e => set('datum', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Betrag gesamt (EUR)</label>
              <CurrencyInput
                required
                placeholder="0,00"
                value={formular.betrag_gesamt}
                onChange={n => set('betrag_gesamt', n ?? '')}
              />
            </div>
          </div>

          {/* Geschäft */}
          <div>
            <label className="label">Geschäft</label>
            {/* Combobox: Auswahl aus den Stammdaten, freier Text legt ein neues Geschäft an.
                Eigene Dropdown-Liste statt <datalist>, da native Datalists in mobilen
                Browsern (getestet: Chrome Android-Emulation) nicht angezeigt werden. */}
            <div className="relative" ref={geschaeftDropdownRef}>
              <input
                ref={geschaeftInputRef}
                className="input input-combobox pr-9"
                placeholder={`Auswählen oder neu eingeben (${geschaefte.length} vorhanden)`}
                value={formular.geschaeft_name}
                onChange={e => {
                  set('geschaeft_name', e.target.value)
                  setGeschaeftDropdownOffen(true)
                }}
                onFocus={() => setGeschaeftDropdownOffen(true)}
                autoComplete="off"
              />
              <button
                type="button"
                tabIndex={-1}
                aria-label="Geschäfte-Liste anzeigen"
                className="absolute inset-y-0 right-0 flex items-center px-2.5 text-gray-400 hover:text-gray-600"
                onMouseDown={e => e.preventDefault()}
                onClick={oeffneGeschaeftsListe}
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                  <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                </svg>
              </button>
              {geschaeftDropdownOffen && geschaeftGefiltert.length > 0 && (
                <div className="absolute left-0 right-0 top-full z-10 mt-1 bg-white border border-gray-300 rounded shadow-lg max-h-60 overflow-y-auto">
                  {geschaeftGefiltert.map(g => (
                    <button
                      key={g.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-blue-50 focus:bg-blue-50 focus:outline-none"
                      onClick={() => {
                        set('geschaeft_name', g.name)
                        setGeschaeftDropdownOffen(false)
                      }}
                    >
                      {g.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="text-[11px] text-gray-400 mt-1">
              {gewaehltesGeschaeft
                ? 'Bekanntes Geschäft – Standard-Kategorie und Empfänger werden übernommen.'
                : 'Nicht in der Liste? Der eingegebene Name wird als neues Geschäft angelegt.'}
            </p>
          </div>

          {/* Bezahlart */}
          <div>
            <label className="label">Bezahlart</label>
            <div className="flex gap-3">
              {[
                { v: 'bar', l: 'Bar' },
                { v: 'karte', l: 'Karte' },
                { v: 'konto', l: 'Überweisung/Konto' },
              ].map(opt => (
                <label key={opt.v} className="flex items-center gap-1.5 text-sm">
                  <input
                    type="radio"
                    name="bezahlart"
                    value={opt.v}
                    checked={formular.bezahlart === opt.v}
                    onChange={() => set('bezahlart', opt.v)}
                  />
                  {opt.l}
                </label>
              ))}
            </div>
          </div>

          {/* Konto (nur bei karte/konto) */}
          {formular.bezahlart !== 'bar' && (
            <div>
              <label className="label">Konto</label>
              <select
                className="input"
                value={formular.konto_id}
                onChange={e => set('konto_id', e.target.value)}
              >
                <option value="">– auswählen –</option>
                {girokonten.map(k => (
                  <option key={k.id} value={k.id}>{k.name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Artikel */}
          <div>
            <label className="label">Artikel (optional)</label>
            {formular.positionen.length > 0 && (
              <div className="space-y-2 mb-2">
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                  <SortableContext items={formular.positionen.map(p => p._id)} strategy={verticalListSortingStrategy}>
                    {formular.positionen.map((p, idx) => (
                      <SortableArtikelZeile
                        key={p._id}
                        id={p._id}
                        p={p}
                        idx={idx}
                        kategorien={kategorien}
                        focusNeuIdx={focusNeuIdx}
                        setPosition={setPosition}
                        removePosition={removePosition}
                        vorschlaege={artikelVorschlaege}
                      />
                    ))}
                  </SortableContext>
                </DndContext>
                <div className="text-xs text-gray-400 text-right">{formular.positionen.length} Artikel · Artikelsumme: {fmt(positionenSumme)}</div>
                {restBetrag > 0.005 && (
                  <div className="text-xs text-right text-gray-500">
                    Rest {fmt(restBetrag)} →{' '}
                    {standardKatName
                      ? <span className="font-medium text-gray-700">{standardKatName}</span>
                      : <span className="text-amber-600">keine Standard-Kategorie (Geschäft wählen/setzen)</span>}
                    {' · '}
                    <button type="button" onClick={() => openHilfe('haushaltsbuch')} className="text-blue-600 hover:underline">Hilfe dazu</button>
                  </div>
                )}
                {restBetrag < -0.005 && (
                  <div className="text-xs text-right text-amber-600">
                    Artikelsumme übersteigt Belegsumme um {fmt(-restBetrag)}
                  </div>
                )}
              </div>
            )}
            <button type="button" className="btn-secondary btn-sm" onClick={addPosition}>+ Artikel</button>
          </div>

          {/* Notiz */}
          <div>
            <label className="label">Notiz</label>
            <input
              className="input"
              placeholder="Optional"
              value={formular.notiz}
              onChange={e => set('notiz', e.target.value)}
            />
          </div>

          {/* Foto-Upload */}
          <div>
            <label className="label">Kassenzettel-Foto</label>
            <div className="flex items-start gap-3">
              <div className="flex flex-col gap-2">
                <label className="btn btn-secondary btn-sm cursor-pointer">
                  Foto wählen / Kamera
                  <input
                    ref={kameraRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="hidden"
                    onChange={handleFoto}
                  />
                </label>
                {foto && (
                  <button
                    type="button"
                    className="text-xs text-red-500 hover:text-red-700"
                    onClick={() => { setFoto(null); setFotoVorschau(null) }}
                  >
                    Foto entfernen
                  </button>
                )}
              </div>
              {fotoVorschau && (
                <img
                  src={fotoVorschau}
                  alt="Vorschau"
                  className="h-24 w-24 object-cover rounded border border-gray-200"
                />
              )}
            </div>
          </div>

          {/* Belege & Texterkennung – nur im Bearbeitungsmodus */}
          {editId && (
            <div className="border border-gray-200 rounded-lg p-3 space-y-3 bg-gray-50">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Belege &amp; Texterkennung</span>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  onClick={() => setFormOcrAn(v => !v)}
                >
                  {formOcrAn ? 'Ausblenden' : (formBelege.length > 0 ? `${formBelege.length} Foto${formBelege.length !== 1 ? 's' : ''} anzeigen` : 'Anzeigen')}
                </button>
              </div>

              {formOcrAn && (
                <div className="space-y-3">
                  {/* Foto-Thumbnails */}
                  {formBelege.length === 0 ? (
                    <p className="text-xs text-gray-400">Noch keine Fotos – speichere zuerst ein Foto über „Kassenzettel-Foto".</p>
                  ) : (
                    <div className="flex gap-2 flex-wrap">
                      {formBelege.map(b => (
                        <img
                          key={b.id}
                          src={belegeApi.dateUrlEintrag(editId, b.id)}
                          alt={b.dateiname}
                          className="h-20 w-20 object-cover rounded border border-gray-200 cursor-pointer hover:opacity-80"
                          onClick={() => setZoomBeleg({ eintragId: editId, id: b.id, dateiname: b.dateiname })}
                        />
                      ))}
                    </div>
                  )}

                  {/* Text erkennen */}
                  {formBelege.length > 0 && !ocrVorschau && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      disabled={ocrLaden}
                      onClick={() => texterkennung(editId)}
                    >
                      {ocrLaden ? 'Erkenne Text…' : 'Text erkennen'}
                    </button>
                  )}

                  {/* OCR-Fehler */}
                  {ocrFehler && (
                    <div className="text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2 text-sm">
                      Texterkennung fehlgeschlagen. Bitte prüfe, ob ein lesbares Foto vorhanden ist.
                    </div>
                  )}

                  {/* OCR-Hinweis */}
                  {ocrHinweis && (
                    <div className="text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-sm">
                      {ocrHinweis.text}
                    </div>
                  )}

                  {/* OCR-Metainfo */}
                  {ocrInfo && (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 bg-white border border-gray-100 rounded px-2 py-1.5">
                      {ocrInfo.preiszeilen != null && <span>Preiszeilen: <strong>{ocrInfo.preiszeilen}</strong></span>}
                      {ocrInfo.variante && (
                        <span className="font-mono text-[10px] bg-gray-50 border border-gray-200 rounded px-1">
                          {ocrInfo.variante}
                          {ocrInfo.segmentiert && <span className="text-green-700 ml-1">✓ freigestellt</span>}
                        </span>
                      )}
                      {ocrInfo.hatVorschau && (
                        <a href={haushaltsbuchApi.belegVorschauUrl(ocrInfo.eintragId)} target="_blank" rel="noreferrer" className="ml-auto text-blue-600 hover:underline">
                          Verarbeitetes Bild
                        </a>
                      )}
                    </div>
                  )}

                  {/* Erkannte Artikel */}
                  {ocrVorschau && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-700">Erkannte Artikel ({ocrVorschau.filter(p => p.ausgewaehlt).length} ausgewählt)</span>
                        {ocrVorschau.length > 0 && (
                          <div className="mb-2 flex items-center gap-2">
                            <span className="text-xs text-gray-500">Kategorie für alle:</span>
                            <KategorieSelect
                              kategorien={kategorien}
                              value={ocrKategorieAlle}
                              onChange={id => setOcrKategorieFuerAlle(id)}
                              placeholder="– auswählen –"
                              className="w-36"
                            />
                          </div>
                        )}
                      </div>
                      <div className="space-y-1">
                        {ocrVorschau.map((p, idx) => (
                          <div key={idx} className="flex flex-wrap gap-2 items-center bg-white rounded border border-gray-100 px-2 py-1">
                            <input
                              type="checkbox"
                              className="haken"
                              checked={p.ausgewaehlt}
                              onChange={e => setOcrPosition(idx, 'ausgewaehlt', e.target.checked)}
                            />
                            <ArtikelBezeichnungFeld
                              className="input flex-1 min-w-[8rem] text-sm"
                              value={p.bezeichnung}
                              onChange={v => setOcrPosition(idx, 'bezeichnung', v)}
                              vorschlaege={ocrInfo?.bekannteArtikel || []}
                              ocrBezeichnung={p.ocr_bezeichnung}
                              onRevert={() => setOcrPosition(idx, 'bezeichnung', p.ocr_bezeichnung)}
                            />
                            <input className="input w-12 text-sm" type="number" step="0.01" value={p.menge} onChange={e => setOcrPosition(idx, 'menge', e.target.value)} />
                            <input
                              className="input w-20 text-sm"
                              type="number"
                              step="0.01"
                              placeholder="EP"
                              value={p.einzelpreis !== '' && p.einzelpreis != null ? p.einzelpreis : p.gesamtpreis}
                              onChange={e => setOcrPosition(idx, 'einzelpreis', e.target.value)}
                            />
                            <KategorieSelect
                              kategorien={kategorien}
                              value={p.kategorie_id}
                              onChange={id => setOcrPosition(idx, 'kategorie_id', id)}
                              placeholder="Kat."
                              className="w-28"
                              menuAlign="right"
                            />
                          </div>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        <button type="button" className="btn-primary btn-sm" onClick={ocrUebernehmen}>
                          Ausgewählte übernehmen
                        </button>
                        <button type="button" className="btn-secondary btn-sm" onClick={resetOcrState}>
                          Verwerfen
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Rohtext-Panel */}
                  {ocrRohtext && (
                    <div className="border-t pt-2">
                      <button
                        type="button"
                        className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                        onClick={() => setOcrRohtextAn(v => !v)}
                      >
                        {ocrRohtextAn ? '▲' : '▼'} Kassenzettel-Text {ocrRohtextAn ? 'ausblenden' : 'anzeigen'}
                      </button>
                      {ocrRohtextAn && (
                        <div className="mt-2 flex gap-2">
                          {ocrInfo?.hatVorschau && (
                            <img
                              ref={belegBildRef}
                              src={haushaltsbuchApi.belegVorschauUrl(ocrInfo.eintragId)}
                              alt="Beleg-Vorschau"
                              className="w-36 lg:w-72 shrink-0 object-contain rounded border border-gray-200 self-start"
                            />
                          )}
                          <div
                            className={`flex-1 border border-gray-200 rounded bg-white overflow-y-auto font-mono text-[11px] leading-relaxed ${belegBildHoehe ? '' : 'max-h-64'}`}
                            style={belegBildHoehe ? { height: `${belegBildHoehe}px` } : undefined}
                          >
                            {ocrRohtext.split('\n').map((zeile, i) => {
                              const hatInhalt = zeile.trim().length > 0
                              return (
                                <div
                                  key={i}
                                  onClick={() => hatInhalt && fuegeRohtextZeileHinzu(zeile)}
                                  className={`px-2 py-0.5 border-b border-gray-100 last:border-0 whitespace-pre ${hatInhalt ? 'hover:bg-blue-50 cursor-pointer' : ''}`}
                                  title={hatInhalt ? 'Als Artikel-Kandidat hinzufügen' : undefined}
                                >
                                  {zeile || ' '}
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Status-Meldung */}
          {status === 'ok' && (
            <div className="text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2 text-sm">
              Eintrag gespeichert!
            </div>
          )}
          {status === 'error' && (
            <div className="text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2 text-sm">
              Fehler beim Speichern. Bitte prüfe die Eingaben.
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={laden}
              className="btn btn-primary flex-1 justify-center"
            >
              {laden ? 'Wird gespeichert…' : editId ? 'Änderungen speichern' : 'Eintrag speichern'}
            </button>
            {editId && (
              <button type="button" className="btn-secondary" onClick={resetForm}>Abbrechen</button>
            )}
          </div>
        </form>
      </div>

      {/* Letzte Haushaltsbuch-Einträge */}
      {letzte.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Zuletzt erfasst</h2>
          </div>
          <div className="divide-y divide-gray-50">
            {letzte.map(e => {
              const badge = STATUS_BADGE[e.abgleich_status] ?? { label: e.abgleich_status, cls: 'badge-gray' }
              return (
                <div key={e.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-3 sm:px-4 py-2 text-sm">
                  <div className="min-w-0">
                    <span className="font-medium text-gray-800">{e.geschaeft?.name ?? '–'}</span>
                    <span className={`badge ${badge.cls} ml-2`}>{badge.label}</span>
                    {e.positionen.length > 0 && (
                      <span className="ml-2 text-xs text-gray-400">{e.positionen.length} Artikel</span>
                    )}
                    <div className="text-xs text-gray-400">{e.datum}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-red-500 font-mono mr-auto sm:mr-0">{fmt(-e.betrag_gesamt)}</span>
                    <button type="button" className="btn-secondary btn-sm h-9" onClick={() => oeffneGalerie(e.id)}>Fotos</button>
                    <button type="button" className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => startEdit(e)}><PencilIcon /></button>
                    <button type="button" className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => handleDelete(e.id)}>×</button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {dialog}

      {/* Beleg-Galerie */}
      {galerie && galerieModalOffen && (
        <Modal onClose={schliesseGalerie} title="Fotos" maxWidth="max-w-lg lg:max-w-3xl">
          {galerie.belege.length === 0 && <p className="text-gray-400 text-sm">Keine Fotos vorhanden.</p>}
          <div className="grid grid-cols-3 gap-3">
            {galerie.belege.map(b => (
              <div key={b.id} className="relative group">
                <img
                  src={belegeApi.dateUrlEintrag(galerie.eintragId, b.id)}
                  alt={b.dateiname}
                  className="w-full h-24 object-cover rounded border border-gray-200 cursor-pointer"
                  onClick={() => setZoomBeleg({ eintragId: galerie.eintragId, id: b.id, dateiname: b.dateiname })}
                />
                <button
                  type="button"
                  className="absolute -top-1.5 -right-1.5 bg-red-500 text-white rounded-full w-5 h-5 text-xs leading-none opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => deleteBeleg(b.id)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-4">
            <label className="btn btn-secondary btn-sm cursor-pointer inline-block">
              + Foto hinzufügen
              <input
                ref={kameraRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={async e => {
                  const datei = e.target.files[0]
                  if (!datei) return
                  await belegeApi.uploadEintrag(galerie.eintragId, datei)
                  const r = await belegeApi.listEintrag(galerie.eintragId)
                  setGalerie({ eintragId: galerie.eintragId, belege: r.data })
                  setOcrVorschau(null)
                  setOcrHinweis(null)
                }}
              />
            </label>
            {galerie.belege.length > 0 && !ocrVorschau && (
              <button type="button" className="btn-secondary btn-sm" disabled={ocrLaden} onClick={() => texterkennung()}>
                {ocrLaden ? 'Erkenne Text…' : 'Text erkennen'}
              </button>
            )}
          </div>

          {ocrFehler && (
            <div className="text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2 text-sm mt-3">
              Texterkennung fehlgeschlagen. Bitte prüfe, ob ein lesbares Foto vorhanden ist.
            </div>
          )}

          {ocrHinweis && (
            <div className="text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-sm mt-3 flex items-center justify-between gap-3">
              <span>{ocrHinweis.text}</span>
              {ocrHinweis.fotoWiederholenEmpfohlen && (
                <button
                  type="button"
                  className="btn-secondary btn-sm whitespace-nowrap"
                  onClick={() => kameraRef.current?.click()}
                >
                  Neues Foto
                </button>
              )}
            </div>
          )}

          {ocrInfo && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 bg-gray-50 border border-gray-100 rounded px-2 py-1.5">
              {ocrInfo.preiszeilen != null && <span>Preiszeilen: <strong>{ocrInfo.preiszeilen}</strong></span>}
              {ocrInfo.variante && (
                <span className="font-mono text-[10px] bg-white border border-gray-200 rounded px-1">
                  {ocrInfo.variante}
                  {ocrInfo.segmentiert && <span className="text-green-700 ml-1" title="Beleg freigestellt">✓ freigestellt</span>}
                </span>
              )}
              {ocrInfo.hatVorschau && (
                <a
                  href={haushaltsbuchApi.belegVorschauUrl(ocrInfo.eintragId)}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto text-blue-600 hover:underline"
                >
                  Verarbeitetes Bild ansehen
                </a>
              )}
            </div>
          )}

          {ocrVorschau && (
            <div className="mt-4 border-t pt-3">
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Erkannte Artikel</h4>
              {ocrVorschau.length === 0 && (
                <p className="text-gray-400 text-sm">Keine Artikel erkannt – Foto ggf. unscharf oder Format unbekannt.</p>
              )}
              {ocrVorschau.length > 0 && (
                <div className="mb-3">
                  <label className="label">Kategorie für alle Artikel vorbelegen</label>
                  <KategorieSelect
                    kategorien={kategorien}
                    value={ocrKategorieAlle}
                    onChange={id => setOcrKategorieFuerAlle(id)}
                    placeholder="– auswählen –"
                  />
                </div>
              )}
              <div className="space-y-2">
                {ocrVorschau.map((p, idx) => (
                  <div key={idx} className="flex gap-2 items-center">
                    <input
                      type="checkbox"
                      className="haken"
                      checked={p.ausgewaehlt}
                      onChange={e => setOcrPosition(idx, 'ausgewaehlt', e.target.checked)}
                    />
                    <ArtikelBezeichnungFeld
                      className="input flex-1"
                      value={p.bezeichnung}
                      onChange={v => setOcrPosition(idx, 'bezeichnung', v)}
                      vorschlaege={ocrInfo?.bekannteArtikel || []}
                      ocrBezeichnung={p.ocr_bezeichnung}
                      onRevert={() => setOcrPosition(idx, 'bezeichnung', p.ocr_bezeichnung)}
                    />
                    <input
                      className="input w-16"
                      type="number"
                      step="0.01"
                      value={p.menge}
                      onChange={e => setOcrPosition(idx, 'menge', e.target.value)}
                    />
                    <input
                      className="input w-24"
                      type="number"
                      step="0.01"
                      placeholder="EP"
                      value={p.einzelpreis !== '' && p.einzelpreis != null ? p.einzelpreis : p.gesamtpreis}
                      onChange={e => setOcrPosition(idx, 'einzelpreis', e.target.value)}
                    />
                    <KategorieSelect
                      kategorien={kategorien}
                      value={p.kategorie_id}
                      onChange={id => setOcrPosition(idx, 'kategorie_id', id)}
                      placeholder="Kategorie"
                      className="w-32"
                      menuAlign="right"
                    />
                  </div>
                ))}
              </div>
              {ocrVorschau.length > 0 && (
                <div className="flex gap-2 mt-3">
                  <button type="button" className="btn-primary btn-sm" onClick={ocrUebernehmen}>
                    Ausgewählte ins Formular übernehmen
                  </button>
                  <button type="button" className="btn-secondary btn-sm" onClick={() => setOcrVorschau(null)}>
                    Verwerfen
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Rohtext-Panel */}
          {ocrRohtext && (
            <div className="mt-3 border-t pt-3">
              <button
                type="button"
                className="btn-secondary btn-sm w-full text-left flex items-center justify-between"
                onClick={() => setOcrRohtextAn(v => !v)}
              >
                <span>Kassenzettel-Text {ocrRohtextAn ? 'ausblenden' : 'anzeigen'}</span>
                <span className="text-gray-400 text-xs">{ocrRohtextAn ? '▲' : '▼'}</span>
              </button>
              {ocrRohtextAn && (
                <div className="mt-2">
                  <p className="text-xs text-gray-400 mb-2">
                    Klick auf eine Zeile → als Artikel-Kandidat hinzufügen
                  </p>
                  <div className="flex gap-2">
                    {ocrInfo?.hatVorschau && (
                      <img
                        src={haushaltsbuchApi.belegVorschauUrl(ocrInfo.eintragId)}
                        alt="Beleg-Vorschau"
                        className="w-40 shrink-0 object-contain rounded border border-gray-200 self-start"
                      />
                    )}
                    <div className="flex-1 border border-gray-200 rounded bg-gray-50 overflow-y-auto max-h-72 font-mono text-[11px] leading-relaxed">
                      {ocrRohtext.split('\n').map((zeile, i) => {
                        const hat_inhalt = zeile.trim().length > 0
                        return (
                          <div
                            key={i}
                            onClick={() => hat_inhalt && fuegeRohtextZeileHinzu(zeile)}
                            className={`px-2 py-0.5 border-b border-gray-100 last:border-0 whitespace-pre
                              ${hat_inhalt ? 'hover:bg-blue-50 cursor-pointer' : 'text-transparent select-none'}`}
                            title={hat_inhalt ? 'Als Artikel-Kandidat hinzufügen' : undefined}
                          >
                            {zeile || ' '}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </Modal>
      )}

      {/* Vollbild-Zoom */}
      {zoomBeleg && (
        <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-[60] p-4" onClick={() => setZoomBeleg(null)}>
          <img
            src={belegeApi.dateUrlEintrag(zoomBeleg.eintragId, zoomBeleg.id)}
            alt={zoomBeleg.dateiname}
            className="max-w-full max-h-full object-contain"
          />
          <button
            onClick={() => setZoomBeleg(null)}
            className="absolute top-4 right-4 text-white text-2xl"
          >
            ×
          </button>
        </div>
      )}
    </div>
  )
}
