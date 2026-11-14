import { useEffect, useState } from 'react'
import { empfaengerApi, importRegelApi, kategorienApi } from '../api'
import KategorieSelect from './KategorieSelect'

const LEER = {
  name: '', stufe: 'haendler', schluesselwoerter: '', iban_muster: '',
  empfaenger_id: '', kategorie_id: null, notiz_text: '', aktiv: true, notiz: '',
}

/**
 * Regel-Formular, geteilt zwischen der Pflegemaske in den Einstellungen und der
 * Inline-Anlage aus einer Buchung heraus. Bewusst eine Komponente: zwei
 * Formulare für dasselbe Objekt laufen sonst auseinander.
 *
 * `initial` darf eine bestehende Regel (mit id) oder nur Vorbelegungen sein.
 */
export default function ImportRegelForm({ initial, onGespeichert, onAbbrechen, kompakt = false }) {
  const [form, setForm] = useState({ ...LEER, ...initial })
  const [empfaenger, setEmpfaenger] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [speichern, setSpeichern] = useState(false)
  const [fehler, setFehler] = useState(null)

  useEffect(() => { setForm({ ...LEER, ...initial }) }, [initial])

  useEffect(() => {
    Promise.all([empfaengerApi.list(), kategorienApi.flat()])
      .then(([e, k]) => { setEmpfaenger(e.data); setKategorien(k.data) })
      .catch(() => setFehler('Stammdaten konnten nicht geladen werden.'))
  }, [])

  const set = (feld, wert) => setForm(f => ({ ...f, [feld]: wert }))

  const onSubmit = async (e) => {
    e.preventDefault()
    setSpeichern(true); setFehler(null)
    const daten = {
      name: form.name.trim(),
      stufe: form.stufe,
      schluesselwoerter: form.schluesselwoerter.split(',').map(w => w.trim()).filter(Boolean),
      iban_muster: form.iban_muster.trim() || null,
      empfaenger_id: form.empfaenger_id === '' ? null : Number(form.empfaenger_id),
      kategorie_id: form.kategorie_id ?? null,
      notiz_text: form.notiz_text.trim() || null,
      aktiv: form.aktiv,
      notiz: form.notiz.trim() || null,
    }
    try {
      const r = form.id
        ? await importRegelApi.update(form.id, daten)
        : await importRegelApi.create(daten)
      onGespeichert?.(r.data)
    } catch (err) {
      setFehler(err.response?.data?.detail ?? 'Speichern fehlgeschlagen.')
    } finally {
      setSpeichern(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className={kompakt ? 'space-y-3' : 'border border-blue-200 bg-blue-50/40 rounded p-4 space-y-3'}>
      {fehler && (
        <div className="rounded px-3 py-2 text-sm bg-red-50 text-red-800 border border-red-200">{fehler}</div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Name*</label>
          <input className="input w-full" value={form.name} required
                 onChange={e => set('name', e.target.value)} placeholder="z. B. PayPal" />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Stufe</label>
          <select className="input w-full" value={form.stufe} onChange={e => set('stufe', e.target.value)}>
            <option value="anbieter">Anbieter (Zahlungsdienstleister)</option>
            <option value="haendler">Händler (Laden)</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          Schlüsselwörter (mit Komma getrennt)
        </label>
        <input className="input w-full" value={form.schluesselwoerter}
               onChange={e => set('schluesselwoerter', e.target.value)}
               placeholder="Paypal Europe, PayPal" />
        <p className="text-xs text-gray-400 mt-1">
          Groß-/Kleinschreibung, Punkte und Umlaute sind egal – „Getränke Nord“ trifft auch „GETRANKE NORD“.
          Der Treffer muss ein ganzes Wort sein.
        </p>
      </div>

      {form.stufe === 'anbieter' && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">IBAN (optional)</label>
          <input className="input w-full font-mono" value={form.iban_muster}
                 onChange={e => set('iban_muster', e.target.value)} />
          <p className="text-xs text-gray-400 mt-1">
            Feste Gläubiger-IBAN – schlägt jedes Schlüsselwort.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Empfänger{form.stufe === 'anbieter' ? '*' : ' (optional)'}
          </label>
          <select className="input w-full" value={form.empfaenger_id}
                  required={form.stufe === 'anbieter'}
                  onChange={e => set('empfaenger_id', e.target.value)}>
            <option value="">– keiner –</option>
            {empfaenger.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Kategorie</label>
          <KategorieSelect kategorien={kategorien} value={form.kategorie_id}
                           onChange={id => set('kategorie_id', id)} />
        </div>
      </div>

      {form.stufe === 'haendler' && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Notiz-Text</label>
          <input className="input w-full" value={form.notiz_text}
                 onChange={e => set('notiz_text', e.target.value)}
                 placeholder={form.name || 'leer = Name der Regel'} />
        </div>
      )}

      {!kompakt && (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Interne Notiz</label>
          <textarea className="input w-full" rows={2} value={form.notiz}
                    onChange={e => set('notiz', e.target.value)} />
        </div>
      )}

      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" className="w-4 h-4 accent-blue-600" checked={form.aktiv}
               onChange={e => set('aktiv', e.target.checked)} />
        Aktiv
      </label>

      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={speichern}>
          {speichern ? 'Speichere…' : 'Speichern'}
        </button>
        <button type="button" className="btn-secondary" onClick={onAbbrechen}>Abbrechen</button>
      </div>
    </form>
  )
}
