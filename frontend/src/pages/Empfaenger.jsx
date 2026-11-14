import { useEffect, useState } from 'react'
import { empfaengerApi, kategorienApi } from '../api'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'
import Modal from '../components/Modal'
import { PencilIcon } from '../components/icons'

export default function Empfaenger() {
  const { confirm, dialog } = useConfirm()
  const [liste, setListe] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [suche, setSuche] = useState('')
  const [form, setForm] = useState(null)
  const [mergeVon, setMergeVon] = useState(null)
  const [mergeZiel, setMergeZiel] = useState('')

  const load = () => empfaengerApi.list(suche || undefined).then(r => setListe(r.data))

  useEffect(() => {
    kategorienApi.flat().then(r => setKategorien(r.data))
  }, [])

  useEffect(() => { load() }, [suche])

  const save = async (e) => {
    e.preventDefault()
    if (form.id) await empfaengerApi.update(form.id, form)
    else await empfaengerApi.create(form)
    setForm(null)
    load()
  }

  const del = async (id) => {
    if (!await confirm('Empfänger löschen? Buchungsverknüpfungen gehen verloren.')) return
    await empfaengerApi.delete(id)
    load()
  }

  const merge = async () => {
    if (!mergeVon || !mergeZiel) return
    if (!await confirm(`„${mergeVon.name}" → „${liste.find(e => e.id === +mergeZiel)?.name}" zusammenführen? Nicht rückgängig machbar.`, { knopf: 'Zusammenführen' })) return
    await empfaengerApi.zusammenfuehren(mergeVon.id, +mergeZiel)
    setMergeVon(null)
    setMergeZiel('')
    load()
  }

  const katName = (id) => kategorien.find(k => k.id === id)?.name ?? '–'

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Empfänger-Stammdaten</h2>
        <button className="btn-primary" onClick={() => setForm({ name: '', iban: '', kategorie_id: '', notiz: '' })}>+ Neu</button>
      </div>

      {/* Suche */}
      <div className="card">
        <input
          className="input"
          placeholder="Name oder IBAN suchen…"
          value={suche}
          onChange={e => setSuche(e.target.value)}
        />
      </div>

      {/* Tabelle */}
      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">IBAN</th>
              <th className="px-3 py-2 font-medium">Kategorie (Vorbelegung)</th>
              <th className="px-3 py-2 font-medium">Notiz</th>
              <th className="px-3 py-2 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {liste.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-400">Keine Einträge</td></tr>
            )}
            {liste.map(e => (
              <tr key={e.id} className="border-b odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                <td className="px-3 py-2 font-medium">{e.name}</td>
                <td className="px-3 py-2 font-mono text-xs text-gray-500">{e.iban || '–'}</td>
                <td className="px-3 py-2 text-gray-500">{katName(e.kategorie_id)}</td>
                <td className="px-3 py-2 text-gray-400 max-w-xs truncate">{e.notiz || ''}</td>
                <td className="px-3 py-2 whitespace-nowrap text-right">
                  <button className="btn-secondary btn-icon mr-1" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setForm({ ...e, kategorie_id: e.kategorie_id ?? '' })}><PencilIcon /></button>
                  <button className="btn-secondary btn-sm h-9 mr-1" onClick={() => { setMergeVon(e); setMergeZiel('') }}>Merge</button>
                  <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => del(e.id)}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Merge-Dialog */}
      {mergeVon && (
        <div className="card border-orange-200 bg-orange-50">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-medium text-orange-800">
              „{mergeVon.name}" zusammenführen mit:
            </span>
            <select
              className="input py-1 text-sm flex-1 min-w-[200px]"
              value={mergeZiel}
              onChange={e => setMergeZiel(e.target.value)}
            >
              <option value="">– Ziel wählen –</option>
              {liste.filter(e => e.id !== mergeVon.id).map(e => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
            <button className="btn-primary btn-sm" disabled={!mergeZiel} onClick={merge}>Zusammenführen</button>
            <button className="btn-secondary btn-sm" onClick={() => setMergeVon(null)}>Abbrechen</button>
          </div>
        </div>
      )}

      {/* Formular-Modal */}
      {form && (
        <form onSubmit={save}>
          <Modal
            onClose={() => setForm(null)}
            title={form.id ? 'Empfänger bearbeiten' : 'Neuer Empfänger'}
            maxWidth="max-w-md"
            footer={
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
                <button type="button" className="btn-secondary" onClick={() => setForm(null)}>Abbrechen</button>
              </div>
            }
          >
            <div>
              <label className="label">Name*</label>
              <input className="input" required autoFocus value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="label">IBAN</label>
              <input className="input font-mono" placeholder="DE…" value={form.iban ?? ''} onChange={e => setForm({ ...form, iban: e.target.value || null })} />
            </div>
            <div>
              <label className="label">Kategorie-Vorbelegung</label>
              <KategorieSelect
                kategorien={kategorien}
                value={form.kategorie_id}
                onChange={id => setForm({ ...form, kategorie_id: id })}
              />
            </div>
            <div>
              <label className="label">Notiz</label>
              <input className="input" value={form.notiz ?? ''} onChange={e => setForm({ ...form, notiz: e.target.value || null })} />
            </div>
          </Modal>
        </form>
      )}
      {dialog}
    </div>
  )
}
