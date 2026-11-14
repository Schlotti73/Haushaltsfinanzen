import { useState, useEffect } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement,
  ArcElement, LineElement, PointElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { Bar, Doughnut, Line } from 'react-chartjs-2'
import { statistikApi } from '../api'

ChartJS.register(
  CategoryScale, LinearScale, BarElement,
  ArcElement, LineElement, PointElement,
  Title, Tooltip, Legend,
)

const MONATE = ['Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun',
                'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

function fmt(n) {
  if (n == null) return '–'
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

function TabBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-t border-b-2 transition-colors ${
        active
          ? 'border-blue-500 text-blue-600 bg-white'
          : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
    >
      {children}
    </button>
  )
}

// ── Monatsübersicht ───────────────────────────────────────────────────────────

function MonatsChart() {
  const [daten, setDaten] = useState([])
  const [jahr, setJahr] = useState(new Date().getFullYear())

  useEffect(() => {
    statistikApi.monats({ jahr }).then(r => setDaten(r.data))
  }, [jahr])

  const labels = daten.map(r => `${r.jahr}-${r.monat}`)
  const chartData = {
    labels,
    datasets: [
      {
        label: 'Einnahmen',
        data: daten.map(r => r.einnahmen),
        backgroundColor: 'rgba(34,197,94,0.7)',
      },
      {
        label: 'Ausgaben',
        data: daten.map(r => Math.abs(r.ausgaben)),
        backgroundColor: 'rgba(239,68,68,0.7)',
      },
    ],
  }

  return (
    <div className="card p-4">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-semibold text-gray-800">Monatsübersicht</h2>
        <select
          className="input py-1 text-sm"
          value={jahr}
          onChange={e => setJahr(Number(e.target.value))}
        >
          {[2017,2018,2019,2020,2021,2022,2023,2024,2025,2026].map(y => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>
      {daten.length === 0
        ? <p className="text-gray-400 text-sm">Keine Daten</p>
        : <Bar data={chartData} options={{ responsive: true, plugins: { legend: { position: 'top' } } }} />
      }
      {daten.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left py-1">Monat</th>
                <th className="text-right py-1">Einnahmen</th>
                <th className="text-right py-1">Ausgaben</th>
                <th className="text-right py-1">Saldo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {daten.map(r => (
                <tr key={`${r.jahr}-${r.monat}`} className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                  <td className="py-1">{MONATE[Number(r.monat)-1]} {r.jahr}</td>
                  <td className="py-1 text-right text-green-600">{fmt(r.einnahmen)}</td>
                  <td className="py-1 text-right text-red-500">{fmt(r.ausgaben)}</td>
                  <td className={`py-1 text-right font-medium ${r.saldo >= 0 ? 'text-green-700' : 'text-red-600'}`}>{fmt(r.saldo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Jahresübersicht ───────────────────────────────────────────────────────────

function JahresChart() {
  const [daten, setDaten] = useState([])

  useEffect(() => {
    statistikApi.jahres().then(r => setDaten(r.data))
  }, [])

  const chartData = {
    labels: daten.map(r => r.jahr),
    datasets: [
      {
        label: 'Einnahmen',
        data: daten.map(r => r.einnahmen),
        backgroundColor: 'rgba(34,197,94,0.7)',
      },
      {
        label: 'Ausgaben',
        data: daten.map(r => Math.abs(r.ausgaben)),
        backgroundColor: 'rgba(239,68,68,0.7)',
      },
      {
        label: 'Saldo',
        data: daten.map(r => r.saldo),
        type: 'line',
        borderColor: 'rgba(59,130,246,0.9)',
        backgroundColor: 'transparent',
        tension: 0.3,
      },
    ],
  }

  return (
    <div className="card p-4">
      <h2 className="font-semibold text-gray-800 mb-4">Jahresübersicht</h2>
      {daten.length === 0
        ? <p className="text-gray-400 text-sm">Keine Daten</p>
        : <Bar data={chartData} options={{ responsive: true }} />
      }
    </div>
  )
}

// ── Kategorien-Auswertung ─────────────────────────────────────────────────────

function KategorienChart() {
  const [daten, setDaten] = useState([])
  const [jahr, setJahr] = useState(new Date().getFullYear())

  useEffect(() => {
    statistikApi.kategorien({ jahr, nur_ausgaben: true }).then(r => setDaten(r.data))
  }, [jahr])

  // Nur Top-15 im Donut
  const top = [...daten].sort((a, b) => a.summe - b.summe).slice(0, 15)
  const colors = [
    '#ef4444','#f97316','#eab308','#22c55e','#14b8a6',
    '#3b82f6','#8b5cf6','#ec4899','#64748b','#0ea5e9',
    '#84cc16','#f59e0b','#10b981','#6366f1','#d946ef',
  ]

  const chartData = {
    labels: top.map(r => r.kategorie),
    datasets: [{
      data: top.map(r => Math.abs(r.summe)),
      backgroundColor: colors,
    }],
  }

  return (
    <div className="card p-4">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-semibold text-gray-800">Ausgaben nach Kategorie</h2>
        <select
          className="input py-1 text-sm"
          value={jahr}
          onChange={e => setJahr(Number(e.target.value))}
        >
          {[2017,2018,2019,2020,2021,2022,2023,2024,2025,2026].map(y => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="max-w-xs mx-auto">
          {top.length === 0
            ? <p className="text-gray-400 text-sm">Keine Daten</p>
            : <Doughnut data={chartData} options={{ plugins: { legend: { position: 'right' } } }} />
          }
        </div>
        <div className="overflow-auto max-h-80">
          <table className="min-w-full text-sm">
            <thead className="text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left py-1">Kategorie</th>
                <th className="text-left py-1">Gruppe</th>
                <th className="text-right py-1">Summe</th>
                <th className="text-right py-1">Anz.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {daten.map(r => (
                <tr key={r.kategorie_id} className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                  <td className="py-1">{r.kategorie}</td>
                  <td className="py-1 text-gray-500">{r.obergruppe !== r.kategorie ? r.obergruppe : ''}</td>
                  <td className="py-1 text-right text-red-500">{fmt(r.summe)}</td>
                  <td className="py-1 text-right text-gray-500">{r.anzahl}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── Geschäfte-Auswertung ──────────────────────────────────────────────────────

function GeschaefteChart() {
  const [daten, setDaten] = useState([])
  const [jahr, setJahr] = useState(new Date().getFullYear())
  // Oberste Ebene: 'geschaeft' oder 'kategorie'. Der Drilldown zeigt jeweils
  // die Gegen-Dimension, gefiltert auf das angeklickte Element.
  const [ebene, setEbene] = useState('geschaeft')
  const [drill, setDrill] = useState(null)   // { id, name } oder null

  // Im Drilldown wird nach der Gegen-Dimension gruppiert und auf das
  // angeklickte Element der Ausgangsebene gefiltert.
  const gruppierung = drill
    ? (ebene === 'geschaeft' ? 'kategorie' : 'geschaeft')
    : ebene

  useEffect(() => {
    const params = { jahr, gruppierung }
    if (drill) params[ebene === 'geschaeft' ? 'geschaeft_id' : 'kategorie_id'] = drill.id
    statistikApi.geschaefte(params).then(r => setDaten(r.data))
  }, [jahr, ebene, gruppierung, drill])

  // Ebenenwechsel verlässt immer den Drilldown – sonst zeigt der Breadcrumb
  // ein Element, nach dem gar nicht mehr gefiltert wird.
  const wechsleEbene = (neu) => { setEbene(neu); setDrill(null) }

  // "Ohne Kategorie" hat keine id und ist daher nicht aufklappbar.
  const istKlickbar = (r) => !drill && r.id != null

  // Top-15 nach Summe für den Balken-Chart (daten kommt bereits absteigend sortiert)
  const top = daten.slice(0, 15)
  const gesamt = daten.reduce((s, r) => s + (r.summe ?? 0), 0)
  const spalte = gruppierung === 'geschaeft' ? 'Geschäft' : 'Kategorie'

  const chartData = {
    labels: top.map(r => r.name),
    datasets: [{
      label: 'Ausgaben',
      data: top.map(r => r.summe),
      backgroundColor: 'rgba(59,130,246,0.7)',
    }],
  }

  return (
    <div className="card p-4">
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <h2 className="font-semibold text-gray-800">Ausgaben nach {spalte}</h2>
        <select
          className="input py-1 text-sm"
          value={jahr}
          onChange={e => setJahr(Number(e.target.value))}
        >
          {[2017,2018,2019,2020,2021,2022,2023,2024,2025,2026].map(y => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        <div className="flex rounded overflow-hidden border border-gray-200 text-sm">
          {[['geschaeft', 'nach Geschäft'], ['kategorie', 'nach Kategorie']].map(([wert, label]) => (
            <button
              key={wert}
              onClick={() => wechsleEbene(wert)}
              className={`px-3 py-1 ${ebene === wert ? 'bg-blue-500 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="text-sm text-gray-500 mb-2">
        <button
          onClick={() => setDrill(null)}
          className={drill ? 'text-blue-600 hover:underline' : ''}
          disabled={!drill}
        >
          {ebene === 'geschaeft' ? 'Geschäfte' : 'Kategorien'}
        </button>
        {drill && <span className="text-gray-700"> › {drill.name}</span>}
      </div>

      <p className="text-xs text-gray-400 mb-3">
        Aus den Haushaltsbuch-Belegen: erfasste Artikel zählen einzeln, der Rest
        des Belegs auf die Standard-Kategorie des Ladens. Unabhängig vom
        Buchungsstatus – kann daher vom Kategorien-Tab abweichen. Gesamt: {fmt(gesamt)}
      </p>
      {daten.length === 0
        ? <p className="text-gray-400 text-sm">Keine Haushaltsbuch-Einträge mit Geschäft für dieses Jahr</p>
        : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <Bar
                data={chartData}
                options={{
                  indexAxis: 'y',
                  responsive: true,
                  plugins: { legend: { display: false } },
                }}
              />
            </div>
            <div className="overflow-auto max-h-96">
              <table className="min-w-full text-sm">
                <thead className="text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="text-left py-1">{spalte}</th>
                    <th className="text-right py-1">Summe</th>
                    <th className="text-right py-1">Belege</th>
                    <th className="text-right py-1">Ø/Beleg</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {daten.map(r => (
                    <tr
                      key={r.id ?? 'ohne'}
                      onClick={() => istKlickbar(r) && setDrill({ id: r.id, name: r.name })}
                      className={`odd:bg-white even:bg-gray-50 hover:bg-blue-50 ${istKlickbar(r) ? 'cursor-pointer' : ''} ${r.id == null ? 'italic text-gray-400' : ''}`}
                    >
                      <td className="py-1 font-medium">{r.name}</td>
                      <td className="py-1 text-right text-red-500">{fmt(r.summe)}</td>
                      <td className="py-1 text-right text-gray-500">{r.anzahl}</td>
                      <td className="py-1 text-right text-gray-500">{fmt(r.schnitt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      }
    </div>
  )
}

// ── Soll/Ist-Vergleich ────────────────────────────────────────────────────────

function SollIst() {
  const [daten, setDaten] = useState([])
  const [jahr, setJahr] = useState(new Date().getFullYear())

  useEffect(() => {
    statistikApi.sollIst(jahr).then(r => setDaten(r.data))
  }, [jahr])

  return (
    <div className="card p-4">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-semibold text-gray-800">Soll / Ist-Vergleich</h2>
        <select
          className="input py-1 text-sm"
          value={jahr}
          onChange={e => setJahr(Number(e.target.value))}
        >
          {[2022,2023,2024,2025,2026].map(y => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>
      {daten.length === 0
        ? <p className="text-gray-400 text-sm">Keine Planungsdaten für dieses Jahr</p>
        : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-gray-500 text-xs uppercase">
                <tr>
                  <th className="text-left py-1">Kategorie</th>
                  <th className="text-right py-1">Plan (Jahr)</th>
                  <th className="text-right py-1">Ist</th>
                  <th className="text-right py-1">Abweichung</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {daten.map(r => (
                  <tr key={r.kategorie_id} className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                    <td className="py-1">{r.kategorie}</td>
                    <td className="py-1 text-right">{fmt(r.plan_jahr)}</td>
                    <td className="py-1 text-right">{fmt(r.ist_summe)}</td>
                    <td className={`py-1 text-right font-medium ${r.abweichung > 0 ? 'text-green-600' : 'text-red-500'}`}>
                      {fmt(r.abweichung)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </div>
  )
}

// ── Sparkonten-Entwicklung ────────────────────────────────────────────────────

function Sparkonten() {
  const [daten, setDaten] = useState({})

  useEffect(() => {
    statistikApi.sparkonten().then(r => setDaten(r.data))
  }, [])

  const kontoNamen = Object.keys(daten)
  if (kontoNamen.length === 0) return (
    <div className="card p-4">
      <h2 className="font-semibold text-gray-800 mb-2">Sparkonten-Entwicklung</h2>
      <p className="text-gray-400 text-sm">Keine Sparkonten gefunden</p>
    </div>
  )

  const alleQuartale = [...new Set(kontoNamen.flatMap(k => daten[k].map(p => p.quartal)))].sort()
  const farben = ['#3b82f6','#22c55e','#f97316','#8b5cf6','#ef4444']

  const chartData = {
    labels: alleQuartale,
    datasets: kontoNamen.map((k, i) => {
      const map = Object.fromEntries(daten[k].map(p => [p.quartal, p.saldo]))
      return {
        label: k,
        data: alleQuartale.map(q => map[q] ?? null),
        borderColor: farben[i % farben.length],
        backgroundColor: 'transparent',
        tension: 0.3,
        spanGaps: true,
      }
    }),
  }

  return (
    <div className="card p-4">
      <h2 className="font-semibold text-gray-800 mb-4">Sparkonten-Entwicklung (quartalsweise)</h2>
      <Line data={chartData} options={{ responsive: true, plugins: { legend: { position: 'top' } } }} />
    </div>
  )
}

// ── Hochrechnung (7.6) ────────────────────────────────────────────────────────

function Hochrechnung() {
  const [daten, setDaten] = useState([])
  const [monate, setMonate] = useState(12)

  useEffect(() => {
    statistikApi.hochrechnung(monate).then(r => setDaten(r.data.verlauf))
  }, [monate])

  const labels = daten.map(r => r.monat)
  const chartData = {
    labels,
    datasets: [
      {
        label: 'Ist (gebucht)',
        data: daten.map(r => r.ist),
        backgroundColor: 'rgba(59,130,246,0.7)',
        type: 'bar',
      },
      {
        label: 'Prognose (wiederkehrend)',
        data: daten.map(r => r.prognose),
        backgroundColor: 'rgba(234,179,8,0.5)',
        borderColor: 'rgba(234,179,8,0.9)',
        type: 'bar',
      },
    ],
  }

  return (
    <div className="card p-4">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="font-semibold text-gray-800">Hochrechnung: Ist vs. Prognose</h2>
        <select className="input py-1 text-sm" value={monate} onChange={e => setMonate(+e.target.value)}>
          {[6, 12, 18, 24].map(m => <option key={m} value={m}>{m} Monate</option>)}
        </select>
      </div>
      <p className="text-xs text-gray-400 mb-3">Blaue Balken = gebuchte Ist-Werte · Gelbe Balken = Prognose aus wiederkehrenden Buchungen</p>
      {daten.length === 0
        ? <p className="text-gray-400 text-sm">Keine Daten</p>
        : <Bar data={chartData} options={{ responsive: true, plugins: { legend: { position: 'top' } } }} />
      }
    </div>
  )
}

// ── Haupt-Seite ───────────────────────────────────────────────────────────────

const TABS = ['Monatsübersicht', 'Jahresübersicht', 'Kategorien', 'Geschäfte', 'Soll/Ist', 'Sparkonten', 'Hochrechnung']

export default function Statistik() {
  const [tab, setTab] = useState(0)

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-900 mb-4">Statistik & Auswertungen</h1>
      <div className="flex flex-wrap border-b border-gray-200 mb-4">
        {TABS.map((t, i) => (
          <TabBtn key={t} active={tab === i} onClick={() => setTab(i)}>{t}</TabBtn>
        ))}
      </div>
      {tab === 0 && <MonatsChart />}
      {tab === 1 && <JahresChart />}
      {tab === 2 && <KategorienChart />}
      {tab === 3 && <GeschaefteChart />}
      {tab === 4 && <SollIst />}
      {tab === 5 && <Sparkonten />}
      {tab === 6 && <Hochrechnung />}
    </div>
  )
}
