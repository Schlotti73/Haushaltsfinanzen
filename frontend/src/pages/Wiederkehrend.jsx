import { useState, useEffect, Fragment, useMemo } from 'react'
import { wiederkehrendApi, kontenApi, kategorienApi } from '../api'
import { useHilfe } from '../HilfeContext'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'
import CurrencyInput from '../components/CurrencyInput'
import { PencilIcon } from '../components/icons'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

const RHYTHMUS_LABEL = { monatlich: 'Monatlich', zweimonatlich: 'Alle 2 Monate', quartal: 'Quartalsweise', jaehrlich: 'Jährlich' }

const LEER = {
  konto_id: '',
  betrag: '',
  empfaenger: '',
  kategorie_id: '',
  rhythmus: 'monatlich',
  start_datum: '',
  end_datum: '',
  aktiv: true,
}

function WbForm({ initial, konten, kategorien, onSave, onCancel }) {
  const [f, setF] = useState(initial || LEER)

  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }))

  const handleSubmit = e => {
    e.preventDefault()
    onSave({
      ...f,
      konto_id: f.konto_id ? Number(f.konto_id) : null,
      kategorie_id: f.kategorie_id ? Number(f.kategorie_id) : null,
      betrag: Number(f.betrag),
      end_datum: f.end_datum || null,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Empfänger</label>
          <input className="input" autoFocus value={f.empfaenger} onChange={e => set('empfaenger', e.target.value)} />
        </div>
        <div>
          <label className="label">Betrag (negativ = Ausgabe)</label>
          <CurrencyInput required value={f.betrag} onChange={(n) => set('betrag', n ?? '')} />
        </div>
        <div>
          <label className="label">Konto</label>
          <select className="input" value={f.konto_id} onChange={e => set('konto_id', e.target.value)}>
            <option value="">– kein –</option>
            {konten.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Kategorie</label>
          <KategorieSelect
            kategorien={kategorien}
            value={f.kategorie_id}
            onChange={id => set('kategorie_id', id)}
          />
        </div>
        <div>
          <label className="label">Rhythmus</label>
          <select className="input" value={f.rhythmus} onChange={e => set('rhythmus', e.target.value)}>
            <option value="monatlich">Monatlich</option>
            <option value="zweimonatlich">Alle 2 Monate</option>
            <option value="quartal">Quartalsweise</option>
            <option value="jaehrlich">Jährlich</option>
          </select>
        </div>
        <div>
          <label className="label">Start-Datum</label>
          <input className="input" type="date" required value={f.start_datum} onChange={e => set('start_datum', e.target.value)} />
        </div>
        <div>
          <label className="label">End-Datum (optional)</label>
          <input className="input" type="date" value={f.end_datum || ''} onChange={e => set('end_datum', e.target.value)} />
        </div>
        <div className="flex items-center gap-2 pt-5">
          <input type="checkbox" role="switch" className="schieber" id="aktiv" checked={f.aktiv} onChange={e => set('aktiv', e.target.checked)} />
          <label htmlFor="aktiv" className="text-sm text-gray-700">Aktiv</label>
        </div>
      </div>
      <div className="flex gap-2 pt-1">
        <button type="submit" className="btn btn-primary btn-sm">Speichern</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  )
}

export default function Wiederkehrend() {
  const { openHilfe } = useHilfe()
  const { confirm, dialog } = useConfirm()
  const [liste, setListe] = useState([])
  const [konten, setKonten] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [neuFormular, setNeuFormular] = useState(false)
  const [editId, setEditId] = useState(null)
  const [filterText, setFilterText] = useState('')
  const [filterKonto, setFilterKonto] = useState('')

  const load = () => wiederkehrendApi.list().then(r => setListe(r.data))

  useEffect(() => {
    load()
    kontenApi.list().then(r => setKonten(r.data))
    kategorienApi.flat().then(r => setKategorien(r.data))
  }, [])

  const kontoName = id => konten.find(k => k.id === id)?.name ?? '–'

  const gefilterteListe = useMemo(() => {
    const text = filterText.toLowerCase()
    return liste.filter(wb => {
      if (filterKonto && String(wb.konto_id) !== filterKonto) return false
      if (text && !(wb.empfaenger ?? '').toLowerCase().includes(text)) return false
      return true
    })
  }, [liste, filterText, filterKonto])
  const katName = id => kategorien.find(k => k.id === id)?.name ?? '–'

  const handleCreate = async data => {
    await wiederkehrendApi.create(data)
    await load()
    setNeuFormular(false)
  }

  const handleUpdate = async (id, data) => {
    await wiederkehrendApi.update(id, data)
    await load()
    setEditId(null)
  }

  const handleDelete = async id => {
    if (!await confirm('Vorlage löschen? Bereits generierte Buchungen bleiben erhalten.')) return
    await wiederkehrendApi.delete(id)
    await load()
  }

  const toggleAktiv = async wb => {
    await wiederkehrendApi.update(wb.id, { aktiv: !wb.aktiv })
    await load()
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
        <h1 className="text-xl font-bold text-gray-900">Wiederkehrende Buchungen</h1>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => openHilfe('wiederkehrend-liquiditaet')} className="text-sm text-blue-600 hover:underline">Hilfe dazu</button>
          <button className="btn btn-primary btn-sm" onClick={() => setNeuFormular(true)}>
            + Neue Vorlage
          </button>
        </div>
      </div>

      {neuFormular && (
        <div className="card p-4 mb-4">
          <h2 className="font-semibold text-gray-800 mb-3">Neue Vorlage</h2>
          <WbForm
            konten={konten}
            kategorien={kategorien}
            onSave={handleCreate}
            onCancel={() => setNeuFormular(false)}
          />
        </div>
      )}

      <div className="card p-3 mb-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="label">Suche</label>
          <input
            className="input w-52"
            placeholder="Empfänger…"
            value={filterText}
            onChange={e => setFilterText(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Konto</label>
          <select className="input" value={filterKonto} onChange={e => setFilterKonto(e.target.value)}>
            <option value="">Alle</option>
            {konten.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
        </div>
        {(filterText || filterKonto) && (
          <button className="btn btn-secondary btn-sm self-end" onClick={() => { setFilterText(''); setFilterKonto('') }}>
            Zurücksetzen
          </button>
        )}
      </div>

      <div className="card overflow-hidden">
        {gefilterteListe.length === 0 ? (
          <div className="p-6 text-center text-gray-400">
            {filterText || filterKonto ? 'Keine Treffer.' : 'Noch keine Vorlagen. Lege wiederkehrende Zahlungen (Miete, Versicherungen, …) an.'}
          </div>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Empfänger</th>
                <th className="px-4 py-2 text-right">Betrag</th>
                <th className="px-4 py-2 text-left">Rhythmus</th>
                <th className="px-4 py-2 text-left">Konto</th>
                <th className="px-4 py-2 text-left">Kategorie</th>
                <th className="px-4 py-2 text-left">Start</th>
                <th className="px-4 py-2 text-left">Ende</th>
                <th className="px-4 py-2 text-center">Aktiv</th>
                <th className="px-4 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {gefilterteListe.map(wb => (
                <Fragment key={wb.id}>
                  <tr className={`odd:bg-white even:bg-gray-50 hover:bg-blue-50 ${wb.aktiv ? '' : 'opacity-50'}`}>
                    <td className="px-4 py-2 font-medium">{wb.empfaenger ?? '–'}</td>
                    <td className={`px-4 py-2 text-right font-mono ${wb.betrag < 0 ? 'text-red-500' : 'text-green-600'}`}>
                      {fmt(wb.betrag)}
                    </td>
                    <td className="px-4 py-2 text-gray-600">{RHYTHMUS_LABEL[wb.rhythmus]}</td>
                    <td className="px-4 py-2 text-gray-600">{kontoName(wb.konto_id)}</td>
                    <td className="px-4 py-2 text-gray-600">{katName(wb.kategorie_id)}</td>
                    <td className="px-4 py-2 text-gray-500">{wb.start_datum}</td>
                    <td className="px-4 py-2 text-gray-400">{wb.end_datum ?? '–'}</td>
                    <td className="px-4 py-2 text-center">
                      <button
                        onClick={() => toggleAktiv(wb)}
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          wb.aktiv
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {wb.aktiv ? 'Ja' : 'Nein'}
                      </button>
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-1 justify-end">
                        <button className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setEditId(editId === wb.id ? null : wb.id)}>
                          <PencilIcon />
                        </button>
                        <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => handleDelete(wb.id)}>
                          ×
                        </button>
                      </div>
                    </td>
                  </tr>
                  {editId === wb.id && (
                    <tr>
                      <td colSpan={9} className="px-4 py-3 bg-blue-50">
                        <WbForm
                          initial={{
                            ...wb,
                            konto_id: wb.konto_id ?? '',
                            kategorie_id: wb.kategorie_id ?? '',
                            end_datum: wb.end_datum ?? '',
                          }}
                          konten={konten}
                          kategorien={kategorien}
                          onSave={data => handleUpdate(wb.id, data)}
                          onCancel={() => setEditId(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {dialog}
    </div>
  )
}
