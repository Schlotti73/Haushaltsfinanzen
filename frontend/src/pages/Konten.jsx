import { useEffect, useMemo, useState } from 'react'
import { useHilfe } from '../HilfeContext'
import CurrencyInput from '../components/CurrencyInput'
import Modal from '../components/Modal'
import { EyeIcon, EyeOffIcon, PencilIcon } from '../components/icons'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement,
  LineElement, PointElement, Title, Tooltip, Legend,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { kontenApi } from '../api'
import { useAuth } from '../AuthContext'
import { useConfirm } from '../components/useConfirm'

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Title, Tooltip, Legend)

const TYPEN = ['giro', 'spar', 'darlehen', 'kredit', 'depot']

// Kontotypen mit Annuitätsrechnung. 'darlehen' = Baufinanzierung (Anfangstilgung,
// Zinsbindung), 'kredit' = Ratenkredit (feste Laufzeit, kein Zinsbindungskonzept).
const TILGUNGS_TYPEN = ['darlehen', 'kredit']
const istTilgungsTyp = (typ) => TILGUNGS_TYPEN.includes(typ)

const DEPOT_LEER = { isin: null, anteile: null, kurs: null, kurs_datum: null }

// Beim Typwechsel die Felder leeren, die zum neuen Typ nicht gehören – sonst
// hinge z.B. eine Anfangstilgung an einem Ratenkredit oder eine Laufzeit an
// einem Girokonto, die das Formular gar nicht mehr anzeigt.
function typWechselReset(typ) {
  if (typ === 'darlehen') return { laufzeit_monate: null, ...DEPOT_LEER }
  if (typ === 'kredit') {
    return {
      tilgungssatz: null, zinsbindung_jahre: null, vollauszahlung_datum: null,
      darlehen_art: null, ...DEPOT_LEER,
    }
  }
  const ohneTilgung = {
    darlehen_betrag: null, zinssatz: null, effektiver_zinssatz: null, tilgungssatz: null,
    rate: null, tilgung_start: null, vollauszahlung_datum: null,
    zinsbindung_jahre: null, laufzeit_monate: null, darlehen_art: null,
  }
  // Beim Depot bleiben ISIN/Anteile/Kurs natürlich stehen.
  return typ === 'depot' ? ohneTilgung : { ...ohneTilgung, ...DEPOT_LEER }
}

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n ?? 0)
}

// Annuitätenrate aus Betrag, Sollzins und Laufzeit: R = B·i / (1 − (1+i)^−n).
// Bei i = 0 entartet die Formel, dann ist die Rate schlicht B/n.
//
// Bewusst auf den vollen Cent AUFgerundet, nicht kaufmännisch gerundet: bei
// 12.000 € / 5 % / 48 Monate ist die exakte Rate 276,3515 €. Abgerundet auf
// 276,35 € unterzahlt man jeden Monat minimal, sodass nach 48 Raten ein Rest
// von 9 Cent bleibt und die Hochrechnung einen 49. Stummel-Monat anhängt.
// Aufgerundet endet der Kredit exakt nach der vereinbarten Laufzeit, die letzte
// Rate fällt dafür geringfügig kleiner aus – so rechnen auch Banken.
function rateAusLaufzeit(betrag, zinssatzProzent, monate) {
  if (!betrag || !monate || monate <= 0 || zinssatzProzent == null) return null
  const i = parseFloat(zinssatzProzent) / 100 / 12
  const rate = i === 0 ? betrag / monate : (betrag * i) / (1 - Math.pow(1 + i, -monate))
  return Number.isFinite(rate) && rate > 0 ? Math.ceil(rate * 100) / 100 : null
}

function fmtDauer(monate) {
  return `${Math.floor(monate / 12)} J ${monate % 12} M`
}

// Zeichnet eine vertikale Markierung am Jahres-Tick des Zinsbindungsendes (kein extra npm-Paket nötig).
const zinsbindungLiniePlugin = {
  id: 'zinsbindungLinie',
  afterDraw(chart, _args, opts) {
    const jahr = opts?.jahr
    if (jahr == null) return
    const idx = chart.data.labels.indexOf(jahr)
    if (idx === -1) return
    const x = chart.scales.x.getPixelForValue(idx)
    const { top, bottom } = chart.chartArea
    const { ctx } = chart
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(x, top)
    ctx.lineTo(x, bottom)
    ctx.lineWidth = 1.5
    ctx.strokeStyle = 'rgba(217,119,6,0.8)'
    ctx.setLineDash([4, 4])
    ctx.stroke()
    ctx.restore()
  },
}

// Detailansicht für beide Tilgungstypen. Beim Ratenkredit entfällt die
// Was-wäre-wenn-Simulation: sie parametrisiert einen neuen Tilgungssatz, was bei
// fester Laufzeit fachlich kein sinnvoller Hebel ist.
function DarlehenDetail({ konto, isAdmin, confirm }) {
  const istKredit = konto.typ === 'kredit'
  // Endfälliges Darlehen (Zwischenfinanzierung): keine Tilgung, keine Rate, keine
  // Sondertilgungen (Rückführungen laufen als normale Buchung) und keine Simulation
  // (die parametrisiert eine Anfangstilgung, die es hier nicht gibt).
  const istEndfaellig = konto.darlehen_art === 'endfaellig'
  const bezeichnung = istEndfaellig ? 'Zwischenfinanzierung' : istKredit ? 'Kredit' : 'Darlehen'
  const { openHilfe } = useHilfe()
  const [data, setData] = useState(null)
  const [mitSonder, setMitSonder] = useState(true)
  const [sonder, setSonder] = useState([])
  const [sForm, setSForm] = useState(null)
  const [zeigeAlleMonate, setZeigeAlleMonate] = useState(false)
  const [szenarioOffen, setSzenarioOffen] = useState(false)
  const [szenarioForm, setSzenarioForm] = useState({ tilgungssatz: '', zusatz: '' })
  const [szenarioData, setSzenarioData] = useState(null)
  const [szenarioFehler, setSzenarioFehler] = useState(null)
  const [szenarioLoading, setSzenarioLoading] = useState(false)

  const load = () => {
    kontenApi.hochrechnung(konto.id, mitSonder).then((r) => setData(r.data))
    if (!istEndfaellig) kontenApi.sondertilgungen(konto.id).then((r) => setSonder(r.data))
  }
  useEffect(load, [konto.id, mitSonder])

  if (!data) return <p className="text-gray-400 text-sm p-4">Lade…</p>

  if (!data.konfiguriert) {
    return (
      <div className="card p-4 mt-2">
        <div className="flex items-center justify-between gap-2 mb-2">
          <h3 className="font-semibold">{bezeichnung} – {konto.name}</h3>
          <button type="button" onClick={() => openHilfe('konten-darlehen')} className="text-xs text-blue-600 hover:underline shrink-0">Hilfe dazu</button>
        </div>
        <p className="text-sm text-gray-500">
          Noch nicht vollständig konfiguriert. Fehlende Angaben: {data.fehlende_parameter.join(', ')}.
          {isAdmin && (istEndfaellig
            ? ' Trage Darlehensbetrag, Zinssatz und Laufzeit über das Stift-Symbol ein. Der Laufzeitbeginn ergibt sich sonst aus der ersten Buchung (erster Abruf).'
            : istKredit
              ? ' Trage Kreditbetrag, Zinssatz, Laufzeit und Tilgungsbeginn über das Stift-Symbol ein.'
              : ' Trage Darlehensbetrag, Zinssatz, Rate und Tilgungsbeginn über das Stift-Symbol ein.')}
        </p>
      </div>
    )
  }

  const e = data.eckdaten
  const jahre = data.jahre
  const szJahre = szenarioData?.jahre ?? []
  const zinsbindungJahr = e.zinsbindung_ende ? parseInt(e.zinsbindung_ende.slice(0, 4), 10) : null
  const alleJahre = Array.from(new Set([
    ...jahre.map((j) => j.jahr), ...szJahre.map((j) => j.jahr),
    ...(zinsbindungJahr != null ? [zinsbindungJahr] : []),
  ])).sort((a, b) => a - b)
  const baseByJahr = Object.fromEntries(jahre.map((j) => [j.jahr, j.restschuld]))
  const szByJahr = Object.fromEntries(szJahre.map((j) => [j.jahr, j.restschuld]))
  const chartData = {
    labels: alleJahre,
    datasets: [
      {
        label: 'Restschuld (Plan)',
        data: alleJahre.map((j) => baseByJahr[j] ?? null),
        borderColor: 'rgba(59,130,246,0.9)',
        backgroundColor: 'rgba(59,130,246,0.1)',
        fill: true, tension: 0.3, pointRadius: 2,
      },
      ...(szenarioData ? [{
        label: 'Restschuld (Szenario)',
        data: alleJahre.map((j) => szByJahr[j] ?? null),
        borderColor: 'rgba(22,163,74,0.9)',
        backgroundColor: 'rgba(22,163,74,0.1)',
        borderDash: [6, 4],
        fill: false, tension: 0.3, pointRadius: 2,
      }] : []),
    ],
  }
  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { display: szenarioData != null },
      zinsbindungLinie: { jahr: zinsbindungJahr },
    },
    scales: { y: { ticks: { callback: (v) => new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(v) } } },
  }

  const vergleich = szenarioData?.vergleich_unveraendert?.eckdaten ?? null
  const deltaMonate = vergleich ? szenarioData.eckdaten.laufzeit_monate - vergleich.laufzeit_monate : null
  const deltaZinsen = vergleich ? szenarioData.eckdaten.gesamt_zinsen - vergleich.gesamt_zinsen : null

  const berechneSzenario = async (ev) => {
    ev.preventDefault()
    setSzenarioFehler(null)
    setSzenarioLoading(true)
    try {
      const r = await kontenApi.hochrechnungSzenario(konto.id, Number(szenarioForm.tilgungssatz), Number(szenarioForm.zusatz || 0))
      setSzenarioData(r.data)
    } catch (err) {
      setSzenarioData(null)
      setSzenarioFehler(err.response?.data?.detail || 'Berechnung fehlgeschlagen.')
    } finally {
      setSzenarioLoading(false)
    }
  }

  const saveSonder = async (ev) => {
    ev.preventDefault()
    const body = { datum: sForm.datum, betrag: Number(sForm.betrag), notiz: sForm.notiz || null }
    if (sForm.id) await kontenApi.sonder.update(konto.id, sForm.id, body)
    else await kontenApi.sonder.create(konto.id, body)
    setSForm(null); load()
  }
  const delSonder = async (sid) => {
    if (!await confirm('Sondertilgung löschen?')) return
    await kontenApi.sonder.delete(konto.id, sid); load()
  }

  // Beim endfälligen Darlehen liegt der interessante Teil in der Zukunft (Zinslast bis zur
  // Ablösung), nicht am Laufzeitbeginn – die Kurzansicht startet deshalb beim laufenden Monat.
  const erstePrognose = istEndfaellig ? data.monate.findIndex((m) => !m.ist) : 0
  // -1 = Fälligkeit liegt bereits in der Vergangenheit: dann die letzten Monate zeigen.
  const abIndex = erstePrognose === -1 ? Math.max(0, data.monate.length - 12)
    : erstePrognose > 0 ? erstePrognose - 1 : 0
  const monateAnzeige = zeigeAlleMonate ? data.monate : data.monate.slice(abIndex, abIndex + 12)

  return (
    <div className="card p-4 mt-2 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold">{bezeichnung} – {konto.name}</h3>
          <button type="button" onClick={() => openHilfe('konten-darlehen')} className="text-xs text-blue-600 hover:underline">Hilfe dazu</button>
        </div>
        {!istEndfaellig && (
          <label className="text-sm flex items-center gap-2">
            <input type="checkbox" checked={mitSonder} onChange={(ev) => setMitSonder(ev.target.checked)} />
            Sondertilgungen einrechnen
          </label>
        )}
      </div>

      {istEndfaellig ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Abgerufen</div>
              <div className="font-semibold">{fmt(data.real_restschuld)}</div>
              <div className="text-xs text-gray-400">von {fmt(data.parameter.darlehen_betrag)}</div>
            </div>
            <div className="bg-blue-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Restlaufzeit</div>
              <div className="font-semibold text-blue-700">{fmtDauer(e.restlaufzeit_monate)}</div>
              <div className="text-xs text-gray-400">fällig am {e.faelligkeit}</div>
            </div>
            <div className="bg-amber-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Zins pro Monat</div>
              <div className="font-semibold text-amber-700">{fmt(e.monatszins_aktuell)}</div>
              <div className="text-xs text-gray-400">beim heutigen Stand</div>
            </div>
            <div className="bg-red-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Zinsen gesamt</div>
              <div className="font-semibold text-red-600">{fmt(e.gesamt_zinsen)}</div>
              <div className="text-xs text-gray-400">davon künftig {fmt(e.zinsen_kuenftig)}</div>
            </div>
          </div>

          <div className="text-xs text-gray-500 flex flex-wrap gap-4">
            <span>Kreditlinie: <strong>{fmt(data.parameter.darlehen_betrag)}</strong></span>
            <span>Noch frei: <strong>{fmt(e.freie_kreditlinie)}</strong></span>
            <span>Sollzins: <strong>{data.parameter.zinssatz?.toLocaleString('de-DE', { minimumFractionDigits: 3 })} %</strong></span>
            {konto.effektiver_zinssatz != null && (
              <span>Effektivzins: <strong>{konto.effektiver_zinssatz.toLocaleString('de-DE', { minimumFractionDigits: 3 })} %</strong></span>
            )}
            <span>Laufzeit: <strong>{konto.zinsbindung_jahre} Jahre</strong> ab {e.laufzeit_beginn}</span>
          </div>

          <div className="text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded px-3 py-2">
            Keine Tilgung und keine Rate – gezahlt werden nur Zinsen, die Ablösung erfolgt zur Fälligkeit
            in einer Summe. Rückführungen erfasst du als normale Buchung auf diesem Konto.
            Die Zinsen sind <strong>rechnerisch</strong>: bis heute aus dem tatsächlichen Saldoverlauf
            (Stand jeweils zu Monatsbeginn), danach mit dem heutigen Stand fortgeschrieben. Da die
            Zinszahlungen über das Girokonto laufen, können sie von der Bankabrechnung abweichen.
          </div>
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Reale Restschuld</div>
              <div className="font-semibold">{fmt(data.real_restschuld)}</div>
            </div>
            <div className="bg-blue-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Laufzeit</div>
              <div className="font-semibold text-blue-700">{fmtDauer(e.laufzeit_monate)}</div>
              <div className="text-xs text-gray-400">bis {e.letzte_rate}</div>
            </div>
            <div className="bg-red-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Zinsen gesamt</div>
              <div className="font-semibold text-red-600">{fmt(e.gesamt_zinsen)}</div>
            </div>
            <div className="bg-green-50 rounded p-3 text-center">
              <div className="text-xs text-gray-500 mb-1">Sondertilgung gesamt</div>
              <div className="font-semibold text-green-600">{fmt(e.gesamt_sondertilgung)}</div>
            </div>
          </div>

          <div className="text-xs text-gray-500 flex flex-wrap gap-4">
            <span>{istKredit ? 'Kreditbetrag' : 'Darlehensbetrag'}: <strong>{fmt(data.parameter.darlehen_betrag)}</strong></span>
            <span>Sollzins: <strong>{data.parameter.zinssatz?.toLocaleString('de-DE', { minimumFractionDigits: 3 })} %</strong></span>
            {konto.effektiver_zinssatz != null && (
              <span>Effektivzins: <strong>{konto.effektiver_zinssatz.toLocaleString('de-DE', { minimumFractionDigits: 3 })} %</strong></span>
            )}
            {istKredit
              ? konto.laufzeit_monate != null && (
                <span>Vereinbarte Laufzeit: <strong>{fmtDauer(konto.laufzeit_monate)}</strong></span>
              )
              : konto.tilgungssatz != null && (
                <span>Anfangstilgung: <strong>{konto.tilgungssatz.toLocaleString('de-DE', { minimumFractionDigits: 3 })} %</strong></span>
              )}
            <span>Monatsrate: <strong>{fmt(data.parameter.rate)}</strong></span>
          </div>
        </>
      )}

      {e.nie_getilgt && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          Achtung: Die Rate deckt nicht einmal die Zinsen – {istKredit ? 'der Kredit' : 'das Darlehen'} wird so nie getilgt.
        </div>
      )}

      {e.zinsbindung_ende && (
        istEndfaellig ? (
          <div className="text-sm bg-amber-50 border border-amber-200 rounded px-3 py-2 flex flex-wrap gap-x-6 gap-y-1">
            <span>Fällig am: <strong>{e.faelligkeit}</strong></span>
            <span>Ablösebetrag: <strong>{fmt(e.abloesebetrag)}</strong></span>
            <span className="text-gray-500">beim heutigen Abrufstand – weitere Abrufe erhöhen ihn</span>
          </div>
        ) : (
          <div className="text-sm bg-amber-50 border border-amber-200 rounded px-3 py-2 flex flex-wrap gap-x-6 gap-y-1">
            <span>Ende Zinsbindung: <strong>{e.zinsbindung_ende}</strong></span>
            <span>Restschuld dann (Plan): <strong>{fmt(e.restschuld_bei_zinsbindungsende)}</strong></span>
            {szenarioData?.eckdaten?.restschuld_bei_zinsbindungsende != null && (
              <span>Restschuld dann (Szenario): <strong>{fmt(szenarioData.eckdaten.restschuld_bei_zinsbindungsende)}</strong></span>
            )}
          </div>
        )
      )}

      <Line data={chartData} options={chartOptions} plugins={[zinsbindungLiniePlugin]} />

      {/* Was-wäre-wenn-Simulation – entfällt beim Ratenkredit (fester Tilgungssatz existiert dort
          nicht) und beim endfälligen Darlehen (dort gibt es überhaupt keine Tilgung) */}
      {!istKredit && !istEndfaellig && (
      <div className="border-t pt-4">
        <button
          type="button"
          className="flex items-center gap-2 font-medium text-gray-700"
          onClick={() => setSzenarioOffen((v) => !v)}
        >
          <span>{szenarioOffen ? '▾' : '▸'}</span> Was-wäre-wenn-Simulation
        </button>
        {szenarioOffen && (
          <div className="mt-3 space-y-3">
            <p className="text-xs text-gray-500">
              Rein rechnerische Vorschau ab heute (reale Restschuld als Startpunkt) – es wird nichts gespeichert.
              Die Ersparnis aus der Ratendifferenz fließt automatisch jedes Jahr im Dezember als Sondertilgung ein
              (im ersten Jahr anteilig nach vergangenen Monaten).
            </p>
            <form onSubmit={berechneSzenario} className="flex flex-wrap items-end gap-3">
              <div>
                <label className="label">Neuer Tilgungssatz (%)</label>
                <input
                  className="input w-32" type="number" step="0.01" min="0.01" required
                  value={szenarioForm.tilgungssatz}
                  onChange={(ev) => setSzenarioForm({ ...szenarioForm, tilgungssatz: ev.target.value })}
                />
              </div>
              <div>
                <label className="label">Zusätzliche jährliche Sondertilgung (€)</label>
                <CurrencyInput value={szenarioForm.zusatz} onChange={(n) => setSzenarioForm({ ...szenarioForm, zusatz: n ?? '' })} />
              </div>
              <button type="submit" className="btn-primary" disabled={szenarioLoading}>
                {szenarioLoading ? 'Berechne…' : 'Berechnen'}
              </button>
              {szenarioData && (
                <button type="button" className="btn-secondary" onClick={() => { setSzenarioData(null); setSzenarioFehler(null) }}>
                  Zurücksetzen
                </button>
              )}
            </form>

            {szenarioFehler && <p className="text-sm text-red-600">{szenarioFehler}</p>}

            {szenarioData && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-gray-50 rounded p-3 text-center">
                    <div className="text-xs text-gray-500 mb-1">Neue Rate</div>
                    <div className="font-semibold">{fmt(szenarioData.parameter.neue_rate)}</div>
                    <div className="text-xs text-gray-400">statt {fmt(szenarioData.parameter.alte_rate)}</div>
                  </div>
                  <div className="bg-green-50 rounded p-3 text-center">
                    <div className="text-xs text-gray-500 mb-1">Monatliche Ersparnis</div>
                    <div className="font-semibold text-green-700">{fmt(szenarioData.parameter.monatliche_ersparnis)}</div>
                    <div className="text-xs text-gray-400">jährlich im Dezember als Sondertilgung</div>
                  </div>
                  <div className="bg-blue-50 rounded p-3 text-center">
                    <div className="text-xs text-gray-500 mb-1">Restlaufzeit (ab heute)</div>
                    <div className="font-semibold text-blue-700">{fmtDauer(szenarioData.eckdaten.laufzeit_monate)}</div>
                    <div className="text-xs text-gray-400">bis {szenarioData.eckdaten.letzte_rate}</div>
                  </div>
                  <div className="bg-red-50 rounded p-3 text-center">
                    <div className="text-xs text-gray-500 mb-1">Zinsen (ab heute)</div>
                    <div className="font-semibold text-red-600">{fmt(szenarioData.eckdaten.gesamt_zinsen)}</div>
                  </div>
                </div>

                {vergleich && (
                  <div className="bg-gray-50 rounded p-3 text-sm">
                    <div className="text-xs text-gray-500 mb-2">Vergleich ggü. unverändertem Tilgungssatz (ab heute, gleiche Zusatz-Sondertilgung)</div>
                    <div className="flex flex-wrap gap-x-6 gap-y-1">
                      <span>
                        Restlaufzeit unverändert: <strong>{fmtDauer(vergleich.laufzeit_monate)}</strong>{' '}
                        (<span className={deltaMonate > 0 ? 'text-red-600' : deltaMonate < 0 ? 'text-green-600' : 'text-gray-500'}>
                          {deltaMonate > 0 ? `+${deltaMonate}` : deltaMonate} Monate
                        </span> im Szenario)
                      </span>
                      <span>
                        Zinsen unverändert: <strong>{fmt(vergleich.gesamt_zinsen)}</strong>{' '}
                        (<span className={deltaZinsen > 0 ? 'text-red-600' : deltaZinsen < 0 ? 'text-green-600' : 'text-gray-500'}>
                          {deltaZinsen > 0 ? `+${fmt(deltaZinsen)}` : fmt(deltaZinsen)}
                        </span> im Szenario)
                      </span>
                    </div>
                  </div>
                )}

                {szenarioData.eckdaten.nie_getilgt && (
                  <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                    Achtung: Die neue Rate deckt nicht einmal die Zinsen – das Darlehen wird so nie getilgt.
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
      )}

      {/* Sondertilgungen – beim endfälligen Darlehen laufen Rückführungen als normale Buchung,
          eine zusätzlich erfasste Sondertilgung würde denselben Betrag doppelt abziehen */}
      {!istEndfaellig && (
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-gray-700">Sondertilgungen</h4>
          {isAdmin && <button className="btn-secondary btn-sm" onClick={() => setSForm({ datum: '', betrag: '', notiz: '' })}>+ Sondertilgung</button>}
        </div>
        {sonder.length === 0
          ? <p className="text-gray-400 text-sm">Keine Sondertilgungen geplant.</p>
          : (
            <table className="min-w-full text-sm">
              <tbody className="divide-y divide-gray-100">
                {sonder.map((s) => (
                  <tr key={s.id} className="hover:bg-blue-50">
                    <td className="py-1.5 text-gray-500 w-28">{s.datum}</td>
                    <td className="py-1.5 font-mono text-right w-32">{fmt(s.betrag)}</td>
                    <td className="py-1.5 pl-3 text-gray-600">{s.notiz}</td>
                    {isAdmin && (
                      <td className="py-1.5 text-right whitespace-nowrap">
                        <button className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setSForm({ ...s })}><PencilIcon /></button>
                        <button className="btn-danger btn-icon ml-1" title="Löschen" aria-label="Löschen" onClick={() => delSonder(s.id)}>×</button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
      )}

      {/* Tilgungsplan bzw. Zinsplan (endfällig: ohne Tilgungs- und Sonderspalte) */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-gray-700">
            {istEndfaellig ? 'Zinsplan' : 'Tilgungsplan'} ({zeigeAlleMonate ? 'alle Monate' : istEndfaellig ? 'ab dem laufenden Monat' : 'erste 12 Monate'})
          </h4>
          <button className="text-blue-600 text-sm hover:underline" onClick={() => setZeigeAlleMonate((v) => !v)}>
            {zeigeAlleMonate ? 'Weniger' : `Alle ${data.monate.length} anzeigen`}
          </button>
        </div>
        <div className="overflow-x-auto max-h-96">
          <table className="min-w-full text-sm">
            <thead className="text-gray-500 text-xs uppercase border-b sticky top-0 bg-white">
              <tr>
                <th className="text-left py-1 pr-3">Datum</th>
                {istEndfaellig ? (
                  <>
                    <th className="text-right py-1 px-3">Schuldstand</th>
                    <th className="text-right py-1 px-3">Zins</th>
                    <th className="text-right py-1 pl-3">Zinsen kumuliert</th>
                  </>
                ) : (
                  <>
                    <th className="text-right py-1 px-3">Rate</th>
                    <th className="text-right py-1 px-3">Zins</th>
                    <th className="text-right py-1 px-3">Tilgung</th>
                    <th className="text-right py-1 px-3">Sonder</th>
                    <th className="text-right py-1 pl-3">Restschuld</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {monateAnzeige.map((m, i) => (
                <tr key={i} className="hover:bg-blue-50">
                  <td className="py-1 pr-3 text-gray-500">
                    {m.datum}
                    {istEndfaellig && !m.ist && <span className="ml-1 text-xs text-gray-400">(Prognose)</span>}
                  </td>
                  {istEndfaellig ? (
                    <>
                      <td className="py-1 px-3 text-right font-mono">{fmt(m.restschuld)}</td>
                      <td className="py-1 px-3 text-right font-mono text-red-500">{fmt(m.zins)}</td>
                      <td className="py-1 pl-3 text-right font-mono text-gray-500">{fmt(m.zins_kumuliert)}</td>
                    </>
                  ) : (
                    <>
                      <td className="py-1 px-3 text-right font-mono">{fmt(m.rate)}</td>
                      <td className="py-1 px-3 text-right font-mono text-red-500">{fmt(m.zins)}</td>
                      <td className="py-1 px-3 text-right font-mono">{fmt(m.tilgung)}</td>
                      <td className="py-1 px-3 text-right font-mono text-green-600">{m.sondertilgung ? fmt(m.sondertilgung) : '–'}</td>
                      <td className="py-1 pl-3 text-right font-mono">{fmt(m.restschuld)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {sForm && (
        <form onSubmit={saveSonder}>
          <Modal
            onClose={() => setSForm(null)}
            title={sForm.id ? 'Sondertilgung bearbeiten' : 'Neue Sondertilgung'}
            maxWidth="max-w-sm"
            footer={
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
                <button type="button" className="btn-secondary" onClick={() => setSForm(null)}>Abbrechen</button>
              </div>
            }
          >
            <div><label className="label">Datum*</label><input className="input" type="date" required value={sForm.datum} onChange={(ev) => setSForm({ ...sForm, datum: ev.target.value })} /></div>
            <div><label className="label">Betrag (€)*</label><CurrencyInput required value={sForm.betrag} onChange={(n) => setSForm({ ...sForm, betrag: n ?? '' })} /></div>
            <div><label className="label">Notiz</label><input className="input" value={sForm.notiz ?? ''} onChange={(ev) => setSForm({ ...sForm, notiz: ev.target.value })} /></div>
          </Modal>
        </form>
      )}
    </div>
  )
}

function fmtIban(iban) {
  if (!iban) return null
  const s = iban.replace(/\s/g, '')
  return s.match(/.{1,4}/g)?.join(' ') ?? s
}

export default function Konten() {
  const { confirm, dialog } = useConfirm()
  const { user } = useAuth()
  const [konten, setKonten] = useState([])
  const [saldi, setSaldi] = useState({})
  const [form, setForm] = useState(null)
  const [fehler, setFehler] = useState(null)
  const [selected, setSelected] = useState(null)
  const [zeigeInaktive, setZeigeInaktive] = useState(false)
  // Wert/Gewinn je Depotkonto, nach konto_id. Nur aktive Depots – ein inaktives
  // Konto fällt in der Tabelle auf den Buchungssaldo zurück, was dort passt.
  const [depots, setDepots] = useState({})

  const load = () => {
    kontenApi.depotUebersicht().then((r) =>
      setDepots(Object.fromEntries(r.data.map((d) => [d.konto_id, d])))
    )
    kontenApi.list(!zeigeInaktive).then((r) => {
      setKonten(r.data)
      // Ein gerade ausgeblendetes Konto darf keine Detailansicht offen lassen.
      setSelected((s) => (s && !r.data.some((k) => k.id === s.id) ? null : s))
      r.data.forEach((k) =>
        kontenApi.saldo(k.id).then((s) => setSaldi((p) => ({ ...p, [k.id]: s.data.saldo })))
      )
    })
  }
  useEffect(load, [zeigeInaktive])

  const toggleAktiv = async (k) => {
    try {
      const res = await kontenApi.update(k.id, { aktiv: !k.aktiv })
      if (zeigeInaktive) {
        setKonten((prev) => prev.map((x) => (x.id === res.data.id ? res.data : x)))
      } else {
        load()  // deaktiviertes Konto verschwindet aus der gefilterten Liste
      }
    } catch (err) {
      setFehler(err.response?.data?.detail ?? 'Ändern fehlgeschlagen')
    }
  }

  const save = async (e) => {
    e.preventDefault()
    setFehler(null)
    const payload = { ...form }
    if (payload.iban) payload.iban = payload.iban.replace(/\s/g, '').toUpperCase()
    if (payload.bic)  payload.bic  = payload.bic.trim().toUpperCase()
    try {
      if (form.id) {
        const res = await kontenApi.update(form.id, payload)
        setKonten((prev) => prev.map((k) => k.id === res.data.id ? res.data : k))
        // Anteile/Kurs können sich geändert haben – sonst stünde in der Tabelle
        // weiter der alte Depotwert.
        kontenApi.depotUebersicht().then((r) =>
          setDepots(Object.fromEntries(r.data.map((d) => [d.konto_id, d])))
        )
      } else {
        await kontenApi.create(payload)
        load()
      }
      setForm(null)
    } catch (err) {
      setFehler(err.response?.data?.detail ?? 'Speichern fehlgeschlagen')
    }
  }

  const del = async (id) => {
    try {
      const countRes = await kontenApi.buchungenCount(id)
      const count = countRes.data.count
      const msg = count > 0
        ? `Konto löschen? ${count} Buchung${count !== 1 ? 'en' : ''} werden ebenfalls gelöscht. `
          + 'Tipp: Konto stattdessen deaktivieren, dann bleibt die Historie erhalten.'
        : 'Konto löschen?'
      if (!await confirm(msg)) return
      await kontenApi.delete(id)
      load()
    } catch (err) {
      console.error('Fehler beim Löschen:', err)
    }
  }

  const isAdmin = user?.rolle === 'admin'

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Konten</h2>
        <div className="flex items-center gap-4">
          <label className="text-sm flex items-center gap-2">
            <input type="checkbox" checked={zeigeInaktive}
              onChange={(e) => setZeigeInaktive(e.target.checked)} />
            Inaktive anzeigen
          </label>
          {isAdmin && (
            <button
              className="btn-primary"
              onClick={() => setForm({ name: '', typ: 'giro', bank: '', iban: '', bic: '', startsaldo: 0, sortierung: 0 })}
            >
              + Neu
            </button>
          )}
        </div>
      </div>

      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Typ</th>
              <th className="px-3 py-2 font-medium">Bank</th>
              <th className="px-3 py-2 font-medium">IBAN / BIC</th>
              <th className="px-3 py-2 font-medium text-right">Saldo</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {konten.map((k) => (
              <tr key={k.id} className="border-b odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                <td className="px-3 py-2 font-medium">{k.name}</td>
                <td className="px-3 py-2"><span className="badge badge-gray">{k.typ}</span></td>
                <td className="px-3 py-2 text-gray-500">{k.bank ?? '–'}</td>
                <td className="px-3 py-2">
                  {k.iban
                    ? <span className="font-mono text-xs text-gray-700">{fmtIban(k.iban)}</span>
                    : <span className="text-gray-300">–</span>}
                  {k.bic && (
                    <span className="ml-2 text-xs text-gray-400 font-mono">{k.bic}</span>
                  )}
                </td>
                {/* Beim Depot zählt der Marktwert; investierte Summe und Gewinn/Verlust
                    stehen darunter. Ohne gepflegte Anteile/Kurs liefert das Backend in
                    `wert` den Buchungssaldo, dann sieht die Zelle aus wie bei jedem
                    anderen Konto. */}
                {k.typ === 'depot' && depots[k.id]?.marktwert != null ? (
                  <td className="px-3 py-2 text-right">
                    <div className="font-mono text-gray-900">{fmt(depots[k.id].wert)}</div>
                    <div className="text-xs text-gray-400 font-mono">
                      investiert {fmt(depots[k.id].investiert)}
                    </div>
                    <div className={`text-xs font-mono ${depots[k.id].gewinn >= 0 ? 'text-green-700' : 'text-red-600'}`}>
                      {depots[k.id].gewinn > 0 ? '+' : ''}{fmt(depots[k.id].gewinn)}
                      {depots[k.id].gewinn_prozent != null &&
                        ` (${depots[k.id].gewinn > 0 ? '+' : ''}${depots[k.id].gewinn_prozent.toLocaleString('de-DE', { minimumFractionDigits: 1 })} %)`}
                    </div>
                    {depots[k.id].kurs_datum && (
                      <div className="text-xs text-gray-400">Kurs vom {depots[k.id].kurs_datum}</div>
                    )}
                  </td>
                ) : (
                  <td className={`px-3 py-2 text-right font-mono ${(saldi[k.id] ?? 0) < 0 ? 'text-red-600' : 'text-gray-900'}`}>
                    {saldi[k.id] !== undefined ? fmt(saldi[k.id]) : '…'}
                  </td>
                )}
                <td className="px-3 py-2">
                  {k.aktiv
                    ? <span className="badge badge-green">aktiv</span>
                    : <span className="badge badge-gray">inaktiv</span>}
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-right">
                  {istTilgungsTyp(k.typ) && (
                    <button
                      className={`btn-sm h-9 mr-1 ${selected?.id === k.id ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setSelected(selected?.id === k.id ? null : k)}
                    >
                      {k.typ === 'kredit' ? 'Kredit' : 'Darlehen'}
                    </button>
                  )}
                  {isAdmin && (
                    <>
                      <button
                        className="btn-secondary btn-icon mr-1"
                        title={k.aktiv ? 'Deaktivieren' : 'Aktivieren'}
                        aria-label={k.aktiv ? 'Deaktivieren' : 'Aktivieren'}
                        onClick={() => toggleAktiv(k)}
                      >
                        {k.aktiv ? <EyeOffIcon /> : <EyeIcon />}
                      </button>
                      <button className="btn-secondary btn-icon mr-1" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setForm({ ...k })}><PencilIcon /></button>
                      <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => del(k.id)}>×</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && istTilgungsTyp(selected.typ) && (
        <DarlehenDetail konto={selected} isAdmin={isAdmin} confirm={confirm} />
      )}

      {form && (
        <form onSubmit={save}>
          <Modal
            onClose={() => setForm(null)}
            title={form.id ? 'Konto bearbeiten' : 'Neues Konto'}
            maxWidth="max-w-md"
            footer={
              <>
                {fehler && (
                  <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">{fehler}</div>
                )}
                <div className="flex gap-2">
                  <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
                  <button type="button" className="btn-secondary" onClick={() => setForm(null)}>Abbrechen</button>
                </div>
              </>
            }
          >
            <div>
              <label className="label">Name*</label>
              <input className="input" required autoFocus value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="label">Typ*</label>
              <select className="input" value={form.typ}
                onChange={(e) => setForm({ ...form, typ: e.target.value, ...typWechselReset(e.target.value) })}>
                {TYPEN.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Bankenname</label>
              <input className="input" placeholder="z.B. ING-DiBa AG"
                value={form.bank ?? ''}
                onChange={(e) => setForm({ ...form, bank: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">IBAN</label>
                <input className="input font-mono text-sm" placeholder="DE00 0000 0000 …"
                  value={form.iban ?? ''}
                  onChange={(e) => setForm({ ...form, iban: e.target.value })} />
              </div>
              <div>
                <label className="label">BIC</label>
                <input className="input font-mono text-sm" placeholder="INGDDEFFXXX"
                  value={form.bic ?? ''}
                  onChange={(e) => setForm({ ...form, bic: e.target.value })} />
              </div>
            </div>
            {/* Bei Darlehen und Kredit bleibt der Startsaldo 0 – die Restschuld kommt
                aus den Buchungen, sonst zählt sie doppelt (siehe Migration l2a3b4c5d6e7). */}
            {!istTilgungsTyp(form.typ) && (
              <div>
                <label className="label">Startsaldo (€)</label>
                <CurrencyInput value={form.startsaldo} onChange={(n) => setForm({ ...form, startsaldo: n ?? 0 })} />
              </div>
            )}
            {form.typ === 'darlehen' && (() => {
              // Beim Umschalten der Art werden Rate/Anfangstilgung/Tilgungsbeginn bewusst NICHT
              // geleert – sie werden nur ignoriert. Wer versehentlich umschaltet, verliert nichts.
              const endfaellig = form.darlehen_art === 'endfaellig'
              const berechneteRate = (form.darlehen_betrag && form.zinssatz != null && form.tilgungssatz != null)
                ? Math.round(form.darlehen_betrag * (parseFloat(form.zinssatz) + parseFloat(form.tilgungssatz)) / 100 / 12 * 100) / 100
                : null
              return (
                <div className="border-t pt-3 space-y-3">
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {endfaellig ? 'Endfälliges Darlehen' : 'Annuitäten-Darlehen'}
                  </div>
                  <div>
                    <label className="label">Art*</label>
                    <select className="input" value={form.darlehen_art ?? 'annuitaet'}
                      onChange={(e) => setForm({ ...form, darlehen_art: e.target.value })}>
                      <option value="annuitaet">Annuitätendarlehen (Rate aus Zins und Tilgung)</option>
                      <option value="endfaellig">Endfällig / Zwischenfinanzierung (nur Zinsen)</option>
                    </select>
                    {endfaellig && (
                      <div className="text-xs text-gray-400 mt-0.5">
                        Keine Tilgung und keine Rate – Ablösung in einer Summe zum Laufzeitende.
                        Rückführungen als normale Buchung erfassen.
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">{endfaellig ? 'Kreditlinie (€)*' : 'Darlehensbetrag (€)*'}</label>
                      <CurrencyInput value={form.darlehen_betrag ?? ''} onChange={(n) => setForm({ ...form, darlehen_betrag: n ?? null })} />
                    </div>
                    <div>
                      <label className="label">Sollzinssatz (% p.a.)*</label>
                      <input className="input" type="number" step="0.001" value={form.zinssatz ?? ''}
                        onChange={(e) => setForm({ ...form, zinssatz: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    <div>
                      <label className="label">Effektiver Zinssatz (% p.a.)</label>
                      <input className="input" type="number" step="0.001" placeholder="laut Bank"
                        value={form.effektiver_zinssatz ?? ''}
                        onChange={(e) => setForm({ ...form, effektiver_zinssatz: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    {!endfaellig && (
                    <div>
                      <label className="label">Anfangstilgung (% p.a.)*</label>
                      <input className="input" type="number" step="0.001" value={form.tilgungssatz ?? ''}
                        onChange={(e) => setForm({ ...form, tilgungssatz: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    )}
                    {!endfaellig && (
                    <div>
                      <label className="label">Monatsrate (€)</label>
                      <input className="input font-mono" type="number" step="0.01"
                        value={form.rate ?? berechneteRate ?? ''}
                        placeholder={berechneteRate ? `≈ ${berechneteRate.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €` : ''}
                        onChange={(e) => setForm({ ...form, rate: e.target.value ? parseFloat(e.target.value) : null })} />
                      {berechneteRate && !form.rate && (
                        <div className="text-xs text-blue-600 mt-0.5">
                          Berechnet: {berechneteRate.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
                          {' '}
                          <button type="button" className="underline" onClick={() => setForm({ ...form, rate: berechneteRate })}>
                            Übernehmen
                          </button>
                        </div>
                      )}
                    </div>
                    )}
                    {!endfaellig && (
                    <div>
                      <label className="label">Tilgungsbeginn*</label>
                      <input className="input" type="date" value={form.tilgung_start ?? ''}
                        onChange={(e) => setForm({ ...form, tilgung_start: e.target.value || null })} />
                    </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">{endfaellig ? 'Beginn der Laufzeit (optional)' : 'Tag der Vollauszahlung (optional)'}</label>
                      <input className="input" type="date" value={form.vollauszahlung_datum ?? ''}
                        onChange={(e) => setForm({ ...form, vollauszahlung_datum: e.target.value || null })} />
                      <div className="text-xs text-gray-400 mt-0.5">
                        {endfaellig
                          ? 'Sonst erste Buchung (erster Abruf)'
                          : 'Referenz für Zinsbindung, sonst erste Buchung'}
                      </div>
                    </div>
                    <div>
                      <label className="label">{endfaellig ? 'Laufzeit (Jahre)*' : 'Zinsbindung (Jahre, optional)'}</label>
                      <input className="input" type="number" step="1" min="1" value={form.zinsbindung_jahre ?? ''}
                        onChange={(e) => setForm({ ...form, zinsbindung_jahre: e.target.value ? parseInt(e.target.value, 10) : null })} />
                      {endfaellig && <div className="text-xs text-gray-400 mt-0.5">Bis zur Ablösung</div>}
                    </div>
                  </div>
                </div>
              )
            })()}
            {form.typ === 'kredit' && (() => {
              const berechneteRate = rateAusLaufzeit(form.darlehen_betrag, form.zinssatz, form.laufzeit_monate)
              return (
                <div className="border-t pt-3 space-y-3">
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">Ratenkredit</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Kreditbetrag (€)*</label>
                      <CurrencyInput value={form.darlehen_betrag ?? ''} onChange={(n) => setForm({ ...form, darlehen_betrag: n ?? null })} />
                    </div>
                    <div>
                      <label className="label">Sollzinssatz (% p.a.)*</label>
                      <input className="input" type="number" step="0.001" value={form.zinssatz ?? ''}
                        onChange={(e) => setForm({ ...form, zinssatz: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    <div>
                      <label className="label">Effektiver Zinssatz (% p.a.)</label>
                      <input className="input" type="number" step="0.001" placeholder="laut Bank"
                        value={form.effektiver_zinssatz ?? ''}
                        onChange={(e) => setForm({ ...form, effektiver_zinssatz: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    <div>
                      <label className="label">Laufzeit (Monate)*</label>
                      <input className="input" type="number" step="1" min="1" value={form.laufzeit_monate ?? ''}
                        onChange={(e) => setForm({ ...form, laufzeit_monate: e.target.value ? parseInt(e.target.value, 10) : null })} />
                      {form.laufzeit_monate > 0 && (
                        <div className="text-xs text-gray-400 mt-0.5">{fmtDauer(form.laufzeit_monate)}</div>
                      )}
                    </div>
                    <div>
                      <label className="label">Monatsrate (€)</label>
                      <input className="input font-mono" type="number" step="0.01"
                        value={form.rate ?? berechneteRate ?? ''}
                        placeholder={berechneteRate ? `≈ ${berechneteRate.toLocaleString('de-DE', { minimumFractionDigits: 2 })} €` : ''}
                        onChange={(e) => setForm({ ...form, rate: e.target.value ? parseFloat(e.target.value) : null })} />
                      {berechneteRate && !form.rate && (
                        <div className="text-xs text-blue-600 mt-0.5">
                          Berechnet: {berechneteRate.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
                          {' '}
                          <button type="button" className="underline" onClick={() => setForm({ ...form, rate: berechneteRate })}>
                            Übernehmen
                          </button>
                        </div>
                      )}
                    </div>
                    <div>
                      <label className="label">Tilgungsbeginn*</label>
                      <input className="input" type="date" value={form.tilgung_start ?? ''}
                        onChange={(e) => setForm({ ...form, tilgung_start: e.target.value || null })} />
                    </div>
                  </div>
                </div>
              )
            })()}
            {form.typ === 'depot' && (() => {
              // Genau ein Wertpapier je Depot. Alles manuell gepflegt – die App ruft
              // bewusst keine Kurse ab. Die ISIN ist reine Dokumentation.
              const wert = (form.anteile && form.kurs)
                ? Math.round(parseFloat(form.anteile) * parseFloat(form.kurs) * 100) / 100
                : null
              // Nulllinie: ab diesem Kurs deckt der Bestand die eingezahlte Summe.
              // Die investierte Summe kommt aus der Depot-Übersicht – bei einem noch
              // ungespeicherten Konto gibt es sie nicht.
              const investiert = depots[form.id]?.investiert
              const breakeven = (form.anteile > 0 && investiert > 0)
                ? Math.round(investiert / parseFloat(form.anteile) * 10000) / 10000
                : null
              return (
                <div className="border-t pt-3 space-y-3">
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">Wertpapier</div>
                  <div>
                    <label className="label">ISIN</label>
                    <input className="input font-mono text-sm" placeholder="z.B. IE00B4L5Y983"
                      value={form.isin ?? ''}
                      onChange={(e) => setForm({ ...form, isin: e.target.value || null })} />
                    <div className="text-xs text-gray-400 mt-0.5">
                      Nur zur Dokumentation – der Kurs wird nicht automatisch abgerufen.
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Anteile</label>
                      <input className="input font-mono" type="number" step="0.0001" min="0"
                        value={form.anteile ?? ''}
                        onChange={(e) => setForm({ ...form, anteile: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    <div>
                      <label className="label">Kurs (€)</label>
                      <input className="input font-mono" type="number" step="0.0001" min="0"
                        value={form.kurs ?? ''}
                        onChange={(e) => setForm({ ...form, kurs: e.target.value ? parseFloat(e.target.value) : null })} />
                    </div>
                    <div>
                      <label className="label">Kurs vom</label>
                      <input className="input" type="date" value={form.kurs_datum ?? ''}
                        onChange={(e) => setForm({ ...form, kurs_datum: e.target.value || null })} />
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 space-y-0.5">
                    <div>
                      {wert != null
                        ? <>Depotwert: <strong>{fmt(wert)}</strong> – Gewinn/Verlust zeigt das Dashboard gegen die eingezahlte Summe.</>
                        : 'Ohne Anteile und Kurs zählt das Depot mit der eingezahlten Summe (Buchungssaldo).'}
                    </div>
                    {breakeven != null && (
                      <div>
                        Gewinnschwelle: ab Kurs{' '}
                        <strong>{breakeven.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} €</strong>
                        {' '}deckt der Bestand die eingezahlten {fmt(investiert)}.
                      </div>
                    )}
                  </div>
                </div>
              )
            })()}
            {form.id && (
              <div className="flex items-center gap-2">
                <input type="checkbox" id="aktiv" checked={form.aktiv}
                  onChange={(e) => setForm({ ...form, aktiv: e.target.checked })} />
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
