import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Chart as ChartJS,
  ArcElement, BarElement, CategoryScale, LinearScale, Legend, Tooltip,
} from 'chart.js'
import { Bar, Pie } from 'react-chartjs-2'
import { belegeApi, gebaeudeApi, kategorienApi } from '../api'
import { useAuth } from '../AuthContext'
import KategorieSelect from '../components/KategorieSelect'
import Modal from '../components/Modal'
import { useConfirm } from '../components/useConfirm'
import { CameraIcon, DrehenIcon, PencilIcon } from '../components/icons'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Legend, Tooltip)

const ARTEN = ['strom', 'wasser', 'abwasser', 'gas', 'waerme', 'sonstige']
const EINHEITEN = ['kWh', 'MWh', 'm³', 'Einheiten']

// Je Zähler eine eigene Farbe, damit Tabelle und Diagramm zusammenpassen
const FARBEN = ['#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed', '#0891b2',
                '#db2777', '#65a30d', '#ea580c', '#4f46e5', '#0d9488', '#b91c1c', '#6b7280']

function zahl(n, stellen = 0) {
  if (n == null) return '–'
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: stellen }).format(n)
}

function euro(n) {
  if (n == null) return '–'
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

// Einspeisung und Bezug zu Kostenarten zusammenziehen.
//
// Ein Einspeisezähler mit gegenzaehler_id (PV) ist keine eigene Kostenart: seine
// Vergütung mindert die Kosten des Bezugszählers. Das Backend liefert die Kosten
// schon mit Vorzeichen - Ausgabe positiv, Ertrag negativ -, hier werden sie je
// Jahr nur addiert. Der Verbrauch bleibt davon unberührt: bezogene und
// eingespeiste kWh sind verschiedene Mengen zu verschiedenen Preisen.
//
// Ergebnis je Art: name, jeJahr (Euro) und teile (die beteiligten Reihen, aber
// nur wenn wirklich verrechnet wurde - daraus baut der Tooltip die Zerlegung).
function kostenarten(reihen) {
  const absorbiert = new Set()
  const zufluss = new Map()
  for (const r of reihen) {
    if (!r.gegenzaehler_id) continue
    const ziel = reihen.find((z) => z.zaehler_id === r.gegenzaehler_id)
    if (!ziel) continue   // Gegenzähler nicht in dieser Auswahl: Art bleibt eigenständig
    absorbiert.add(r.zaehler_id)
    if (!zufluss.has(ziel.zaehler_id)) zufluss.set(ziel.zaehler_id, [])
    zufluss.get(ziel.zaehler_id).push(r)
  }
  return reihen.filter((r) => !absorbiert.has(r.zaehler_id)).map((r) => {
    const teile = [r, ...(zufluss.get(r.zaehler_id) || [])]
    const jeJahr = {}
    for (const t of teile) {
      for (const j of t.jahre) {
        if (j.kosten == null) continue
        jeJahr[j.jahr] = Math.round(((jeJahr[j.jahr] || 0) + j.kosten) * 100) / 100
      }
    }
    return { zaehler_id: r.zaehler_id, name: r.name, jeJahr, teile: teile.length > 1 ? teile : null }
  })
}

// Zerlegung für den Tooltip: "Bezug 2.951,38 € − Einspeisung 577,26 €"
function zerlegung(art, jahr) {
  if (!art.teile) return null
  const werte = art.teile.map((t) => {
    const k = t.jahre.find((x) => x.jahr === Number(jahr))?.kosten
    return k == null ? null : `${t.richtung === 'einspeisung' ? 'Einspeisung' : 'Bezug'} ${euro(Math.abs(k))}`
  }).filter(Boolean)
  return werte.length > 1 ? werte.join(' − ') : null
}

export default function Gebaeude() {
  const { user } = useAuth()
  const istAdmin = user?.rolle === 'admin'
  const { confirm, dialog } = useConfirm()

  const [gebaeude, setGebaeude] = useState([])
  const [gewaehltId, setGewaehltId] = useState(null)
  const [reiter, setReiter] = useState('uebersicht')
  const [uebersicht, setUebersicht] = useState(null)
  const [zaehler, setZaehler] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [laedt, setLaedt] = useState(false)
  const [zeigeInaktive, setZeigeInaktive] = useState(false)
  // Aufgeklappter Zähler: hier oben, damit er ein Neuladen nach dem Speichern
  // einer Ablesung übersteht - der Bereich darunter wird dabei neu aufgebaut.
  const [offenerZaehler, setOffenerZaehler] = useState(null)
  const [neuesGebaeude, setNeuesGebaeude] = useState(false)
  const [offeneAblesungen, setOffeneAblesungen] = useState([])

  // Liste der Gebäude: auch nach Anlegen, Umbenennen oder Deaktivieren nötig.
  const gebaeudeLaden = useCallback((waehle) => (
    gebaeudeApi.list(!zeigeInaktive).then((r) => {
      setGebaeude(r.data)
      setGewaehltId((id) => {
        const ziel = waehle ?? id
        return r.data.some((g) => g.id === ziel) ? ziel : (r.data[0]?.id ?? null)
      })
      return r.data
    })
  ), [zeigeInaktive])

  useEffect(() => { gebaeudeLaden() }, [gebaeudeLaden])

  useEffect(() => {
    kategorienApi.flat().then((r) => setKategorien(r.data))
  }, [])

  const laden = useCallback(() => {
    // Die offenen Ablesungen gehen über alle Gebäude und ändern sich mit jeder
    // gespeicherten Ablesung, deshalb hängen sie am selben Neuladen.
    gebaeudeApi.offeneAblesungen().then((r) => setOffeneAblesungen(r.data))
    if (!gewaehltId) return
    setLaedt(true)
    Promise.all([gebaeudeApi.uebersicht(gewaehltId), gebaeudeApi.zaehler(gewaehltId)])
      .then(([u, z]) => { setUebersicht(u.data); setZaehler(z.data) })
      .finally(() => setLaedt(false))
  }, [gewaehltId])

  useEffect(() => { laden() }, [laden])

  const gewaehlt = gebaeude.find((g) => g.id === gewaehltId)

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-7xl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold">Gebäude</h2>
          <select
            className="input w-auto"
            value={gewaehltId ?? ''}
            onChange={(e) => setGewaehltId(e.target.value ? Number(e.target.value) : null)}
          >
            {gebaeude.length === 0 && <option value="">– noch keines –</option>}
            {gebaeude.map((g) => (
              <option key={g.id} value={g.id}>{g.name}{g.aktiv ? '' : ' (deaktiviert)'}</option>
            ))}
          </select>
          {istAdmin && (
            <button
              className="btn-secondary btn-sm"
              onClick={() => { setNeuesGebaeude(true); setReiter('stammdaten') }}
            >+ Gebäude</button>
          )}
        </div>
        {gewaehlt && (
          <span className="text-sm text-gray-500">
            {[gewaehlt.strasse, [gewaehlt.plz, gewaehlt.ort].filter(Boolean).join(' ')].filter(Boolean).join(', ')}
          </span>
        )}
      </div>

      <OffeneAblesungen
        eintraege={offeneAblesungen}
        onSpringen={(e) => {
          setGewaehltId(e.gebaeude_id)
          setOffenerZaehler(e.zaehler_id)
          setReiter('zaehler')
        }}
      />

      <div className="flex gap-1 border-b border-gray-200">
        {[['uebersicht', 'Übersicht'], ['zaehler', 'Zähler'], ['nebenkosten', 'Nebenkosten'],
          ['stammdaten', 'Stammdaten']].map(([wert, text]) => (
          <button
            key={wert}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${
              reiter === wert ? 'border-blue-600 text-blue-700 font-medium' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setReiter(wert)}
          >
            {text}
          </button>
        ))}
      </div>

      {laedt && <div className="text-gray-400 text-sm">Lädt…</div>}
      {!laedt && !gewaehltId && !neuesGebaeude && reiter !== 'stammdaten' && (
        <div className="card text-sm text-gray-500">
          Noch kein Gebäude angelegt. Der Import der Verbrauchszahlen legt eines an,
          oder du legst eines unter „Stammdaten“ an.
        </div>
      )}

      {!laedt && gewaehltId && reiter === 'uebersicht' && uebersicht && (
        <Uebersicht daten={uebersicht} />
      )}
      {!laedt && gewaehltId && reiter === 'zaehler' && (
        <ZaehlerBereich
          gebaeudeId={gewaehltId}
          zaehler={zaehler}
          kategorien={kategorien}
          istAdmin={istAdmin}
          confirm={confirm}
          offen={offenerZaehler}
          setOffen={setOffenerZaehler}
          onAenderung={laden}
        />
      )}
      {!laedt && gewaehltId && reiter === 'nebenkosten' && uebersicht && (
        <Nebenkosten
          gebaeudeId={gewaehltId}
          daten={uebersicht}
          zaehler={zaehler}
          kategorien={kategorien}
          istAdmin={istAdmin}
          onAenderung={laden}
        />
      )}
      {reiter === 'stammdaten' && (
        <Stammdaten
          gebaeude={gewaehlt}
          neu={neuesGebaeude}
          istAdmin={istAdmin}
          confirm={confirm}
          zeigeInaktive={zeigeInaktive}
          setZeigeInaktive={setZeigeInaktive}
          onNeuAbbrechen={() => setNeuesGebaeude(false)}
          onGespeichert={(id) => { setNeuesGebaeude(false); gebaeudeLaden(id) }}
          onGeloescht={() => { setNeuesGebaeude(false); setReiter('uebersicht'); gebaeudeLaden() }}
        />
      )}
      {dialog}
    </div>
  )
}

// ── Offene Jahresablesungen ─────────────────────────────────────────────────
// Steht über den Reitern und gilt für alle aktiven Gebäude, nicht nur für das
// gewählte - sonst fiele eine Lücke im anderen Haus nie auf.

function OffeneAblesungen({ eintraege, onSpringen }) {
  const [eingeklappt, setEingeklappt] = useState(false)
  if (eintraege.length === 0) return null

  const jahre = eintraege.reduce((s, e) => s + e.jahre.length, 0)
  const mehrereGebaeude = new Set(eintraege.map((e) => e.gebaeude_id)).size > 1

  return (
    <div className="card border-amber-200 bg-amber-50 space-y-2">
      <button
        className="flex items-center gap-2 text-sm font-medium text-amber-800 w-full text-left"
        onClick={() => setEingeklappt((e) => !e)}
      >
        <span className="text-gray-500">{eingeklappt ? '▸' : '▾'}</span>
        {jahre === 1 ? 'Eine Jahresablesung fehlt' : `${jahre} Jahresablesungen fehlen`}
        <span className="font-normal text-amber-700">
          bei {eintraege.length === 1 ? 'einem Zähler' : `${eintraege.length} Zählern`}
        </span>
      </button>

      {!eingeklappt && (
        <ul className="space-y-1 text-sm">
          {eintraege.map((e) => (
            <li key={e.zaehler_id} className="flex flex-wrap items-baseline gap-x-2">
              <button
                className="text-amber-800 font-medium underline underline-offset-2"
                onClick={() => onSpringen(e)}
              >
                {mehrereGebaeude && <span className="text-gray-500">{e.gebaeude} · </span>}
                {e.zaehler}
              </button>
              <span className="text-gray-600">{e.jahre.join(', ')}</span>
            </li>
          ))}
        </ul>
      )}

      {!eingeklappt && (
        <p className="text-xs text-gray-600">
          Wird ein Zähler nicht mehr abgelesen, trag im Reiter „Zähler“ sein Enddatum ein
          oder setz ihn auf „nicht aktiv“ – dann verschwindet er aus dieser Liste.
        </p>
      )}
    </div>
  )
}

// ── Übersicht: Jahrestabelle + Diagramm ─────────────────────────────────────

const FARBE_SONSTIGE = '#94a3b8'

function Uebersicht({ daten }) {
  const [zeigeKosten, setZeigeKosten] = useState(false)
  const [sichtbar, setSichtbar] = useState(() => new Set(daten.reihen.map((r) => r.zaehler_id)))
  const [zeigeSonstige, setZeigeSonstige] = useState(true)

  const umschalten = (id) => setSichtbar((s) => {
    const n = new Set(s)
    n.has(id) ? n.delete(id) : n.add(id)
    return n
  })

  const wert = (reihe, jahr) => {
    const j = reihe.jahre.find((x) => x.jahr === jahr)
    if (!j) return null
    return zeigeKosten ? j.kosten : j.verbrauch
  }

  const gezeigt = daten.reihen.filter((r) => sichtbar.has(r.zaehler_id))

  // In der Kosten-Ansicht zeigt das Diagramm Kostenarten, nicht Zaehler: die
  // PV-Einspeisung steckt dann im Bezugszaehler. In der Verbrauchs-Ansicht
  // bleibt jeder Zaehler fuer sich, weil kWh nicht verrechnet werden.
  const arten = useMemo(() => kostenarten(daten.reihen), [daten.reihen])
  const absorbiert = useMemo(
    () => new Set(daten.reihen.map((r) => r.zaehler_id)
      .filter((id) => !arten.some((a) => a.zaehler_id === id))),
    [daten.reihen, arten],
  )
  const farbeFuer = (zaehlerId) =>
    FARBEN[daten.reihen.findIndex((r) => r.zaehler_id === zaehlerId) % FARBEN.length]
  // Zeilen, die im Diagramm nicht mehr einzeln vorkommen, brauchen auch kein
  // Haekchen - sonst schaltet man etwas um, das nichts bewirkt.
  const legende = zeigeKosten
    ? daten.reihen.filter((r) => !absorbiert.has(r.zaehler_id))
    : daten.reihen

  // Übrige Nebenkosten (Grundsteuer, Versicherung, Müll …) je Jahr aufsummiert.
  // Sie haben keinen Verbrauch, kommen also nur in der Kosten-Ansicht vor.
  const sonstigeJeJahr = daten.jahre.map((j) =>
    (daten.sonstige_kosten[j] || []).reduce((s, p) => s + p.betrag, 0))
  const hatSonstige = sonstigeJeJahr.some((b) => b > 0)
  const sonstigeImDiagramm = zeigeKosten && zeigeSonstige && hatSonstige

  // Einheiten nie mischen: wo mehrere vorkommen, bekommt jede ihre eigene Achse
  const einheiten = [...new Set(gezeigt.map((r) => r.einheit))]
  const chartDaten = {
    labels: daten.jahre,
    datasets: [
      ...(zeigeKosten
        ? arten.filter((a) => sichtbar.has(a.zaehler_id)).map((a) => ({
            label: `${a.name} (€)`,
            data: daten.jahre.map((j) => a.jeJahr[j] ?? null),
            backgroundColor: farbeFuer(a.zaehler_id),
            yAxisID: 'y',
            art: a,
          }))
        : gezeigt.map((r) => ({
            label: `${r.name} (${r.einheit})`,
            data: daten.jahre.map((j) => wert(r, j)),
            backgroundColor: farbeFuer(r.zaehler_id),
            yAxisID: einheiten.length === 1 ? 'y' : `y${einheiten.indexOf(r.einheit)}`,
          }))),
      ...(sonstigeImDiagramm ? [{
        label: 'Übrige Nebenkosten (€)',
        data: sonstigeJeJahr.map((b) => b || null),
        backgroundColor: FARBE_SONSTIGE,
        yAxisID: 'y',
      }] : []),
    ],
  }
  const scales = { x: { stacked: false } }
  if (zeigeKosten || einheiten.length === 1) {
    scales.y = { beginAtZero: true, title: { display: true, text: zeigeKosten ? '€' : einheiten[0] } }
  } else {
    einheiten.forEach((e, i) => {
      scales[`y${i}`] = {
        beginAtZero: true, position: i === 0 ? 'left' : 'right',
        grid: { drawOnChartArea: i === 0 },
        title: { display: true, text: e },
      }
    })
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-2">
            <button className={zeigeKosten ? 'btn-secondary' : 'btn-primary'} onClick={() => setZeigeKosten(false)}>Verbrauch</button>
            <button className={zeigeKosten ? 'btn-primary' : 'btn-secondary'} onClick={() => setZeigeKosten(true)}>Kosten</button>
          </div>
          <div className="flex gap-2 text-xs">
            <button className="text-blue-700 hover:underline" onClick={() => setSichtbar(new Set(daten.reihen.map((r) => r.zaehler_id)))}>alle</button>
            <button className="text-blue-700 hover:underline" onClick={() => setSichtbar(new Set())}>keine</button>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {legende.map((r) => (
            <label key={r.zaehler_id} className="flex items-center gap-1.5 text-sm cursor-pointer">
              <input type="checkbox" className="haken" checked={sichtbar.has(r.zaehler_id)} onChange={() => umschalten(r.zaehler_id)} />
              <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: farbeFuer(r.zaehler_id) }} />
              {r.name}
            </label>
          ))}
          {zeigeKosten && hatSonstige && (
            <label className="flex items-center gap-1.5 text-sm cursor-pointer">
              <input type="checkbox" className="haken" checked={zeigeSonstige} onChange={() => setZeigeSonstige((s) => !s)} />
              <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: FARBE_SONSTIGE }} />
              Übrige Nebenkosten
            </label>
          )}
        </div>
        {(gezeigt.length > 0 || sonstigeImDiagramm) && (
          <div className="h-72">
            <Bar
              data={chartDaten}
              options={{ responsive: true, maintainAspectRatio: false, scales,
                         plugins: {
                           legend: { position: 'bottom' },
                           tooltip: { callbacks: {
                             label: (k) => (zeigeKosten
                               ? `${k.dataset.label}: ${euro(k.parsed.y)}`
                               : `${k.dataset.label}: ${zahl(k.parsed.y, 2)}`),
                             afterLabel: (k) => (k.dataset.art
                               ? zerlegung(k.dataset.art, daten.jahre[k.dataIndex])
                               : null),
                           } },
                         } }}
            />
          </div>
        )}
      </div>

      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b bg-gray-50 text-xs uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Zähler</th>
              {daten.jahre.map((j) => <th key={j} className="px-3 py-2 font-medium text-right">{j}</th>)}
            </tr>
          </thead>
          <tbody>
            {daten.reihen.map((r) => (
              <tr key={r.zaehler_id} className="border-b odd:bg-white even:bg-gray-50">
                <td className="px-3 py-2 whitespace-nowrap">
                  {r.name}
                  <span className="text-gray-400 text-xs"> ({zeigeKosten ? '€' : r.einheit})</span>
                  {r.richtung === 'einspeisung' && <span className="badge badge-green ml-1">Einspeisung</span>}
                  {/* Die Tabelle zeigt Brutto je Zaehler, das Kosten-Diagramm das
                      verrechnete Netto - das Badge sagt, wo der Unterschied herkommt. */}
                  {r.verrechnet_mit?.length > 0 && (
                    <span className="text-gray-400 text-xs ml-1"
                          title="Im Kosten-Diagramm sind diese Betraege miteinander verrechnet">
                      verrechnet mit {r.verrechnet_mit.join(', ')}
                    </span>
                  )}
                </td>
                {daten.jahre.map((j) => {
                  const eintrag = r.jahre.find((x) => x.jahr === j)
                  const v = wert(r, j)
                  return (
                    <td key={j} className="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                      {zeigeKosten ? (v == null ? '–' : euro(v)) : zahl(v, 2)}
                      {eintrag?.zaehlerwechsel && (
                        <span className="ml-1 text-amber-600" title="Zählerwechsel in diesem Jahr">⇄</span>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
            {zeigeKosten && hatSonstige && (
              <tr className="border-b bg-gray-50">
                <td className="px-3 py-2 whitespace-nowrap">
                  Übrige Nebenkosten
                  <span className="text-gray-400 text-xs"> (€)</span>
                </td>
                {daten.jahre.map((j, i) => (
                  <td key={j} className="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                    {sonstigeJeJahr[i] ? euro(sonstigeJeJahr[i]) : '–'}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Zähler: Stammdaten, Ablesungen, Wechsel ─────────────────────────────────

function ZaehlerBereich({ gebaeudeId, zaehler, kategorien, istAdmin, confirm, offen, setOffen, onAenderung }) {
  const [form, setForm] = useState(null)         // Zähler bearbeiten/anlegen
  const [wechsel, setWechsel] = useState(null)   // Zählerwechsel-Dialog
  const [vorschlaege, setVorschlaege] = useState([])

  useEffect(() => {
    gebaeudeApi.vorschlaege(gebaeudeId).then((r) => setVorschlaege(r.data))
  }, [gebaeudeId, zaehler])

  const katPfad = (id) => kategorien.find((k) => k.id === id)?.pfad ?? '–'

  const uebernehmen = async (v) => {
    await gebaeudeApi.zaehlerUpdate(v.zaehler_id, { kategorie_id: v.kategorie_id })
    onAenderung()
  }

  return (
    <div className="space-y-3">
      {vorschlaege.length > 0 && (
        <div className="card bg-amber-50 border-amber-200 space-y-2">
          <div className="text-sm font-medium">
            Vorschläge für die Kostenzuordnung (anhand der Zählernummer)
          </div>
          {vorschlaege.map((v) => (
            <div key={v.zaehler_id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{v.zaehler}</span>
              <span className="text-gray-500">→ {v.kategorie}</span>
              <button className="btn-secondary btn-sm" onClick={() => uebernehmen(v)}>übernehmen</button>
            </div>
          ))}
        </div>
      )}

      {istAdmin && (
        <button className="btn-primary" onClick={() => setForm({ gebaeude_id: gebaeudeId, art: 'sonstige', einheit: 'kWh', richtung: 'bezug' })}>
          + Zähler
        </button>
      )}

      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b bg-gray-50 text-xs uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Zähler</th>
              <th className="px-3 py-2 font-medium">Nummer</th>
              <th className="px-3 py-2 font-medium">Art</th>
              <th className="px-3 py-2 font-medium">Einheit</th>
              <th className="px-3 py-2 font-medium">Kategorie</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {zaehler.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-gray-400">Keine Zähler</td></tr>
            )}
            {zaehler.map((z) => (
              <Fragment key={z.id}>
                <tr
                  className="border-b cursor-pointer hover:bg-gray-50"
                  onClick={() => setOffen(offen === z.id ? null : z.id)}
                >
                  <td className="px-3 py-2 whitespace-nowrap font-medium">
                    <span className="text-gray-400 mr-1">{offen === z.id ? '▾' : '▸'}</span>
                    {z.name}
                  </td>
                  <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{z.seriennummer || '–'}</td>
                  <td className="px-3 py-2 text-gray-500">{z.art}</td>
                  <td className="px-3 py-2 text-gray-500">{z.einheit}</td>
                  <td className="px-3 py-2">
                    {z.kategorie_id
                      ? <span className="text-gray-600">{katPfad(z.kategorie_id)}</span>
                      : <span className="badge bg-amber-100 text-amber-800">ohne Kategorie</span>}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {z.richtung === 'einspeisung' && <span className="badge badge-green mr-1">Einspeisung</span>}
                    {z.gueltig_bis && <span className="badge badge-gray">ersetzt am {z.gueltig_bis}</span>}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    {istAdmin && (
                      <div className="flex justify-end gap-1">
                        {!z.gueltig_bis && (
                          <button className="btn-secondary btn-sm" title="Zählerwechsel" onClick={() => setWechsel(z)}>⇄ Wechsel</button>
                        )}
                        <button className="btn-secondary btn-icon" title="Bearbeiten" onClick={() => setForm(z)}><PencilIcon /></button>
                        <button
                          className="btn-danger btn-icon" title="Löschen"
                          onClick={async () => {
                            if (!await confirm(`Zähler "${z.name}" mit allen Ablesungen löschen?`)) return
                            await gebaeudeApi.zaehlerDelete(z.id)
                            onAenderung()
                          }}
                        >×</button>
                      </div>
                    )}
                  </td>
                </tr>
                {offen === z.id && (
                  <tr className="border-b">
                    <td colSpan={7} className="p-0">
                      <Ablesungen zaehler={z} istAdmin={istAdmin} onAenderung={onAenderung} confirm={confirm} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {form && (
        <ZaehlerForm
          zaehler={form}
          kategorien={kategorien}
          alleZaehler={zaehler}
          onClose={() => setForm(null)}
          onGespeichert={() => { setForm(null); onAenderung() }}
        />
      )}
      {wechsel && (
        <WechselDialog
          zaehler={wechsel}
          onClose={() => setWechsel(null)}
          onFertig={() => { setWechsel(null); onAenderung() }}
        />
      )}
    </div>
  )
}

function Ablesungen({ zaehler, istAdmin, onAenderung, confirm }) {
  const [liste, setListe] = useState([])
  const [neu, setNeu] = useState({ datum: new Date().toISOString().slice(0, 10), stand: '', art: 'jahr' })
  const [hinweis, setHinweis] = useState(null)
  const [bearbeitet, setBearbeitet] = useState(null)  // Ablesung, die gerade in der Zeile editiert wird
  // Zählerstand-Foto: ein Durchlauf ist immer Datei wählen -> zuschneiden ->
  // hochladen. `ziel` ist die Ablesung, an die es soll; null heißt "die, die
  // mit Eintragen gleich entsteht", und dann wartet die Datei in `neuesFoto`.
  const [rohdatei, setRohdatei] = useState(null)
  const [fotoStand, setFotoStand] = useState(0)   // Cache-Brecher fuer die Vorschau
  const [ziel, setZiel] = useState(null)
  const [neuesFoto, setNeuesFoto] = useState(null)
  const [fotoFehler, setFotoFehler] = useState(null)
  const dateiRef = useRef(null)

  const laden = useCallback(() => {
    gebaeudeApi.ablesungen(zaehler.id).then((r) => setListe(r.data))
  }, [zaehler.id])
  useEffect(() => { laden() }, [laden])

  // Plausibilität prüfen, sobald ein Stand eingegeben ist – Hinweis, keine Sperre
  useEffect(() => {
    if (neu.stand === '' || neu.art !== 'jahr') { setHinweis(null); return }
    const jahr = Number(neu.datum.slice(0, 4))
    gebaeudeApi.pruefung(zaehler.id, jahr, Number(neu.stand))
      .then((r) => setHinweis(r.data.hinweis))
      .catch(() => setHinweis(null))
  }, [neu.stand, neu.datum, neu.art, zaehler.id])

  // Datei wählen: derselbe versteckte Eingabeknopf für alle Knöpfe, `ziel`
  // merkt sich, wohin das Ergebnis gehört.
  const dateiWaehlen = (ablesungId) => {
    setFotoFehler(null)
    setZiel(ablesungId ?? null)
    dateiRef.current.value = ''
    dateiRef.current.click()
  }

  const fotoHochladen = async (ablesungId, datei) => {
    try {
      await belegeApi.uploadAblesung(ablesungId, datei)
      setFotoStand(Date.now())
      laden()
    } catch (err) {
      setFotoFehler(err.response?.data?.detail ?? 'Das Foto konnte nicht gespeichert werden.')
    }
  }

  const zuschnittFertig = (datei) => {
    setRohdatei(null)
    if (ziel == null) setNeuesFoto(datei)
    else fotoHochladen(ziel, datei)
  }

  const fotoLoeschen = async (a) => {
    if (!await confirm('Foto dieser Ablesung löschen?')) return
    await belegeApi.deleteAblesung(a.id, a.foto_id)
    laden()
  }

  // Erst die Ablesung, dann ihr Foto: das Foto braucht die ID, die der Server
  // beim Anlegen vergibt. Scheitert der Upload, steht die Ablesung trotzdem -
  // das Foto lässt sich an der Zeile nachtragen.
  const speichern = async () => {
    const r = await gebaeudeApi.ablesungCreate({
      zaehler_id: zaehler.id, datum: neu.datum, stand: Number(neu.stand), art: neu.art,
    })
    if (neuesFoto) {
      await fotoHochladen(r.data.id, neuesFoto)
      setNeuesFoto(null)
    }
    setNeu({ ...neu, stand: '' })
    laden()
    onAenderung()
  }

  // Beim Speichern einer Zeile wird das Jahr bewusst neu aus dem Datum gesetzt:
  // wer das Datum korrigiert, meint in der Regel auch das Jahr.
  const zeileSpeichern = async () => {
    await gebaeudeApi.ablesungUpdate(bearbeitet.id, {
      datum: bearbeitet.datum,
      jahr: Number(bearbeitet.datum.slice(0, 4)),
      stand: Number(bearbeitet.stand),
      art: bearbeitet.art,
      notiz: bearbeitet.notiz || null,
    })
    setBearbeitet(null)
    laden()
    onAenderung()
  }

  return (
    <div className="bg-gray-50 px-3 py-3 space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="label">Datum</label>
          <input type="date" className="input w-auto" value={neu.datum}
                 onChange={(e) => setNeu({ ...neu, datum: e.target.value })} />
        </div>
        <div>
          <label className="label">Stand ({zaehler.einheit})</label>
          <input type="number" step="any" className="input w-32" value={neu.stand}
                 onChange={(e) => setNeu({ ...neu, stand: e.target.value })} />
        </div>
        <div>
          <label className="label">Art</label>
          <select className="input w-auto" value={neu.art} onChange={(e) => setNeu({ ...neu, art: e.target.value })}>
            <option value="jahr">Jahresablesung</option>
            <option value="zwischen">Zwischenablesung</option>
          </select>
        </div>
        {neuesFoto ? (
          <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded px-2 py-1">
            <FotoVorschau datei={neuesFoto} className="w-12 h-8 object-cover rounded" />
            <span className="text-xs text-blue-800 font-medium">Foto bereit</span>
            <button className="text-xs text-blue-700 underline" onClick={() => dateiWaehlen(null)}>ändern</button>
            <button className="text-blue-700 px-1" title="Foto verwerfen" onClick={() => setNeuesFoto(null)}>×</button>
          </div>
        ) : (
          <button className="btn-secondary" onClick={() => dateiWaehlen(null)}>
            <CameraIcon className="w-4 h-4" /> Foto
          </button>
        )}
        <button className="btn-primary" disabled={neu.stand === ''} onClick={speichern}>Eintragen</button>
      </div>
      {/* Ein einziger Datei-Eingang für alle Foto-Knöpfe dieses Zählers.
          capture="environment" öffnet am Handy direkt die Rückkamera. */}
      <input
        ref={dateiRef} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={(e) => { const d = e.target.files?.[0]; if (d) setRohdatei(d) }}
      />
      {fotoFehler && <div className="text-xs text-red-600">{fotoFehler}</div>}
      {rohdatei && (
        <FotoZuschnitt
          datei={rohdatei}
          onFertig={zuschnittFertig}
          onAbbrechen={() => setRohdatei(null)}
        />
      )}
      {hinweis && <div className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1">{hinweis}</div>}
      {neu.art === 'zwischen' && (
        <div className="text-xs text-gray-500">
          Zwischenablesungen sind reine Information und gehen nicht in Jahresverbrauch, Diagramm oder Kosten ein.
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 text-xs uppercase">
            <th className="py-1 font-medium">Datum</th>
            <th className="py-1 font-medium">Jahr</th>
            <th className="py-1 font-medium text-right">Stand</th>
            <th className="py-1 font-medium">Art</th>
            <th className="py-1 font-medium">Foto</th>
            <th className="py-1 font-medium">Notiz</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {liste.map((a) => (bearbeitet?.id === a.id ? (
            <tr key={a.id} className="border-t border-gray-200 bg-blue-50">
              <td className="py-1 pr-2">
                <input type="date" className="input w-auto" value={bearbeitet.datum}
                       onChange={(e) => setBearbeitet({ ...bearbeitet, datum: e.target.value })} />
              </td>
              <td className="py-1 text-gray-500">{bearbeitet.datum.slice(0, 4)}</td>
              <td className="py-1 pr-2">
                <input type="number" step="any" className="input w-28 text-right" value={bearbeitet.stand}
                       onChange={(e) => setBearbeitet({ ...bearbeitet, stand: e.target.value })} />
              </td>
              <td className="py-1 pr-2">
                <select className="input w-auto" value={bearbeitet.art}
                        onChange={(e) => setBearbeitet({ ...bearbeitet, art: e.target.value })}>
                  <option value="jahr">Jahr</option>
                  <option value="zwischen">Zwischen</option>
                </select>
              </td>
              <td className="py-1 pr-2 text-gray-400 text-xs">–</td>
              <td className="py-1 pr-2">
                <input className="input" value={bearbeitet.notiz ?? ''}
                       onChange={(e) => setBearbeitet({ ...bearbeitet, notiz: e.target.value })} />
              </td>
              <td className="py-1 text-right whitespace-nowrap">
                <button className="btn-primary btn-sm mr-1" disabled={bearbeitet.stand === ''} onClick={zeileSpeichern}>Speichern</button>
                <button className="btn-secondary btn-sm" onClick={() => setBearbeitet(null)}>Abbrechen</button>
              </td>
            </tr>
          ) : (
            <tr key={a.id} className="border-t border-gray-200">
              <td className="py-1">{a.datum}</td>
              <td className="py-1">{a.jahr}</td>
              <td className="py-1 text-right tabular-nums">{zahl(a.stand, 3)}</td>
              <td className="py-1">
                {a.art === 'jahr' ? <span className="badge badge-blue">Jahr</span> : <span className="badge badge-gray">Zwischen</span>}
              </td>
              <td className="py-1 pr-2">
                {a.foto_id ? (
                  <div className="flex items-center gap-1">
                    <a href={belegeApi.dateUrlAblesung(a.id, a.foto_id, fotoStand)} target="_blank" rel="noreferrer"
                       title="Foto in voller Größe öffnen">
                      <img
                        src={belegeApi.dateUrlAblesung(a.id, a.foto_id, fotoStand)}
                        alt={`Zählwerk am ${a.datum}`}
                        className="w-14 h-9 object-cover rounded border border-gray-200"
                      />
                    </a>
                    {istAdmin && (
                      <button className="text-gray-400 hover:text-red-600 px-1" title="Foto löschen"
                              onClick={() => fotoLoeschen(a)}>×</button>
                    )}
                  </div>
                ) : (
                  <button
                    className="w-14 h-9 rounded border border-dashed border-gray-300 text-gray-400
                               hover:text-gray-600 hover:border-gray-400 flex items-center justify-center"
                    title="Foto nachtragen"
                    aria-label={`Foto zur Ablesung vom ${a.datum} nachtragen`}
                    onClick={() => dateiWaehlen(a.id)}
                  ><CameraIcon className="w-4 h-4" /></button>
                )}
              </td>
              <td className="py-1 text-gray-500 text-xs">{a.notiz}</td>
              <td className="py-1 text-right whitespace-nowrap">
                {istAdmin && (
                  <>
                    {a.foto_id && (
                      <button
                        className="btn-secondary btn-icon-sm mr-1" title="Foto ersetzen"
                        aria-label={`Foto der Ablesung vom ${a.datum} ersetzen`}
                        onClick={() => dateiWaehlen(a.id)}
                      ><CameraIcon className="w-4 h-4" /></button>
                    )}
                    <button
                      className="btn-secondary btn-icon-sm mr-1" title="Bearbeiten"
                      onClick={() => setBearbeitet({ ...a, stand: String(a.stand) })}
                    ><PencilIcon /></button>
                    <button
                      className="btn-danger btn-icon-sm" title="Löschen"
                      onClick={async () => {
                        if (!await confirm('Ablesung löschen?')) return
                        await gebaeudeApi.ablesungDelete(a.id)
                        laden()
                        onAenderung()
                      }}
                    >×</button>
                  </>
                )}
              </td>
            </tr>
          )))}
          {liste.length === 0 && <tr><td colSpan={7} className="py-2 text-gray-400">Noch keine Ablesungen</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

// Vorschau einer Datei, die noch nicht hochgeladen ist (Blob-URL statt Endpunkt).
function FotoVorschau({ datei, className }) {
  const url = useMemo(() => URL.createObjectURL(datei), [datei])
  useEffect(() => () => URL.revokeObjectURL(url), [url])
  return <img src={url} alt="Gewähltes Zählwerk-Foto" className={className} />
}

// ── Foto zuschneiden und drehen, bevor es hochgeladen wird ──────────────────
// Bewusst im Browser: so geht nur der Ausschnitt über die Leitung, und am Handy
// ist das der Moment, in dem man das Bild noch vor Augen hat. Der 90°-Knopf ist
// kein Komfort - OpenCV verwirft serverseitig die EXIF-Drehung, ein quer
// aufgenommenes Zählwerk käme sonst quer in der Ablage an.
const ANZEIGE_MAX = { breite: 560, hoehe: 320 }
const STANDARD_AUSSCHNITT = { x: 0.08, y: 0.3, b: 0.84, h: 0.4 }

function FotoZuschnitt({ datei, onFertig, onAbbrechen }) {
  const [bild, setBild] = useState(null)
  const [drehung, setDrehung] = useState(0)
  const [aus, setAus] = useState(STANDARD_AUSSCHNITT)   // Anteile des gedrehten Bildes, 0..1
  const [zieht, setZieht] = useState(null)
  const [fehler, setFehler] = useState(null)
  const flaecheRef = useRef(null)
  const leinwandRef = useRef(null)

  useEffect(() => {
    const url = URL.createObjectURL(datei)
    const img = new Image()
    // React raeumt den Effekt im Entwicklungsmodus sofort wieder ab und laeuft
    // ein zweites Mal. Ohne diese Sperre meldet das erste, mit der URL
    // weggeraeumte Bild einen Fehler, obwohl das zweite laengst geladen ist.
    let verworfen = false
    img.onload = () => {
      if (verworfen) return
      setBild(img)
      setFehler(null)
    }
    img.onerror = () => {
      if (!verworfen) setFehler('Das Bild konnte nicht gelesen werden.')
    }
    img.src = url
    return () => {
      verworfen = true
      URL.revokeObjectURL(url)
    }
  }, [datei])

  // Maße nach der Drehung: bei 90° und 270° tauschen Breite und Höhe.
  const gedreht = useMemo(() => {
    if (!bild) return null
    const quer = drehung % 180 !== 0
    return {
      b: quer ? bild.naturalHeight : bild.naturalWidth,
      h: quer ? bild.naturalWidth : bild.naturalHeight,
    }
  }, [bild, drehung])

  const anzeige = useMemo(() => {
    if (!gedreht) return null
    const skala = Math.min(ANZEIGE_MAX.breite / gedreht.b, ANZEIGE_MAX.hoehe / gedreht.h, 1)
    return { b: Math.round(gedreht.b * skala), h: Math.round(gedreht.h * skala) }
  }, [gedreht])

  // Gezeichnet statt per CSS gedreht: nur so stimmen Zeigerkoordinaten und
  // Ausschnitt ohne Umrechnung über die Drehmatrix überein.
  useEffect(() => {
    const c = leinwandRef.current
    if (!c || !bild || !anzeige) return
    c.width = anzeige.b
    c.height = anzeige.h
    const ctx = c.getContext('2d')
    ctx.clearRect(0, 0, c.width, c.height)
    ctx.save()
    ctx.translate(c.width / 2, c.height / 2)
    ctx.rotate((drehung * Math.PI) / 180)
    const quer = drehung % 180 !== 0
    const zb = quer ? c.height : c.width
    const zh = quer ? c.width : c.height
    ctx.drawImage(bild, -zb / 2, -zh / 2, zb, zh)
    ctx.restore()
  }, [bild, drehung, anzeige])

  const anteil = (e) => {
    const r = flaecheRef.current.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    }
  }

  const ziehBeginn = (e) => {
    e.preventDefault()
    const p = anteil(e)
    setZieht(p)
    setAus({ x: p.x, y: p.y, b: 0, h: 0 })
  }

  const ziehLauf = (e) => {
    if (!zieht) return
    const p = anteil(e)
    setAus({
      x: Math.min(zieht.x, p.x), y: Math.min(zieht.y, p.y),
      b: Math.abs(p.x - zieht.x), h: Math.abs(p.y - zieht.y),
    })
  }

  // Ein Klick ohne Zug ist kein Ausschnitt - dann zurück auf den Vorschlag,
  // statt ein leeres Rechteck stehen zu lassen.
  const ziehEnde = () => {
    setZieht(null)
    setAus((a) => (a.b < 0.04 || a.h < 0.04 ? STANDARD_AUSSCHNITT : a))
  }

  const uebernehmen = (ganz = false) => {
    if (!bild || !gedreht) return
    const bereich = ganz ? { x: 0, y: 0, b: 1, h: 1 } : aus
    const quelle = document.createElement('canvas')
    quelle.width = gedreht.b
    quelle.height = gedreht.h
    const qctx = quelle.getContext('2d')
    qctx.translate(quelle.width / 2, quelle.height / 2)
    qctx.rotate((drehung * Math.PI) / 180)
    qctx.drawImage(bild, -bild.naturalWidth / 2, -bild.naturalHeight / 2)

    const sx = Math.round(bereich.x * gedreht.b)
    const sy = Math.round(bereich.y * gedreht.h)
    const sb = Math.max(1, Math.round(bereich.b * gedreht.b))
    const sh = Math.max(1, Math.round(bereich.h * gedreht.h))
    const ziel = document.createElement('canvas')
    ziel.width = sb
    ziel.height = sh
    ziel.getContext('2d').drawImage(quelle, sx, sy, sb, sh, 0, 0, sb, sh)
    ziel.toBlob((blob) => {
      if (!blob) { setFehler('Der Ausschnitt konnte nicht erzeugt werden.'); return }
      onFertig(new File([blob], 'zaehlerstand.jpg', { type: 'image/jpeg' }))
    }, 'image/jpeg', 0.9)
  }

  return (
    <Modal
      onClose={onAbbrechen}
      title="Foto zuschneiden"
      maxWidth="max-w-2xl"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button className="btn-secondary" onClick={() => setDrehung((d) => (d + 90) % 360)}>
            <DrehenIcon className="w-4 h-4" /> 90° drehen
          </button>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={() => uebernehmen(true)}>Ganzes Foto</button>
            <button className="btn-primary" disabled={!bild} onClick={() => uebernehmen(false)}>Übernehmen</button>
          </div>
        </div>
      }
    >
      {fehler && <div className="text-sm text-red-600">{fehler}</div>}
      <div className="bg-gray-900 rounded flex items-center justify-center p-3" style={{ minHeight: 200 }}>
        {anzeige ? (
          <div
            ref={flaecheRef}
            className="relative select-none"
            style={{ width: anzeige.b, height: anzeige.h, touchAction: 'none', cursor: 'crosshair' }}
            onPointerDown={ziehBeginn}
            onPointerMove={ziehLauf}
            onPointerUp={ziehEnde}
            onPointerLeave={ziehEnde}
          >
            <canvas ref={leinwandRef} className="block rounded" />
            <div
              className="absolute border-2 border-white pointer-events-none"
              style={{
                left: `${aus.x * 100}%`, top: `${aus.y * 100}%`,
                width: `${aus.b * 100}%`, height: `${aus.h * 100}%`,
                boxShadow: '0 0 0 9999px rgba(17,24,39,.55)',
              }}
            />
          </div>
        ) : (
          <span className="text-gray-400 text-sm">Lädt…</span>
        )}
      </div>
      <div className="text-xs text-gray-500">
        Rechteck um das Zählwerk ziehen. Es geht nur der Ausschnitt zum Server; liegt das
        Zählwerk quer, vorher drehen.
      </div>
    </Modal>
  )
}

function ZaehlerForm({ zaehler, kategorien, alleZaehler, onClose, onGespeichert }) {
  const [f, setF] = useState(zaehler)
  const [fehler, setFehler] = useState(null)
  const neu = !zaehler.id

  // Verrechnet wird nur mit einem Bezugszaehler derselben Art im selben Gebaeude -
  // dieselbe Bedingung prueft das Backend in _pruefe_zaehler.
  const moeglicheGegenzaehler = alleZaehler.filter(
    (z) => z.id !== f.id && z.richtung === 'bezug' && z.art === f.art,
  )

  const speichern = async () => {
    setFehler(null)
    try {
      if (neu) await gebaeudeApi.zaehlerCreate(f)
      else await gebaeudeApi.zaehlerUpdate(zaehler.id, f)
      onGespeichert()
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Speichern fehlgeschlagen')
    }
  }

  return (
    <Modal onClose={onClose} title={neu ? 'Neuer Zähler' : `Zähler: ${zaehler.name}`}>
      <div className="space-y-3">
        <div>
          <label className="label">Name</label>
          <input className="input" value={f.name ?? ''} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </div>
        <div>
          <label className="label">Seriennummer</label>
          <input className="input" value={f.seriennummer ?? ''} onChange={(e) => setF({ ...f, seriennummer: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Art</label>
            <select className="input" value={f.art} onChange={(e) => setF({ ...f, art: e.target.value })}>
              {ARTEN.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Einheit</label>
            <select className="input" value={f.einheit} onChange={(e) => setF({ ...f, einheit: e.target.value })}>
              {EINHEITEN.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="label">Richtung</label>
          <select className="input" value={f.richtung} onChange={(e) => setF({ ...f, richtung: e.target.value })}>
            <option value="bezug">Bezug (Verbrauch)</option>
            <option value="einspeisung">Einspeisung (z. B. PV)</option>
          </select>
        </div>
        {f.richtung === 'einspeisung' && (
          <div>
            <label className="label">Kosten verrechnen mit</label>
            <select
              className="input"
              value={f.gegenzaehler_id ?? ''}
              onChange={(e) => setF({ ...f, gegenzaehler_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">– separat als Ertrag ausweisen –</option>
              {moeglicheGegenzaehler.map((z) => (
                <option key={z.id} value={z.id}>{z.name}</option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">
              Die Vergütung mindert dann die Kosten dieses Bezugszählers, statt als
              eigene Kostenart zu erscheinen. Nur die Euro-Beträge werden verrechnet –
              bezogene und eingespeiste kWh bleiben getrennt.
            </p>
          </div>
        )}
        <div>
          <label className="label">Kategorie für die Kosten</label>
          <KategorieSelect
            kategorien={kategorien}
            value={f.kategorie_id}
            onChange={(id) => setF({ ...f, kategorie_id: id })}
          />
          <p className="text-xs text-gray-400 mt-1">
            Die Jahreskosten sind die Summe der gebuchten Buchungen dieser Kategorie.
          </p>
        </div>
        <div>
          <label className="label">Zwischenzähler von</label>
          <select
            className="input"
            value={f.uebergeordneter_zaehler_id ?? ''}
            onChange={(e) => setF({ ...f, uebergeordneter_zaehler_id: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">– eigenständig –</option>
            {alleZaehler.filter((z) => z.id !== f.id).map((z) => (
              <option key={z.id} value={z.id}>{z.name}</option>
            ))}
          </select>
        </div>
        {fehler && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
            {fehler}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-secondary" onClick={onClose}>Abbrechen</button>
          <button className="btn-primary" disabled={!f.name} onClick={speichern}>Speichern</button>
        </div>
      </div>
    </Modal>
  )
}

function WechselDialog({ zaehler, onClose, onFertig }) {
  const [f, setF] = useState({
    datum: new Date().toISOString().slice(0, 10),
    endstand_alt: '', anfangsstand_neu: '0', seriennummer_neu: '',
  })

  const speichern = async () => {
    await gebaeudeApi.zaehlerWechsel(zaehler.id, {
      datum: f.datum,
      endstand_alt: Number(f.endstand_alt),
      anfangsstand_neu: Number(f.anfangsstand_neu || 0),
      ...(f.seriennummer_neu ? { seriennummer_neu: f.seriennummer_neu } : {}),
    })
    onFertig()
  }

  return (
    <Modal onClose={onClose} title={`Zählerwechsel: ${zaehler.name}`}>
      <div className="space-y-3">
        <p className="text-xs text-gray-500">
          Der alte Zähler wird mit seinem Endstand abgeschlossen, der neue beginnt beim
          Anfangsstand. Der Jahresverbrauch des Wechseljahrs setzt sich aus beiden zusammen.
        </p>
        <div>
          <label className="label">Datum des Wechsels</label>
          <input type="date" className="input" value={f.datum} onChange={(e) => setF({ ...f, datum: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Endstand alt ({zaehler.einheit})</label>
            <input type="number" step="any" className="input" value={f.endstand_alt}
                   onChange={(e) => setF({ ...f, endstand_alt: e.target.value })} />
          </div>
          <div>
            <label className="label">Anfangsstand neu</label>
            <input type="number" step="any" className="input" value={f.anfangsstand_neu}
                   onChange={(e) => setF({ ...f, anfangsstand_neu: e.target.value })} />
          </div>
        </div>
        <div>
          <label className="label">Seriennummer des neuen Zählers</label>
          <input className="input" value={f.seriennummer_neu} onChange={(e) => setF({ ...f, seriennummer_neu: e.target.value })} />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button className="btn-secondary" onClick={onClose}>Abbrechen</button>
          <button className="btn-primary" disabled={f.endstand_alt === ''} onClick={speichern}>Wechsel eintragen</button>
        </div>
      </div>
    </Modal>
  )
}

// ── Nebenkosten ─────────────────────────────────────────────────────────────

function Nebenkosten({ gebaeudeId, daten, zaehler, kategorien, istAdmin, onAenderung }) {
  const [zuordnungen, setZuordnungen] = useState([])
  const [neueKategorie, setNeueKategorie] = useState(null)

  const laden = useCallback(() => {
    gebaeudeApi.kostenkategorien(gebaeudeId).then((r) => setZuordnungen(r.data))
  }, [gebaeudeId])
  useEffect(() => { laden() }, [laden])

  const katName = (id) => kategorien.find((k) => k.id === id)?.pfad ?? '–'

  const verbrauchskosten = useMemo(() => daten.reihen
    .filter((r) => r.kategorie_id)
    .map((r) => ({
      name: r.name,
      einheit: r.einheit,
      proJahr: Object.fromEntries(r.jahre.map((j) => [j.jahr, j])),
    })), [daten.reihen])

  // daten.jahre enthaelt jedes Jahr mit einer Ablesung. Kosten gibt es oft
  // erst ab einem spaeteren Jahr - die frueheren waeren hier nur leere
  // Spalten, also zeigt die Tabelle sie nur auf Wunsch.
  const [alleJahre, setAlleJahre] = useState(false)
  const jahreMitWerten = useMemo(() => daten.jahre.filter((j) =>
    verbrauchskosten.some((z) => z.proJahr[j]?.kosten)
    || (daten.sonstige_kosten[j] || []).some((p) => p.betrag)
  ), [daten.jahre, daten.sonstige_kosten, verbrauchskosten])
  const leere = daten.jahre.length - jahreMitWerten.length
  const jahre = useMemo(
    () => [...(alleJahre ? daten.jahre : jahreMitWerten)].reverse(),
    [alleJahre, daten.jahre, jahreMitWerten],
  )

  return (
    <div className="space-y-4">
      <NebenkostenDiagramme daten={daten} />

      {leere > 0 && (
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" role="switch" className="schieber schieber-sm" checked={alleJahre} onChange={(e) => setAlleJahre(e.target.checked)} />
          {leere} {leere === 1 ? 'Jahr' : 'Jahre'} ohne Kosten mit anzeigen
        </label>
      )}

      <div className="card p-0">
        <div className="px-3 py-2 border-b font-semibold text-gray-700">
          Verbrauchsbezogene Nebenkosten
        </div>
        {verbrauchskosten.length === 0 ? (
          <div className="px-3 py-4 text-sm text-gray-500">
            Noch kein Zähler mit Kategorie. Im Reiter „Zähler“ je Zähler eine Kategorie
            hinterlegen – die Kosten kommen dann automatisch aus den Buchungen.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50 text-xs uppercase tracking-wide">
                  <th className="px-3 py-2 font-medium">Zähler</th>
                  {jahre.map((j) => <th key={j} className="px-3 py-2 font-medium text-right">{j}</th>)}
                </tr>
              </thead>
              <tbody>
                {verbrauchskosten.map((z) => (
                  <tr key={z.name} className="border-b odd:bg-white even:bg-gray-50">
                    <td className="px-3 py-2 whitespace-nowrap">{z.name}</td>
                    {jahre.map((j) => {
                      const e = z.proJahr[j]
                      return (
                        <td key={j} className="px-3 py-2 text-right tabular-nums whitespace-nowrap">
                          {euro(e?.kosten)}
                          {e?.preis_je_einheit != null && (
                            <div className="text-xs text-gray-400">
                              {zahl(e.preis_je_einheit, 4)} €/{z.einheit}
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card p-0">
        <div className="px-3 py-2 border-b font-semibold text-gray-700 flex items-center justify-between gap-2">
          <span>Übrige Nebenkosten</span>
          {istAdmin && (
            <div className="flex items-center gap-2">
              <div className="w-64">
                <KategorieSelect kategorien={kategorien} value={neueKategorie} onChange={setNeueKategorie} />
              </div>
              <button
                className="btn-secondary btn-sm"
                disabled={!neueKategorie}
                onClick={async () => {
                  await gebaeudeApi.kostenkategorieAdd(gebaeudeId, neueKategorie)
                  setNeueKategorie(null)
                  laden()
                  onAenderung()
                }}
              >hinzufügen</button>
            </div>
          )}
        </div>
        {zuordnungen.length === 0 ? (
          <div className="px-3 py-4 text-sm text-gray-500">
            Kategorien ohne Verbrauchsbezug (Grundsteuer, Versicherung, Müll …) hier zuordnen –
            sie werden jahresweise zusammengefasst.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b bg-gray-50 text-xs uppercase tracking-wide">
                  <th className="px-3 py-2 font-medium">Kategorie</th>
                  {jahre.map((j) => <th key={j} className="px-3 py-2 font-medium text-right">{j}</th>)}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {zuordnungen.map((z) => (
                  <tr key={z.id} className="border-b odd:bg-white even:bg-gray-50">
                    <td className="px-3 py-2">{katName(z.kategorie_id)}</td>
                    {jahre.map((j) => {
                      const posten = (daten.sonstige_kosten[j] || []).find((p) => p.kategorie_id === z.kategorie_id)
                      return <td key={j} className="px-3 py-2 text-right tabular-nums">{euro(posten?.betrag)}</td>
                    })}
                    <td className="px-3 py-2 text-right">
                      {istAdmin && (
                        <button
                          className="btn-danger btn-icon-sm"
                          onClick={async () => {
                            await gebaeudeApi.kostenkategorieDelete(z.id)
                            laden()
                            onAenderung()
                          }}
                        >×</button>
                      )}
                    </td>
                  </tr>
                ))}
                <tr className="font-semibold bg-gray-50">
                  <td className="px-3 py-2">Summe</td>
                  {jahre.map((j) => {
                    const summe = (daten.sonstige_kosten[j] || [])
                      .filter((p) => zuordnungen.some((z) => z.kategorie_id === p.kategorie_id))
                      .reduce((s, p) => s + p.betrag, 0)
                    return <td key={j} className="px-3 py-2 text-right tabular-nums">{summe ? euro(summe) : '–'}</td>
                  })}
                  <td></td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Stammdaten: Gebäude anlegen, ändern, deaktivieren, löschen, Fotos ───────

const LEERES_GEBAEUDE = { name: '', strasse: '', plz: '', ort: '', notiz: '', aktiv: true }

function Stammdaten({ gebaeude, neu, istAdmin, confirm, zeigeInaktive, setZeigeInaktive,
                      onNeuAbbrechen, onGespeichert, onGeloescht }) {
  const [form, setForm] = useState(LEERES_GEBAEUDE)
  const [fehler, setFehler] = useState(null)
  const [speichert, setSpeichert] = useState(false)
  const [loeschDialog, setLoeschDialog] = useState(false)

  // Beim Wechsel des Gebäudes oder beim Umschalten auf "neu" das Formular neu
  // befüllen - sonst stehen die Daten des vorigen Gebäudes darin.
  useEffect(() => {
    if (neu) setForm(LEERES_GEBAEUDE)
    else if (gebaeude) setForm({
      name: gebaeude.name ?? '', strasse: gebaeude.strasse ?? '', plz: gebaeude.plz ?? '',
      ort: gebaeude.ort ?? '', notiz: gebaeude.notiz ?? '', aktiv: gebaeude.aktiv,
    })
    setFehler(null)
  }, [neu, gebaeude])

  const feld = (name) => ({
    value: form[name],
    onChange: (e) => setForm((f) => ({ ...f, [name]: e.target.value })),
  })

  const speichern = async () => {
    if (!form.name.trim()) { setFehler('Ein Name ist nötig.'); return }
    setSpeichert(true)
    setFehler(null)
    try {
      const antwort = neu
        ? await gebaeudeApi.create(form)
        : await gebaeudeApi.update(gebaeude.id, form)
      onGespeichert(antwort.data.id)
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Speichern fehlgeschlagen.')
    } finally {
      setSpeichert(false)
    }
  }

  if (!istAdmin) {
    return <div className="card text-sm text-gray-500">Stammdaten darf nur ein Administrator ändern.</div>
  }

  if (!neu && !gebaeude) {
    return (
      <div className="space-y-4">
        <InaktiveSchalter zeigeInaktive={zeigeInaktive} setZeigeInaktive={setZeigeInaktive} />
        <div className="card text-sm text-gray-500">Kein Gebäude gewählt.</div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <InaktiveSchalter zeigeInaktive={zeigeInaktive} setZeigeInaktive={setZeigeInaktive} />

      <div className="card space-y-3">
        <div className="font-semibold text-gray-700">
          {neu ? 'Neues Gebäude' : 'Gebäude bearbeiten'}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className="text-sm text-gray-600">Name</span>
            <input className="input" placeholder="z. B. Musterweg 1" {...feld('name')} />
          </label>
          <label className="block sm:col-span-2">
            <span className="text-sm text-gray-600">Straße</span>
            <input className="input" {...feld('strasse')} />
          </label>
          <label className="block">
            <span className="text-sm text-gray-600">PLZ</span>
            <input className="input" {...feld('plz')} />
          </label>
          <label className="block">
            <span className="text-sm text-gray-600">Ort</span>
            <input className="input" {...feld('ort')} />
          </label>
          <label className="block sm:col-span-2">
            <span className="text-sm text-gray-600">Notiz</span>
            <textarea className="input" rows={2} {...feld('notiz')} />
          </label>
        </div>

        {/* items-start, weil die Erklaerung daneben zweizeilig wird. */}
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            role="switch"
            className="schieber mt-0.5"
            checked={form.aktiv}
            onChange={(e) => setForm((f) => ({ ...f, aktiv: e.target.checked }))}
          />
          <span>
            aktiv
            <span className="text-gray-500"> – deaktivierte Gebäude verschwinden aus der Auswahl,
              ihre Daten bleiben erhalten</span>
          </span>
        </label>

        {fehler && <div className="text-sm text-red-600">{fehler}</div>}

        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" disabled={speichert} onClick={speichern}>
            {speichert ? 'Speichert…' : 'Speichern'}
          </button>
          {neu && <button className="btn-secondary" onClick={onNeuAbbrechen}>Abbrechen</button>}
          {!neu && (
            <button className="btn-danger ml-auto" onClick={() => setLoeschDialog(true)}>
              Gebäude löschen
            </button>
          )}
        </div>
      </div>

      {!neu && <Fotos gebaeudeId={gebaeude.id} confirm={confirm} />}

      {loeschDialog && (
        <LoeschDialog
          gebaeude={gebaeude}
          onClose={() => setLoeschDialog(false)}
          onGeloescht={() => { setLoeschDialog(false); onGeloescht() }}
        />
      )}
    </div>
  )
}

function InaktiveSchalter({ zeigeInaktive, setZeigeInaktive }) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-600">
      <input
        type="checkbox"
        role="switch"
        className="schieber schieber-sm"
        checked={zeigeInaktive}
        onChange={(e) => setZeigeInaktive(e.target.checked)}
      />
      auch deaktivierte Gebäude in der Auswahl zeigen
    </label>
  )
}

// Löschen nimmt Zähler und Ablesungen mit - deshalb beide Zahlen nennen und
// den Namen abtippen lassen.
function LoeschDialog({ gebaeude, onClose, onGeloescht }) {
  const [eingabe, setEingabe] = useState('')
  const [fehler, setFehler] = useState(null)
  const [laeuft, setLaeuft] = useState(false)
  const passt = eingabe.trim() === gebaeude.name

  const loeschen = async () => {
    setLaeuft(true)
    try {
      await gebaeudeApi.delete(gebaeude.id)
      onGeloescht()
    } catch (e) {
      setFehler(e.response?.data?.detail ?? 'Löschen fehlgeschlagen.')
      setLaeuft(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title="Gebäude löschen"
      footer={
        <div className="flex gap-2 justify-end">
          <button className="btn-secondary" onClick={onClose}>Abbrechen</button>
          <button className="btn-danger" disabled={!passt || laeuft} onClick={loeschen}>
            {laeuft ? 'Löscht…' : 'Endgültig löschen'}
          </button>
        </div>
      }
    >
      <p className="text-sm">
        <b>{gebaeude.name}</b> wird mit allen zugehörigen Daten gelöscht:
      </p>
      <ul className="text-sm list-disc pl-5 space-y-1">
        <li>{gebaeude.zaehler_anzahl} Zähler</li>
        <li>{gebaeude.ablesungen_anzahl} Ablesungen</li>
        <li>alle Fotos und Kostenverknüpfungen</li>
      </ul>
      <p className="text-sm text-gray-600">
        Die Buchungen selbst bleiben erhalten. Das Löschen lässt sich nicht rückgängig machen –
        willst du das Gebäude nur aus der Auswahl nehmen, setze es stattdessen auf „nicht aktiv“.
      </p>
      <label className="block">
        <span className="text-sm text-gray-600">Zum Bestätigen den Namen eintippen:</span>
        <input
          className="input"
          value={eingabe}
          placeholder={gebaeude.name}
          onChange={(e) => setEingabe(e.target.value)}
        />
      </label>
      {fehler && <div className="text-sm text-red-600">{fehler}</div>}
    </Modal>
  )
}

function Fotos({ gebaeudeId, confirm }) {
  const [fotos, setFotos] = useState([])
  const [laedtHoch, setLaedtHoch] = useState(false)
  const [fehler, setFehler] = useState(null)

  const laden = useCallback(() => {
    belegeApi.listGebaeude(gebaeudeId).then((r) => setFotos(r.data))
  }, [gebaeudeId])
  useEffect(() => { laden() }, [laden])

  const hochladen = async (e) => {
    const dateien = [...e.target.files]
    e.target.value = ''
    if (!dateien.length) return
    setLaedtHoch(true)
    setFehler(null)
    try {
      for (const datei of dateien) await belegeApi.uploadGebaeude(gebaeudeId, datei)
      laden()
    } catch (err) {
      setFehler(err.response?.data?.detail ?? 'Hochladen fehlgeschlagen.')
    } finally {
      setLaedtHoch(false)
    }
  }

  const entfernen = async (foto) => {
    if (!await confirm('Foto „' + foto.dateiname + '“ löschen?')) return
    await belegeApi.deleteGebaeude(gebaeudeId, foto.id)
    laden()
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="font-semibold text-gray-700">Fotos</span>
        <label className="btn-secondary btn-sm cursor-pointer">
          {laedtHoch ? 'Lädt hoch…' : 'Foto hinzufügen'}
          <input type="file" accept="image/*" multiple className="hidden"
                 disabled={laedtHoch} onChange={hochladen} />
        </label>
      </div>

      {fehler && <div className="text-sm text-red-600">{fehler}</div>}

      {fotos.length === 0 ? (
        <div className="text-sm text-gray-500">Noch keine Fotos.</div>
      ) : (
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
          {fotos.map((f) => (
            <div key={f.id} className="relative group">
              <a href={belegeApi.dateUrlGebaeude(gebaeudeId, f.id)} target="_blank" rel="noreferrer">
                <img
                  src={belegeApi.dateUrlGebaeude(gebaeudeId, f.id)}
                  alt={f.dateiname}
                  className="w-full h-32 object-cover rounded border border-gray-200"
                />
              </a>
              <button
                className="absolute top-1 right-1 bg-red-600 text-white rounded px-2 text-sm
                           opacity-0 group-hover:opacity-100 focus:opacity-100 transition"
                title="Foto löschen"
                onClick={() => entfernen(f)}
              >×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Nebenkosten-Diagramme ───────────────────────────────────────────────────
// Beide Diagramme zeigen dieselben "Arten": je Zähler mit Kategorie die
// verbrauchsbezogenen Kosten, dazu jede zugeordnete übrige Nebenkosten-
// Kategorie. Farben und Reihenfolge sind in beiden gleich.

// Chart.js stapelt Balken, zieht aber keine Verbindung zwischen gleichen
// Segmenten benachbarter Jahre. Das Plugin zeichnet diese Linien an den
// Segmentkanten entlang - so sieht man je Art, ob sie wächst oder schrumpft.
const reihenlinien = {
  id: 'reihenlinien',
  afterDatasetsDraw(chart) {
    const { ctx } = chart
    ctx.save()
    ctx.lineWidth = 1
    ctx.setLineDash([3, 3])
    chart.data.datasets.forEach((datensatz, index) => {
      const meta = chart.getDatasetMeta(index)
      if (meta.hidden) return
      ctx.strokeStyle = datensatz.backgroundColor
      for (let i = 0; i < meta.data.length - 1; i++) {
        const links = meta.data[i]
        const rechts = meta.data[i + 1]
        if (!datensatz.data[i] || !datensatz.data[i + 1]) continue
        ctx.beginPath()
        ctx.moveTo(links.x + links.width / 2, links.y)
        ctx.lineTo(rechts.x - rechts.width / 2, rechts.y)
        ctx.stroke()
      }
    })
    ctx.restore()
  },
}

function NebenkostenDiagramme({ daten }) {
  // Jahre ohne jeden Betrag gehören nicht ins Diagramm - sie entstehen aus
  // Ablesungen, zu denen es (noch) keine Buchungen gibt.
  const arten = useMemo(() => {
    // Einspeisung ist in ihrem Bezugszaehler verrechnet (siehe kostenarten),
    // taucht hier also nicht als eigene Art auf.
    const ausZaehlern = kostenarten(daten.reihen.filter((r) => r.kategorie_id))
      .map((a) => ({
        name: a.name,
        teile: a.teile,
        jeJahr: Object.fromEntries(Object.entries(a.jeJahr).filter(([, b]) => b)),
      }))
    const ausKategorien = new Map()
    for (const [jahr, posten] of Object.entries(daten.sonstige_kosten)) {
      for (const p of posten) {
        if (!ausKategorien.has(p.kategorie)) ausKategorien.set(p.kategorie, { name: p.kategorie, jeJahr: {} })
        ausKategorien.get(p.kategorie).jeJahr[jahr] = p.betrag
      }
    }
    return [...ausZaehlern, ...ausKategorien.values()]
      .filter((a) => Object.keys(a.jeJahr).length > 0)
  }, [daten])

  const jahre = useMemo(
    () => daten.jahre.filter((j) => arten.some((a) => a.jeJahr[j])),
    [daten.jahre, arten],
  )

  const [jahrFuerKreis, setJahrFuerKreis] = useState(null)
  const gewaehltesJahr = jahre.includes(jahrFuerKreis) ? jahrFuerKreis : jahre[jahre.length - 1]

  if (jahre.length === 0) {
    return (
      <div className="card text-sm text-gray-500">
        Noch keine Nebenkosten erfasst – sobald Zähler oder Kategorien mit Buchungen
        verknüpft sind, erscheint hier die Entwicklung je Jahr.
      </div>
    )
  }

  const farbe = (i) => FARBEN[i % FARBEN.length]

  const balkenDaten = {
    labels: jahre,
    datasets: arten.map((a, i) => ({
      label: a.name,
      data: jahre.map((j) => a.jeJahr[j] ?? null),
      backgroundColor: farbe(i),
      art: a.teile ? a : null,
    })),
  }

  // Ein Tortenstueck kann nur eine positive Groesse sein - Chart.js nimmt von
  // negativen Werten den Absolutwert und zeichnet sie als Kosten. Arten mit
  // negativem Netto (die PV traegt sich und mehr) stehen deshalb als Fussnote
  // unter dem Diagramm statt als falsches Stueck darin.
  const imJahr = arten.map((a, i) => ({
    name: a.name, betrag: a.jeJahr[gewaehltesJahr] ?? 0, farbe: farbe(i),
  }))
  const kreisArten = imJahr.filter((a) => a.betrag > 0)
  const ertraege = imJahr.filter((a) => a.betrag < 0)
  const stueckSumme = kreisArten.reduce((s, a) => s + a.betrag, 0)
  // Gesamt ist die echte Jahresbelastung inklusive der Ertraege, damit die Zahl
  // zum Konto passt. Die Prozente beziehen sich auf die Summe der Stuecke.
  const kreisSumme = imJahr.reduce((s, a) => s + a.betrag, 0)

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="card space-y-3">
        <div className="font-semibold text-gray-700">Entwicklung je Jahr</div>
        <div className="h-72">
          <Bar
            data={balkenDaten}
            plugins={[reihenlinien]}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true, title: { display: true, text: '€' } },
              },
              plugins: {
                legend: { position: 'bottom' },
                tooltip: { callbacks: {
                  label: (k) => `${k.dataset.label}: ${euro(k.parsed.y)}`,
                  afterLabel: (k) => (k.dataset.art
                    ? zerlegung(k.dataset.art, jahre[k.dataIndex])
                    : null),
                } },
              },
            }}
          />
        </div>
      </div>

      <div className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold text-gray-700">Aufteilung {gewaehltesJahr}</span>
          <div className="flex flex-wrap gap-1">
            {jahre.map((j) => (
              <button
                key={j}
                className={`px-2 py-1 text-xs rounded border ${
                  j === gewaehltesJahr
                    ? 'border-blue-600 text-blue-700 font-medium'
                    : 'border-gray-200 text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setJahrFuerKreis(j)}
              >{j}</button>
            ))}
          </div>
        </div>
        <div className="h-72">
          <Pie
            data={{
              labels: kreisArten.map((a) => a.name),
              datasets: [{
                data: kreisArten.map((a) => a.betrag),
                backgroundColor: kreisArten.map((a) => a.farbe),
              }],
            }}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                  callbacks: {
                    label: (k) => {
                      const anteil = stueckSumme ? Math.round((k.parsed / stueckSumme) * 100) : 0
                      return `${k.label}: ${euro(k.parsed)} (${anteil} % der gezeigten Kosten)`
                    },
                  },
                },
              },
            }}
          />
        </div>
        <div className="text-sm text-gray-600 space-y-1">
          <div>Gesamt {gewaehltesJahr}: <b>{euro(kreisSumme)}</b></div>
          {ertraege.map((a) => (
            <div key={a.name} className="text-green-700">
              {a.name}: {euro(-a.betrag)} Ertrag – im Gesamtbetrag abgezogen,
              aber nicht in der Aufteilung enthalten.
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
