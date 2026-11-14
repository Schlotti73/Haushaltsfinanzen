import { useEffect, useState, Fragment } from 'react'
import { useHilfe } from '../HilfeContext'
import CurrencyInput from '../components/CurrencyInput'
import Modal from '../components/Modal'
import { PencilIcon } from '../components/icons'
import { auswaehlbareKonten } from '../kontoAuswahl'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement,
  LineElement, PointElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'
import { projekteApi, kontenApi, kategorienApi, buchungenApi } from '../api'
import { useAuth } from '../AuthContext'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'

ChartJS.register(
  CategoryScale, LinearScale, BarElement,
  LineElement, PointElement,
  Title, Tooltip, Legend,
)

const TYPEN = ['darlehen', 'bauprojekt', 'sonstiges']

function fmt(n) {
  return n != null ? new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n) : '–'
}

function round2(n) {
  return Math.round(n * 100) / 100
}

function DarlehenKurve({ raten, name }) {
  if (!raten.length) return null

  const chartData = {
    labels: raten.map(r => r.datum),
    datasets: [
      {
        label: 'Restschuld',
        data: raten.map(r => r.restschuld),
        borderColor: 'rgba(59,130,246,0.9)',
        backgroundColor: 'rgba(59,130,246,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 2,
      },
    ],
  }

  const options = {
    responsive: true,
    plugins: { legend: { display: false }, title: { display: false } },
    scales: {
      y: {
        ticks: {
          callback: (v) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v),
        },
      },
    },
  }

  return (
    <div className="card p-4 mt-4">
      <h3 className="font-semibold text-gray-800 mb-3">Restschuld-Verlauf – {name}</h3>
      <Line data={chartData} options={options} />
    </div>
  )
}

function BudgetVsIst({ projektId, projektName }) {
  const [daten, setDaten] = useState(null)

  useEffect(() => {
    projekteApi.budgetVsIst(projektId).then(r => setDaten(r.data))
  }, [projektId])

  if (!daten) return <p className="text-gray-400 text-sm p-4">Lade…</p>

  const ausgaben = daten.kategorien.filter(k => k.ist_summe < 0)
  const einnahmen = daten.kategorien.filter(k => k.ist_summe >= 0)

  const chartData = {
    labels: ausgaben.map(k => k.kategorie),
    datasets: [
      {
        label: 'Ist (Ausgaben)',
        data: ausgaben.map(k => Math.abs(k.ist_summe)),
        backgroundColor: 'rgba(239,68,68,0.7)',
      },
    ],
  }

  const restBudget = daten.budget != null ? daten.budget + daten.ist_gesamt : null

  return (
    <div className="card p-4 mt-4">
      <h3 className="font-semibold text-gray-800 mb-3">Budget vs. Ist – {projektName}</h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="bg-gray-50 rounded p-3 text-center">
          <div className="text-xs text-gray-500 mb-1">Budget</div>
          <div className="font-semibold">{fmt(daten.budget)}</div>
        </div>
        <div className="bg-red-50 rounded p-3 text-center">
          <div className="text-xs text-gray-500 mb-1">Ausgaben (Ist)</div>
          <div className="font-semibold text-red-600">{fmt(daten.ist_gesamt)}</div>
        </div>
        {restBudget != null && (
          <div className={`rounded p-3 text-center ${restBudget >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
            <div className="text-xs text-gray-500 mb-1">Rest</div>
            <div className={`font-semibold ${restBudget >= 0 ? 'text-green-600' : 'text-red-600'}`}>{fmt(restBudget)}</div>
          </div>
        )}
        {einnahmen.length > 0 && (
          <div className="bg-green-50 rounded p-3 text-center">
            <div className="text-xs text-gray-500 mb-1">Einnahmen (Ist)</div>
            <div className="font-semibold text-green-600">{fmt(einnahmen.reduce((s, k) => s + k.ist_summe, 0))}</div>
          </div>
        )}
      </div>

      {ausgaben.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Bar data={chartData} options={{ responsive: true, plugins: { legend: { display: false } } }} />
          <div className="overflow-auto max-h-64">
            <table className="min-w-full text-sm">
              <thead className="text-gray-500 text-xs uppercase">
                <tr>
                  <th className="text-left py-1">Kategorie</th>
                  <th className="text-right py-1">Summe</th>
                  <th className="text-right py-1">Anz.</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {daten.kategorien.map((k, i) => (
                  <tr key={i} className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                    <td className="py-1">{k.kategorie}</td>
                    <td className={`py-1 text-right font-mono ${k.ist_summe < 0 ? 'text-red-500' : 'text-green-600'}`}>{fmt(k.ist_summe)}</td>
                    <td className="py-1 text-right text-gray-500">{k.anzahl}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {ausgaben.length === 0 && <p className="text-gray-400 text-sm">Keine Buchungen für dieses Projekt</p>}
    </div>
  )
}

function PostenForm({ projektId, posten, kategorien, darlehenKonten, onClose, onSaved }) {
  const [form, setForm] = useState(
    posten ?? { bezeichnung: '', betrag: '', notiz: '', kategorie_id: '', erledigt: false, darlehen_konto_id: null }
  )

  const save = async (e) => {
    e.preventDefault()
    const body = {
      bezeichnung: form.bezeichnung,
      betrag: parseFloat(form.betrag),
      notiz: form.notiz || null,
      kategorie_id: form.kategorie_id ? parseInt(form.kategorie_id) : null,
      erledigt: !!form.erledigt,
      darlehen_konto_id: form.darlehen_konto_id ? parseInt(form.darlehen_konto_id) : null,
    }
    if (posten?.id) await projekteApi.posten.update(projektId, posten.id, body)
    else await projekteApi.posten.create(projektId, body)
    onSaved()
  }

  return (
    <form onSubmit={save}>
      <Modal
        onClose={onClose}
        title={posten?.id ? 'Posten bearbeiten' : 'Neuer Posten'}
        maxWidth="max-w-md"
        footer={
          <div className="flex gap-2">
            <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
            <button type="button" className="btn-secondary" onClick={onClose}>Abbrechen</button>
          </div>
        }
      >
        <div><label className="label">Bezeichnung*</label><input className="input" required autoFocus value={form.bezeichnung} onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })} /></div>
        <div><label className="label">Geplanter Betrag (€)*</label><CurrencyInput required value={form.betrag ?? ''} onChange={(n) => setForm({ ...form, betrag: n ?? '' })} /></div>
        <div>
          <label className="label">Kategorie</label>
          <KategorieSelect
            kategorien={kategorien}
            value={form.kategorie_id}
            onChange={id => setForm({ ...form, kategorie_id: id })}
          />
        </div>
        {darlehenKonten.length > 0 && (
          <div>
            <label className="label">Darlehenskonto (Vorfilter beim Verknüpfen)</label>
            <select
              className="input"
              value={form.darlehen_konto_id ?? ''}
              onChange={(e) => setForm({ ...form, darlehen_konto_id: e.target.value ? parseInt(e.target.value) : null })}
            >
              <option value="">– keines –</option>
              {auswaehlbareKonten(darlehenKonten, form.darlehen_konto_id).map((k) => (
                <option key={k.id} value={k.id}>{k.name}{k.aktiv ? '' : ' (inaktiv)'}</option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">
              Setzt nur die Konto-Vorauswahl im Verknüpfen-Dialog. Buchungen werden dadurch nicht automatisch zugerechnet.
            </p>
          </div>
        )}
        <div><label className="label">Notiz</label><textarea className="input" rows={2} value={form.notiz ?? ''} onChange={(e) => setForm({ ...form, notiz: e.target.value })} /></div>
        <div className="flex items-center gap-2">
          <input type="checkbox" id="posten-erledigt" checked={!!form.erledigt} onChange={(e) => setForm({ ...form, erledigt: e.target.checked })} />
          <label htmlFor="posten-erledigt" className="text-sm">Erledigt</label>
        </div>
      </Modal>
    </form>
  )
}

function VerknuepfenModal({ projektId, posten, konten, onClose, onChanged }) {
  const [suche, setSuche] = useState('')
  const [kontoFilter, setKontoFilter] = useState(posten.darlehen_konto_id ?? '')
  const [treffer, setTreffer] = useState([])
  const [lade, setLade] = useState(false)

  const darlehenKonten = konten.filter((k) => k.typ === 'darlehen')

  const suchen = async (e) => {
    e?.preventDefault()
    setLade(true)
    const params = { pro_seite: 50, seite: 1 }
    if (suche) params.suche = suche
    if (kontoFilter) params.konto_id = kontoFilter
    const r = await buchungenApi.list(params)
    // Nur Buchungen anzeigen, die noch keinem anderen Posten zugeordnet sind
    setTreffer(r.data.items.filter((b) => !b.geplante_ausgabe_id || b.geplante_ausgabe_id === posten.id))
    setLade(false)
  }

  useEffect(() => { suchen() }, [])

  const verknuepfe = async (bid) => {
    await projekteApi.posten.verknuepfen(projektId, posten.id, [bid])
    setTreffer((t) => t.map((b) => b.id === bid ? { ...b, geplante_ausgabe_id: posten.id } : b))
    onChanged()
  }

  return (
    <Modal
      onClose={onClose}
      title={`Buchungen verknüpfen – ${posten.bezeichnung}`}
      maxWidth="max-w-2xl"
      footer={
        <div className="flex justify-end">
          <button className="btn-primary" onClick={onClose}>Fertig</button>
        </div>
      }
    >
      <form onSubmit={suchen} className="sticky top-0 z-10 bg-white flex gap-2 flex-wrap pb-2">
        {darlehenKonten.length > 0 && (
          <select
            className="input w-auto"
            value={kontoFilter}
            onChange={(e) => setKontoFilter(e.target.value ? parseInt(e.target.value) : '')}
          >
            <option value="">Alle Konten</option>
            {auswaehlbareKonten(darlehenKonten, kontoFilter).map((k) => (
              <option key={k.id} value={k.id}>{k.name}{k.aktiv ? '' : ' (inaktiv)'}</option>
            ))}
          </select>
        )}
        <input className="input flex-1 min-w-0" placeholder="Suche Empfänger/Notiz…" value={suche} onChange={(e) => setSuche(e.target.value)} />
        <button type="submit" className="btn-secondary">Suchen</button>
      </form>
      {lade && <p className="text-gray-400 text-sm">Lade…</p>}
      {!lade && treffer.length === 0 && <p className="text-gray-400 text-sm">Keine Buchungen gefunden</p>}
      <table className="min-w-full text-sm">
        <tbody className="divide-y divide-gray-100">
          {treffer.map((b) => {
            const verknuepft = b.geplante_ausgabe_id === posten.id
            return (
              <tr key={b.id} className="hover:bg-blue-50">
                <td className="py-1.5 text-gray-500 whitespace-nowrap pr-3">{b.datum}</td>
                <td className="py-1.5 pr-3">{b.empfaenger || <span className="text-gray-400">–</span>}</td>
                <td className={`py-1.5 text-right font-mono pr-3 ${b.betrag < 0 ? 'text-red-500' : 'text-green-600'}`}>{fmt(b.betrag)}</td>
                <td className="py-1.5 text-right">
                  {verknuepft
                    ? <span className="badge badge-gray">verknüpft</span>
                    : <button className="btn-secondary btn-sm" onClick={() => verknuepfe(b.id)}>+ verknüpfen</button>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Modal>
  )
}

function Planung({ projektId, projektName, isAdmin, confirm, darlehenKonten, konten }) {
  const { openHilfe } = useHilfe()
  const [daten, setDaten] = useState(null)
  const [kategorien, setKategorien] = useState([])
  const [postenForm, setPostenForm] = useState(null)
  const [verknuepfenPosten, setVerknuepfenPosten] = useState(null)
  const [expandiert, setExpandiert] = useState({})

  const load = () => projekteApi.planVsIst(projektId).then((r) => setDaten(r.data))
  useEffect(() => { load() }, [projektId])
  useEffect(() => { kategorienApi.flat().then((r) => setKategorien(r.data)) }, [])

  if (!daten) return <p className="text-gray-400 text-sm p-4">Lade…</p>

  const restBudget = daten.budget != null ? round2(daten.budget - daten.ist_gesamt) : null
  const restPlan = daten.budget != null ? round2(daten.budget - daten.geplant_gesamt) : null

  const delPosten = async (gid) => {
    if (!await confirm('Posten löschen? Verknüpfte Buchungen bleiben erhalten.')) return
    await projekteApi.posten.delete(projektId, gid)
    load()
  }

  const loesen = async (gid, bid) => {
    await projekteApi.posten.loesen(projektId, gid, [bid])
    load()
  }

  return (
    <div className="card p-4 mt-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-800">Planung – {projektName}</h3>
          <button type="button" onClick={() => openHilfe('projekte-plan-ist')} className="text-xs text-blue-600 hover:underline">Hilfe dazu</button>
        </div>
        {isAdmin && <button className="btn-primary btn-sm" onClick={() => setPostenForm({})}>+ Posten</button>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="bg-gray-50 rounded p-3 text-center">
          <div className="text-xs text-gray-500 mb-1">Budget</div>
          <div className="font-semibold">{fmt(daten.budget)}</div>
        </div>
        <div className="bg-blue-50 rounded p-3 text-center">
          <div className="text-xs text-gray-500 mb-1">Geplant gesamt</div>
          <div className="font-semibold text-blue-700">{fmt(daten.geplant_gesamt)}</div>
        </div>
        <div className="bg-red-50 rounded p-3 text-center">
          <div className="text-xs text-gray-500 mb-1">Ist gesamt</div>
          <div className="font-semibold text-red-600">{fmt(daten.ist_gesamt)}</div>
        </div>
        {restBudget != null && (
          <div className={`rounded p-3 text-center ${restBudget >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
            <div className="text-xs text-gray-500 mb-1">Ergebnis (Budget − Ist)</div>
            <div className={`font-semibold ${restBudget >= 0 ? 'text-green-600' : 'text-red-600'}`}>{fmt(restBudget)}</div>
          </div>
        )}
      </div>

      {restPlan != null && (
        <div className="text-xs text-gray-500 mb-3">Noch nicht verplant (Budget − Geplant): <span className={restPlan >= 0 ? 'text-green-600' : 'text-red-600'}>{fmt(restPlan)}</span></div>
      )}

      {daten.posten.length === 0 && <p className="text-gray-400 text-sm">Noch keine geplanten Ausgaben. {isAdmin && 'Lege oben einen Posten an.'}</p>}

      {daten.posten.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-gray-500 text-xs uppercase border-b">
              <tr>
                <th className="text-left py-2 pr-3">Posten</th>
                <th className="text-right py-2 px-3">Geplant</th>
                <th className="text-right py-2 px-3">Ist</th>
                <th className="text-right py-2 px-3">Abweichung</th>
                <th className="text-center py-2 px-3">Buchungen</th>
                {isAdmin && <th className="text-right py-2 pl-3">Aktion</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {daten.posten.map((p) => {
                const offen = expandiert[p.id]
                return (
                  <Fragment key={p.id}>
                    <tr className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                      <td className="py-2 pr-3">
                        <div className="flex items-center gap-2">
                          {p.erledigt && <span className="badge badge-gray">erledigt</span>}
                          <span className={p.erledigt ? 'line-through text-gray-400' : ''}>{p.bezeichnung}</span>
                        </div>
                        {p.notiz && <div className="text-xs text-gray-400">{p.notiz}</div>}
                      </td>
                      <td className={`py-2 px-3 text-right font-mono ${p.betrag < 0 ? 'text-green-600' : ''}`}>{fmt(p.betrag)}</td>
                      <td className={`py-2 px-3 text-right font-mono ${p.ist < 0 ? 'text-green-600' : ''}`}>{fmt(p.ist)}</td>
                      <td className={`py-2 px-3 text-right font-mono ${p.abweichung > 0 ? 'text-red-500' : 'text-green-600'}`}>
                        {p.abweichung > 0 ? '+' : ''}{fmt(p.abweichung)}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <button className="text-blue-600 hover:underline" onClick={() => setExpandiert({ ...expandiert, [p.id]: !offen })}>
                          {p.anzahl_buchungen} {offen ? '▲' : '▼'}
                        </button>
                      </td>
                      {isAdmin && (
                        <td className="py-2 pl-3 text-right whitespace-nowrap">
                          <button className="btn-secondary btn-sm h-9" onClick={() => setVerknuepfenPosten(p)}>Verknüpfen</button>
                          <button className="btn-secondary btn-icon ml-1" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setPostenForm(p)}><PencilIcon /></button>
                          <button className="btn-danger btn-icon ml-1" title="Löschen" aria-label="Löschen" onClick={() => delPosten(p.id)}>×</button>
                        </td>
                      )}
                    </tr>
                    {offen && (
                      <tr className="bg-gray-50">
                        <td colSpan={isAdmin ? 6 : 5} className="px-3 py-2">
                          {p.buchungen.length === 0 && <span className="text-gray-400 text-xs">Keine verknüpften Buchungen</span>}
                          {p.buchungen.map((b) => (
                            <div key={b.id} className="flex items-center gap-3 text-xs py-0.5">
                              <span className="text-gray-500 w-24">{b.datum}</span>
                              <span className="flex-1">{b.empfaenger || '–'}</span>
                              <span className={`font-mono ${b.betrag < 0 ? 'text-red-500' : 'text-green-600'}`}>{fmt(b.betrag)}</span>
                              {isAdmin && <button className="text-red-400 hover:text-red-600" title="Verknüpfung lösen" onClick={() => loesen(p.id, b.id)}>×</button>}
                            </div>
                          ))}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {postenForm && (
        <PostenForm
          projektId={projektId}
          posten={postenForm.id ? postenForm : null}
          kategorien={kategorien}
          darlehenKonten={darlehenKonten}
          onClose={() => setPostenForm(null)}
          onSaved={() => { setPostenForm(null); load() }}
        />
      )}
      {verknuepfenPosten && (
        <VerknuepfenModal
          projektId={projektId}
          posten={verknuepfenPosten}
          konten={konten}
          onClose={() => { setVerknuepfenPosten(null); load() }}
          onChanged={load}
        />
      )}
    </div>
  )
}

export default function Projekte() {
  const { confirm, dialog } = useConfirm()
  const { user } = useAuth()
  const [projekte, setProjekte] = useState([])
  const [selected, setSelected] = useState(null)
  const [raten, setRaten] = useState([])
  const [detailTab, setDetailTab] = useState('tabelle')
  const [form, setForm] = useState(null)
  const [konten, setKonten] = useState([])
  const [summaries, setSummaries] = useState({})
  const isAdmin = user?.rolle === 'admin'

  const loadSummaries = (liste) => {
    Promise.all(liste.map((p) => projekteApi.planVsIst(p.id).then((r) => ({ id: p.id, data: r.data }))))
      .then((results) => {
        const map = {}
        results.forEach((r) => { map[r.id] = r.data })
        setSummaries(map)
      })
  }

  const load = () => { projekteApi.list().then((r) => { setProjekte(r.data); loadSummaries(r.data) }) }
  useEffect(load, [])
  useEffect(() => { kontenApi.list(false).then((r) => setKonten(r.data)) }, [])
  const darlehenKonten = konten.filter((k) => k.typ === 'darlehen')

  const selectProjekt = (p) => {
    setSelected(p)
    setDetailTab('tabelle')
    if (p.typ === 'darlehen') {
      projekteApi.darlehen(p.id).then((r) => setRaten(r.data))
    } else {
      setRaten([])
    }
  }

  const save = async (e) => {
    e.preventDefault()
    if (form.id) await projekteApi.update(form.id, form)
    else await projekteApi.create(form)
    setForm(null)
    load()
  }

  const del = async (id) => {
    if (!await confirm('Projekt löschen?')) return
    await projekteApi.delete(id)
    if (selected?.id === id) setSelected(null)
    load()
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Projekte</h2>
        {isAdmin && <button className="btn-primary" onClick={() => setForm({ name: '', typ: 'sonstiges', budget: '', start_datum: '', ende_datum: '' })}>+ Neu</button>}
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {projekte.map((p) => (
          <div
            key={p.id}
            onClick={() => selectProjekt(p)}
            className={`card cursor-pointer transition-colors ${selected?.id === p.id ? 'border-blue-400 bg-blue-50' : 'hover:border-gray-300'}`}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold">{p.name}</div>
                <div className="flex gap-1 mt-1">
                  <span className="badge badge-gray">{p.typ}</span>
                  {!p.aktiv && <span className="badge badge-gray">inaktiv</span>}
                </div>
              </div>
              {isAdmin && (
                <div className="flex gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
                  <button className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setForm({ ...p })}><PencilIcon /></button>
                  <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => del(p.id)}>×</button>
                </div>
              )}
            </div>
            {p.budget != null && (
              <div className="mt-2 text-sm text-gray-600">Budget: {fmt(p.budget)}</div>
            )}
            {p.budget != null && summaries[p.id] && (() => {
              const rest = round2(p.budget - summaries[p.id].ist_gesamt)
              return <div className={`text-xs mt-0.5 font-medium ${rest >= 0 ? 'text-green-600' : 'text-red-500'}`}>Ergebnis: {fmt(rest)}</div>
            })()}
            {p.start_datum && <div className="text-xs text-gray-400 mt-0.5">ab {p.start_datum}</div>}
          </div>
        ))}
      </div>

      {/* Detail-Bereich mit Tabs */}
      {selected && (() => {
        const tabs = []
        if (selected.typ === 'darlehen' && raten.length > 0) {
          tabs.push(['tabelle', 'Tilgungsplan'], ['kurve', 'Restschuld-Verlauf'])
        }
        tabs.push(['planung', 'Planung'], ['budget', 'Budget vs. Ist'])
        const aktiv = tabs.some(([k]) => k === detailTab) ? detailTab : tabs[0][0]

        return (
          <div className="space-y-2">
            <div className="flex gap-2 border-b border-gray-200">
              {tabs.map(([k, label]) => (
                <button
                  key={k}
                  onClick={() => setDetailTab(k)}
                  className={`px-4 py-2 text-sm font-medium rounded-t border-b-2 transition-colors ${
                    aktiv === k ? 'border-blue-500 text-blue-600 bg-white' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {aktiv === 'tabelle' && (
              <div className="card p-0 overflow-x-auto">
                <div className="px-4 py-3 border-b font-semibold">Tilgungsplan – {selected.name}</div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
                      <th className="px-3 py-2 font-medium">Datum</th>
                      <th className="px-3 py-2 font-medium text-right">Restschuld</th>
                      <th className="px-3 py-2 font-medium text-right">Tilgung</th>
                      <th className="px-3 py-2 font-medium text-right">Zinsen</th>
                      <th className="px-3 py-2 font-medium text-right">Einzahlung</th>
                    </tr>
                  </thead>
                  <tbody>
                    {raten.map((r) => (
                      <tr key={r.id} className="border-b odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                        <td className="px-3 py-1.5 text-gray-500">{r.datum}</td>
                        <td className="px-3 py-1.5 text-right font-mono">{fmt(r.restschuld)}</td>
                        <td className="px-3 py-1.5 text-right font-mono">{fmt(r.tilgung)}</td>
                        <td className="px-3 py-1.5 text-right font-mono">{fmt(r.zinsen)}</td>
                        <td className="px-3 py-1.5 text-right font-mono">{fmt(r.einzahlung)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {aktiv === 'kurve' && <DarlehenKurve raten={raten} name={selected.name} />}
            {aktiv === 'planung' && <Planung projektId={selected.id} projektName={selected.name} isAdmin={isAdmin} confirm={confirm} darlehenKonten={darlehenKonten} konten={konten} />}
            {aktiv === 'budget' && <BudgetVsIst projektId={selected.id} projektName={selected.name} />}
          </div>
        )
      })()}

      {form && (
        <form onSubmit={save}>
          <Modal
            onClose={() => setForm(null)}
            title={form.id ? 'Projekt bearbeiten' : 'Neues Projekt'}
            maxWidth="max-w-md"
            footer={
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
                <button type="button" className="btn-secondary" onClick={() => setForm(null)}>Abbrechen</button>
              </div>
            }
          >
            <div><label className="label">Name*</label><input className="input" required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div>
              <label className="label">Typ*</label>
              <select className="input" value={form.typ} onChange={(e) => setForm({ ...form, typ: e.target.value })}>
                {TYPEN.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div><label className="label">Budget (€)</label><CurrencyInput value={form.budget ?? ''} onChange={(n) => setForm({ ...form, budget: n ?? null })} /></div>
            {form.typ === 'darlehen' && (
              <div>
                <label className="label">Darlehenskonto</label>
                <select className="input" value={form.darlehen_konto_id ?? ''} onChange={(e) => setForm({ ...form, darlehen_konto_id: e.target.value ? parseInt(e.target.value) : null })}>
                  <option value="">– keines –</option>
                  {auswaehlbareKonten(darlehenKonten, form.darlehen_konto_id).map((k) => (
                    <option key={k.id} value={k.id}>{k.name}{k.aktiv ? '' : ' (inaktiv)'}</option>
                  ))}
                </select>
                {darlehenKonten.length === 0 && <p className="text-xs text-gray-400 mt-1">Kein Konto mit Typ „Darlehen" vorhanden.</p>}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div><label className="label">Start</label><input className="input" type="date" value={form.start_datum ?? ''} onChange={(e) => setForm({ ...form, start_datum: e.target.value || null })} /></div>
              <div><label className="label">Ende</label><input className="input" type="date" value={form.ende_datum ?? ''} onChange={(e) => setForm({ ...form, ende_datum: e.target.value || null })} /></div>
            </div>
            {form.id && (
              <div className="flex items-center gap-2">
                <input type="checkbox" id="aktiv" checked={form.aktiv ?? true} onChange={(e) => setForm({ ...form, aktiv: e.target.checked })} />
                <label htmlFor="aktiv" className="text-sm">Aktiv</label>
              </div>
            )}
          </Modal>
        </form>
      )}
      {dialog}
    </div>
  )
}
