import { useState, useEffect } from 'react'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, LineElement, PointElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { statistikApi, kontenApi, generierungApi } from '../api'
import { useHilfe } from '../HilfeContext'

ChartJS.register(CategoryScale, LinearScale, LineElement, PointElement, Title, Tooltip, Legend, Filler)

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n ?? 0)
}

export default function Liquiditaet() {
  const { openHilfe } = useHilfe()
  const [konten, setKonten] = useState([])
  const [kontoId, setKontoId] = useState('')
  const [monate, setMonate] = useState(12)
  const [daten, setDaten] = useState(null)
  const [generInfo, setGenerInfo] = useState(null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [meldung, setMeldung] = useState(null)

  useEffect(() => {
    kontenApi.list().then(r => setKonten(r.data))
  }, [])

  useEffect(() => {
    setLoading(true)
    statistikApi.liquiditaet({ konto_id: kontoId || undefined, monate })
      .then(r => setDaten(r.data))
      .finally(() => setLoading(false))
  }, [kontoId, monate])

  const handleGenerierungVorschau = async () => {
    const r = await generierungApi.vorschau(monate, kontoId || undefined)
    setGenerInfo(r.data)
  }

  const handleGenerierungAusfuehren = async () => {
    setGenerating(true)
    try {
      const r = await generierungApi.ausfuehren(monate, kontoId || undefined)
      setMeldung(`${r.data.erstellt} geplante Buchungen wurden erzeugt.`)
      // Vorschau neu laden
      const r2 = await statistikApi.liquiditaet({ konto_id: kontoId || undefined, monate })
      setDaten(r2.data)
      setGenerInfo(null)
    } finally {
      setGenerating(false)
    }
  }

  const verlauf = daten?.verlauf ?? []
  const labels = verlauf.map(p => p.monat)
  const werte = verlauf.map(p => p.saldo)

  const chartData = {
    labels,
    datasets: [{
      label: 'Kontostand',
      data: werte,
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: verlauf.length > 20 ? 2 : 4,
    }],
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
        <h1 className="text-xl font-bold text-gray-900">Liquiditätsvorschau</h1>
        <button type="button" onClick={() => openHilfe('wiederkehrend-liquiditaet')} className="text-sm text-blue-600 hover:underline">Hilfe dazu</button>
      </div>

      {/* Filter */}
      <div className="card p-4 mb-4 flex flex-wrap gap-4 items-end">
        <div>
          <label className="label">Konto</label>
          <select className="input" value={kontoId} onChange={e => setKontoId(e.target.value)}>
            <option value="">Alle Girokonten zusammen</option>
            {konten.filter(k => k.typ === 'giro').map(k => (
              <option key={k.id} value={k.id}>{k.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Vorschau-Zeitraum</label>
          <select className="input" value={monate} onChange={e => setMonate(Number(e.target.value))}>
            {[3, 6, 12, 18, 24].map(m => (
              <option key={m} value={m}>{m} Monate</option>
            ))}
          </select>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={handleGenerierungVorschau}>
          Geplante Buchungen prüfen
        </button>
      </div>

      {meldung && (
        <div className="card p-4 mb-4 bg-green-50 border border-green-200 flex items-center justify-between">
          <span className="text-sm text-green-800">{meldung}</span>
          <button className="text-green-600 hover:text-green-800 text-lg leading-none ml-4" onClick={() => setMeldung(null)}>×</button>
        </div>
      )}

      {/* Generierungs-Info */}
      {generInfo && (
        <div className="card p-4 mb-4 bg-yellow-50 border border-yellow-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-yellow-800">
                {generInfo.anzahl} geplante Buchungen aus wiederkehrenden Vorlagen
              </p>
              <p className="text-xs text-yellow-600 mt-0.5">
                Diese werden als Status "geplant" in die Buchungsliste eingetragen.
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="btn btn-primary btn-sm"
                onClick={handleGenerierungAusfuehren}
                disabled={generInfo.anzahl === 0 || generating}
              >
                {generating ? 'Erzeuge…' : 'Buchungen erzeugen'}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => setGenerInfo(null)}>
                Schließen
              </button>
            </div>
          </div>
          {generInfo.buchungen.length > 0 && (
            <div className="mt-3 max-h-48 overflow-auto">
              <table className="min-w-full text-xs">
                <thead className="text-gray-500">
                  <tr>
                    <th className="text-left py-0.5">Datum</th>
                    <th className="text-left py-0.5">Empfänger</th>
                    <th className="text-right py-0.5">Betrag</th>
                  </tr>
                </thead>
                <tbody>
                  {generInfo.buchungen.slice(0, 50).map((b, i) => (
                    <tr key={i} className="border-t border-yellow-100 odd:bg-white even:bg-yellow-50">
                      <td className="py-0.5">{b.datum}</td>
                      <td className="py-0.5">{b.empfaenger ?? '–'}</td>
                      <td className={`py-0.5 text-right ${b.betrag < 0 ? 'text-red-500' : 'text-green-600'}`}>
                        {fmt(b.betrag)}
                      </td>
                    </tr>
                  ))}
                  {generInfo.buchungen.length > 50 && (
                    <tr>
                      <td colSpan={3} className="py-0.5 text-gray-400">… und {generInfo.buchungen.length - 50} weitere</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Kontostand-Karte */}
      {daten && (
        <div className="card p-4 mb-4 flex items-center gap-6">
          <div>
            <p className="text-sm text-gray-500">Aktueller Saldo</p>
            <p className={`text-2xl font-bold ${daten.saldo_heute >= 0 ? 'text-green-700' : 'text-red-600'}`}>
              {fmt(daten.saldo_heute)}
            </p>
          </div>
          {verlauf.length > 1 && (
            <div>
              <p className="text-sm text-gray-500">Saldo in {monate} Monaten (geplant)</p>
              <p className={`text-2xl font-bold ${verlauf[verlauf.length - 1]?.saldo >= 0 ? 'text-blue-700' : 'text-red-600'}`}>
                {fmt(verlauf[verlauf.length - 1]?.saldo)}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Chart */}
      {loading
        ? <div className="text-gray-400 text-sm">Lade…</div>
        : verlauf.length > 1 && (
          <div className="card p-4">
            <Line data={chartData} options={{
              responsive: true,
              plugins: { legend: { display: false } },
              scales: {
                y: {
                  ticks: {
                    callback: v => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v)
                  }
                }
              }
            }} />
          </div>
        )
      }

      {!loading && verlauf.length <= 1 && (
        <div className="card p-6 text-center text-gray-400">
          Keine geplanten Buchungen im Zeitraum.<br/>
          Füge wiederkehrende Buchungen hinzu und klicke "Buchungen erzeugen".
        </div>
      )}
    </div>
  )
}
