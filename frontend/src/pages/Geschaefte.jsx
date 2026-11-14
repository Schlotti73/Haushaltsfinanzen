import { useEffect, useState } from 'react'
import { useHilfe } from '../HilfeContext'
import { geschaefteApi, kategorienApi, empfaengerApi } from '../api'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'
import Modal from '../components/Modal'
import { PencilIcon } from '../components/icons'

export default function Geschaefte() {
  const { openHilfe } = useHilfe()
  const { confirm, dialog } = useConfirm()
  const [geschaefte, setGeschaefte] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [empfaenger, setEmpfaenger] = useState([])
  const [nurAktiv, setNurAktiv] = useState(true)
  const [suche, setSuche] = useState('')
  const [form, setForm] = useState(null)

  const load = () => {
    geschaefteApi.list({ nur_aktiv: nurAktiv, suche: suche || undefined }).then(r => setGeschaefte(r.data))
  }

  useEffect(load, [nurAktiv, suche])
  useEffect(() => {
    kategorienApi.flat().then(r => setKategorien(r.data.filter(k => k.art !== 'einnahme')))
    empfaengerApi.list().then(r => setEmpfaenger(r.data))
  }, [])

  const save = async (e) => {
    e.preventDefault()
    const map = (form.mwst_kategorie_map || []).filter(x => String(x.schluessel).trim())
    const keys = map.map(x => String(x.schluessel).trim().toUpperCase())
    const dupe = keys.find((k, i) => keys.indexOf(k) !== i)
    if (dupe) { alert(`Doppelter MwSt-Schlüssel: „${dupe}" – bitte eindeutig.`); return }
    const daten = {
      name: form.name,
      standard_kategorie_id: form.standard_kategorie_id ? Number(form.standard_kategorie_id) : null,
      empfaenger_id: form.empfaenger_id ? Number(form.empfaenger_id) : null,
      mwst_kategorie_map: map.map(x => ({ schluessel: String(x.schluessel).trim(), kategorie_id: Number(x.kategorie_id) })),
    }
    if (form.id) await geschaefteApi.update(form.id, daten)
    else await geschaefteApi.create(daten)
    setForm(null)
    load()
  }

  // MwSt→Kategorie-Map-Editor
  const setMap = (i, feld, wert) =>
    setForm(f => ({ ...f, mwst_kategorie_map: f.mwst_kategorie_map.map((e, idx) => idx === i ? { ...e, [feld]: wert } : e) }))
  const removeMap = (i) =>
    setForm(f => ({ ...f, mwst_kategorie_map: f.mwst_kategorie_map.filter((_, idx) => idx !== i) }))
  const addMap = () =>
    setForm(f => ({ ...f, mwst_kategorie_map: [...(f.mwst_kategorie_map || []), { schluessel: '', kategorie_id: kategorien[0]?.id ?? 0 }] }))

  const mapKurz = (m) => (m || []).map(e => `${e.schluessel}→${kategorieName(e.kategorie_id)}`).join(', ')

  const del = async (id) => {
    if (!await confirm('Geschäft löschen?')) return
    await geschaefteApi.delete(id)
    load()
  }

  const toggleAktiv = async (g) => {
    await geschaefteApi.update(g.id, { aktiv: !g.aktiv })
    load()
  }

  const kategorieName = (id) => kategorien.find(k => k.id === id)?.name ?? '–'
  const empfaengerName = (id) => empfaenger.find(e => e.id === id)?.name ?? '–'

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-xl font-bold">Geschäfte</h2>
        <button className="btn-primary" onClick={() => setForm({ name: '', standard_kategorie_id: '', empfaenger_id: '', mwst_kategorie_map: [] })}>+ Neu</button>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <input
          className="input max-w-xs"
          placeholder="Suche…"
          value={suche}
          onChange={e => setSuche(e.target.value)}
        />
        <label className="flex items-center gap-1.5 text-sm text-gray-600">
          <input type="checkbox" checked={nurAktiv} onChange={e => setNurAktiv(e.target.checked)} />
          nur aktive
        </label>
      </div>

      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Standard-Kategorie</th>
              <th className="px-3 py-2 font-medium">Artikel-Kategorien (MwSt)</th>
              <th className="px-3 py-2 font-medium">Empfänger-Link</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {geschaefte.map(g => (
              <tr key={g.id} className="border-b odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                <td className="px-3 py-2 font-medium">{g.name}</td>
                <td className="px-3 py-2 text-gray-600">{kategorieName(g.standard_kategorie_id)}</td>
                <td className="px-3 py-2 text-gray-600">
                  {g.mwst_kategorie_map?.length
                    ? <span className="text-xs">{mapKurz(g.mwst_kategorie_map)}</span>
                    : <span className="text-gray-300">–</span>}
                </td>
                <td className="px-3 py-2 text-gray-600">{empfaengerName(g.empfaenger_id)}</td>
                <td className="px-3 py-2">
                  {g.aktiv
                    ? <span className="badge badge-green">aktiv</span>
                    : <span className="badge badge-gray">inaktiv</span>}
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex gap-1 justify-end">
                    <button className="btn-secondary btn-sm h-9" onClick={() => toggleAktiv(g)}>
                      {g.aktiv ? 'Deaktivieren' : 'Aktivieren'}
                    </button>
                    <button className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setForm({ ...g })}><PencilIcon /></button>
                    <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => del(g.id)}>×</button>
                  </div>
                </td>
              </tr>
            ))}
            {geschaefte.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-400">Keine Geschäfte gefunden</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {form && (
        <form onSubmit={save}>
          <Modal
            onClose={() => setForm(null)}
            title={form.id ? 'Geschäft bearbeiten' : 'Neues Geschäft'}
            maxWidth="max-w-lg"
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
              <label className="label">Standard-Kategorie</label>
              <KategorieSelect
                kategorien={kategorien}
                value={form.standard_kategorie_id}
                onChange={id => setForm({ ...form, standard_kategorie_id: id })}
              />
            </div>
            <div>
              <div className="flex items-baseline justify-between gap-2">
                <label className="label">Empfänger-Link (für Kontoauszug-Abgleich)</label>
                <button type="button" onClick={() => openHilfe('empfaenger-link')} className="text-[11px] text-blue-600 hover:underline shrink-0">
                  Hilfe dazu
                </button>
              </div>
              <select className="input" value={form.empfaenger_id ?? ''} onChange={e => setForm({ ...form, empfaenger_id: e.target.value })}>
                <option value="">– keine –</option>
                {empfaenger.map(e => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
              {empfaenger.length === 0 && (
                <p className="text-[11px] text-amber-700 mt-1">
                  Noch keine Empfänger angelegt – die Auswahl bleibt deshalb leer.
                  Empfänger pflegst du unter <span className="font-medium">Empfänger</span>.
                </p>
              )}
            </div>

            {/* Artikel-Kategorisierung: MwSt-Schlüssel → Kategorie (Foto-Import) */}
            <div className="border-t pt-3">
              <label className="label">Artikel-Kategorien (MwSt-Schlüssel → Kategorie)</label>
              <p className="text-[11px] text-gray-400 mb-2">
                Steuert, wie Artikel eines Kassenzettels (per Foto-Import) auf Kategorien verteilt werden –
                z.&nbsp;B. <span className="font-mono">A → Lebensmittel</span>, <span className="font-mono">B → Haushaltswaren</span>.
                Die Standard-Kategorie oben greift als Fallback für nicht aufgeteilte Belege.
              </p>
              <div className="space-y-1.5">
                {(form.mwst_kategorie_map || []).map((e, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      className="input w-16 text-center font-mono uppercase"
                      value={e.schluessel}
                      maxLength={2}
                      placeholder="A"
                      onChange={ev => setMap(i, 'schluessel', ev.target.value)}
                    />
                    <span className="text-gray-400">→</span>
                    <KategorieSelect
                      kategorien={kategorien}
                      value={e.kategorie_id}
                      isClearable={false}
                      className="flex-1"
                      onChange={id => setMap(i, 'kategorie_id', id ?? kategorien[0]?.id ?? 0)}
                    />
                    <button type="button" className="text-gray-400 hover:text-red-600 px-1" onClick={() => removeMap(i)} title="Entfernen">×</button>
                  </div>
                ))}
                {(form.mwst_kategorie_map || []).length === 0 && (
                  <p className="text-[11px] text-gray-400">Keine Zuordnung – Standard nach MwSt-Satz (7 % → Lebensmittel, sonst Haushaltswaren).</p>
                )}
                <button type="button" className="text-xs text-blue-600 hover:underline" onClick={addMap}>+ Zuordnung</button>
              </div>
            </div>
          </Modal>
        </form>
      )}
      {dialog}
    </div>
  )
}
