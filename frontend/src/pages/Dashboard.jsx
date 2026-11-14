import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { erinnerungenApi, kontenApi, buchungenApi, einstellungenApi } from '../api'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

// Auf volle Euro, für Näherungsangaben – Cent täuschen dort Genauigkeit vor.
function fmtRund(n) {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(n)
}

// "2031-04-01" -> "04/2031". Das Backend liefert immer ISO-Daten.
function monatJahr(iso) {
  if (!iso) return '–'
  const [j, m] = iso.split('-')
  return `${m}/${j}`
}

// Volle Monate von heute bis zum Stichtag; negativ, wenn er in der Vergangenheit liegt.
function monateBis(iso) {
  const ziel = new Date(iso)
  const heute = new Date()
  return (ziel.getFullYear() - heute.getFullYear()) * 12 + (ziel.getMonth() - heute.getMonth())
}

// Fenster, in dem eine Anschlussfinanzierung praktisch relevant wird.
const ZINSBINDUNG_WARN_MONATE = 24

// Betrag in einer Kachel. Auf dem Handy stehen zwei Kacheln nebeneinander, dort
// ragen sechsstellige Beträge in text-xl über den Rand hinaus – daher kleiner und
// mit erlaubtem Umbruch (das Format enthält nur geschützte Leerzeichen, ohne
// break-words würde die Zahl als ein Wort überlaufen).
const BETRAG = 'text-lg sm:text-xl font-bold mt-1 break-words'

export default function Dashboard() {
  const [konten, setKonten] = useState([])
  const [saldi, setSaldi] = useState({})
  const [recent, setRecent] = useState([])
  const [darlehen, setDarlehen] = useState([])
  const [depots, setDepots] = useState([])
  const [zeigeFinanzsaldo, setZeigeFinanzsaldo] = useState(false)
  const [erinnerungen, setErinnerungen] = useState([])

  useEffect(() => {
    kontenApi.list().then((r) => {
      setKonten(r.data)
      r.data.forEach((k) =>
        kontenApi.saldo(k.id).then((s) => setSaldi((prev) => ({ ...prev, [k.id]: s.data.saldo })))
      )
    })
    buchungenApi.list({ pro_seite: 10, status: 'gebucht' }).then((r) => setRecent(r.data.items))
    kontenApi.darlehenUebersicht().then((r) => setDarlehen(r.data))
    kontenApi.depotUebersicht().then((r) => setDepots(r.data))
    einstellungenApi.getDashboard().then((r) => setZeigeFinanzsaldo(r.data.finanzsaldo))
    erinnerungenApi.list().then((r) => setErinnerungen(r.data))
  }, [])

  const giro = konten.filter((k) => k.typ === 'giro')
  const spar = konten.filter((k) => k.typ === 'spar')

  const summe = (liste) => liste.reduce((s, k) => s + (saldi[k.id] ?? 0), 0)
  const sumGiro = summe(giro)
  const sumSpar = summe(spar)
  // Depots zählen mit dem Marktwert (Anteile × Kurs). Das Backend liefert in `wert`
  // bereits den Rückfall auf den Buchungssaldo, falls Anteile oder Kurs fehlen.
  const sumDepot = depots.reduce((s, d) => s + (d.wert ?? 0), 0)
  // Restschulden kommen bereits positiv aus dem Backend.
  const sumVerbindlichkeiten = darlehen.reduce((s, d) => s + (d.real_restschuld ?? 0), 0)
  const finanzsaldo = sumGiro + sumSpar + sumDepot - sumVerbindlichkeiten

  return (
    <div className="p-4 sm:p-6 space-y-6">
      <h2 className="text-xl font-bold">Dashboard</h2>

      <Erinnerungen eintraege={erinnerungen} />

      {zeigeFinanzsaldo && (
        <div
          className="card inline-block"
          title="Summe aller Konten abzüglich der Restschulden. Sachwerte (z.B. Immobilien) sind nicht erfasst und daher nicht enthalten."
        >
          <div className="text-xs text-gray-500 mb-0.5">Finanzsaldo (ohne Sachwerte)</div>
          <div className={`${BETRAG} ${finanzsaldo < 0 ? 'text-red-600' : 'text-gray-900'}`}>
            {fmt(finanzsaldo)}
          </div>
        </div>
      )}

      <KontoGruppe titel="Girokonten" summe={sumGiro} konten={giro} saldi={saldi} />
      <KontoGruppe titel="Sparkonten" summe={sumSpar} konten={spar} saldi={saldi} />
      {depots.length > 0 && (
        <Gruppe titel="Depots" summe={sumDepot}>
          {depots.map((d) => <DepotCard key={d.konto_id} d={d} />)}
        </Gruppe>
      )}

      {darlehen.length > 0 && (
        <Gruppe titel="Darlehen & Kredite" summe={sumVerbindlichkeiten} negativ>
          {darlehen.map((d) => <DarlehenCard key={d.konto_id} d={d} />)}
        </Gruppe>
      )}

      {/* Letzte Buchungen */}
      <div className="card">
        <h3 className="font-semibold mb-3">Letzte Buchungen</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b">
              <th className="pb-1 font-medium">Datum</th>
              <th className="pb-1 font-medium">Empfänger</th>
              <th className="pb-1 font-medium text-right">Betrag</th>
            </tr>
          </thead>
          <tbody>
            {recent.map((b) => (
              <tr key={b.id} className="border-b odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                <td className="py-1.5 text-gray-500">{b.datum}</td>
                <td className="py-1.5">{b.empfaenger ?? '–'}</td>
                <td className={`py-1.5 text-right font-mono ${b.betrag < 0 ? 'text-red-600' : 'text-green-700'}`}>
                  {fmt(b.betrag)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Rahmen um jede Gruppe. Bewusst ohne eigene Hintergrundfarbe: die Kacheln
// darin sind weiß, ein weißer Rahmen würde mit ihnen verschwimmen.
// Die Gruppensumme steht links, der Titel daneben – so ist die Zahl eindeutig
// der Gruppe zugeordnet und wird nicht als weitere Kachel missverstanden.
function Gruppe({ titel, summe, negativ, children }) {
  return (
    <section className="rounded-lg border border-gray-300 p-3 sm:p-4">
      <div className="flex items-baseline gap-3 mb-3">
        <div className={`text-lg font-bold ${negativ || summe < 0 ? 'text-red-600' : 'text-gray-900'}`}>
          {fmt(summe)}
        </div>
        <h3 className="text-sm font-semibold text-gray-600">{titel}</h3>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">{children}</div>
    </section>
  )
}

function KontoGruppe({ titel, summe, konten, saldi }) {
  if (konten.length === 0) return null
  return (
    <Gruppe titel={titel} summe={summe}>
      {konten.map((k) => <SaldoCard key={k.id} title={k.name} value={saldi[k.id]} sub={k.bank} />)}
    </Gruppe>
  )
}

// Feldnamen der API in Bezeichnungen aus dem Kontenformular übersetzen.
const PARAMETER_LABEL = {
  darlehen_betrag: 'Darlehensbetrag',
  zinssatz: 'Zinssatz',
  rate: 'Rate',
  tilgung_start: 'Tilgungsbeginn',
  // nur beim endfälligen Darlehen als fehlend gemeldet
  zinsbindung_jahre: 'Laufzeit in Jahren',
  vollauszahlung_datum: 'Beginn der Laufzeit',
}

// Ab diesem Anteil des vereinbarten Betrags gilt ein Darlehen als voll ausgezahlt.
// Etwas unter 100 %, damit Rundungen und Bereitstellungszinsen nicht dazu führen,
// dass ein längst abgerufenes Darlehen dauerhaft als „in Auszahlung" gilt.
const VOLLAUSZAHLUNG_ANTEIL = 0.995

function DarlehenCard({ d }) {
  // Endfälliges Darlehen (Zwischenfinanzierung): es wird nicht getilgt, ein Fortschrittsbalken
  // stünde dauerhaft auf 0 % und sähe nach Fehler aus. Stattdessen zählt hier, wann welcher
  // Betrag abzulösen ist.
  const istEndfaellig = d.darlehen_art === 'endfaellig'
  // Bezugsgröße ist der höchste je erreichte Schuldenstand, nicht der vereinbarte
  // Betrag: in der Auszahlungsphase ist eine niedrige Restschuld noch keine Tilgung.
  const getilgt = d.hoechststand > 0
    ? Math.min(100, Math.max(0, (1 - d.real_restschuld / d.hoechststand) * 100))
    : null
  // Solange nicht alles abgerufen ist, wäre ein Balken bei 0 % ohne Erklärung
  // irritierend – dort steht stattdessen der Auszahlungsstand.
  const inAuszahlung =
    d.darlehen_betrag > 0 && d.hoechststand < d.darlehen_betrag * VOLLAUSZAHLUNG_ANTEIL
  const restMonate = d.zinsbindung_ende ? monateBis(d.zinsbindung_ende) : null
  // Beim endfälligen Darlehen füllt die Fälligkeit die Zinsbindungsfelder – die Warnung wäre
  // dort nur eine Dopplung der Fälligkeitszeile mit falschem Wort.
  const zinsbindungWarnung =
    d.typ === 'darlehen' && !istEndfaellig && restMonate !== null && restMonate <= ZINSBINDUNG_WARN_MONATE

  return (
    <div className="card p-3 sm:p-4">
      <div className="text-xs text-gray-500 mb-0.5">{d.name}</div>
      {d.bank && <div className="text-xs text-gray-400">{d.bank}</div>}
      <div className={`${BETRAG} text-red-600`}>{fmt(d.real_restschuld)}</div>

      {/* „in Anspruch genommen“ statt „abgerufen“: der Höchststand enthält auch
          belastete Zinsen, ist also nicht exakt die Summe der Auszahlungen. */}
      {istEndfaellig ? (
        <div className="text-xs text-gray-500 mt-2 space-y-0.5">
          <div>
            Endfällig – fällig {d.faelligkeit ? monatJahr(d.faelligkeit) : '–'}
            {d.restlaufzeit_monate != null && ` (noch ${d.restlaufzeit_monate} Monate)`}
          </div>
          {d.monatszins_aktuell != null && <div>Zins z.Zt. {fmt(d.monatszins_aktuell)} / Monat</div>}
          {d.freie_kreditlinie > 0 && <div>Noch nicht abgerufen: {fmtRund(d.freie_kreditlinie)}</div>}
        </div>
      ) : inAuszahlung ? (
        <div className="text-xs text-gray-500 mt-2">
          In Auszahlung – bisher ca. {fmtRund(d.hoechststand)} von {fmtRund(d.darlehen_betrag)} in
          Anspruch genommen
        </div>
      ) : getilgt !== null && (
        <div className="mt-2">
          <div className="h-1.5 bg-gray-200 rounded">
            <div className="h-1.5 bg-green-600 rounded" style={{ width: `${getilgt}%` }} />
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {getilgt > 0 && getilgt < 1 ? 'unter 1' : getilgt.toFixed(0)} % getilgt
          </div>
        </div>
      )}

      {!d.konfiguriert && (
        <div className="text-xs text-amber-600 mt-2">
          Unvollständig gepflegt – es fehlen:{' '}
          {d.fehlende_parameter.map(p => PARAMETER_LABEL[p] ?? p).join(', ')}.{' '}
          <Link to="/konten" className="underline">In den Konten ergänzen</Link>
        </div>
      )}
      {zinsbindungWarnung && (
        <div className="text-xs text-amber-600 mt-2">
          Zinsbindung endet {monatJahr(d.zinsbindung_ende)}
          {d.restschuld_bei_zinsbindungsende != null &&
            ` – Restschuld dann ca. ${fmt(d.restschuld_bei_zinsbindungsende)}`}
        </div>
      )}
    </div>
  )
}

// "2026-03-12" -> "12.03.2026"
function tagMonatJahr(iso) {
  if (!iso) return null
  const [j, m, t] = iso.split('-')
  return `${t}.${m}.${j}`
}

// Anteile können Bruchstücke sein (Sparplan-Ausführungen), daher bis zu 4 Nachkommastellen.
function fmtAnteile(n) {
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits: 4 }).format(n)
}

// Kurse mit 4 Nachkommastellen: die Gewinnschwelle auf Cent gerundet läge je nach
// Anteilszahl schon wieder ein paar Euro neben der echten Nulllinie.
function fmtKurs(n) {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 4,
  }).format(n)
}

// Depotkachel: Marktwert groß, darunter die investierte Summe und der Gewinn/Verlust.
// Ohne gepflegte Anteile/Kurs gibt es keinen Marktwert – dann steht dort der
// Buchungssaldo (= das Eingezahlte) mit einem Hinweis, was zu ergänzen ist.
function DepotCard({ d }) {
  const hatMarktwert = d.marktwert != null
  const positiv = d.gewinn > 0
  return (
    <div className="card p-3 sm:p-4">
      <div className="text-xs text-gray-500 mb-0.5">{d.name}</div>
      {d.bank && <div className="text-xs text-gray-400">{d.bank}</div>}
      <div className={`${BETRAG} text-gray-900`}>{fmt(d.wert)}</div>

      {hatMarktwert ? (
        <div className="text-xs text-gray-500 mt-2 space-y-0.5">
          <div>Investiert: {fmt(d.investiert)}</div>
          <div className={positiv ? 'text-green-700' : d.gewinn < 0 ? 'text-red-600' : ''}>
            {positiv ? '+' : ''}{fmt(d.gewinn)}
            {d.gewinn_prozent != null && ` (${positiv ? '+' : ''}${d.gewinn_prozent.toLocaleString('de-DE', { minimumFractionDigits: 1 })} %)`}
          </div>
          <div className="text-gray-400">
            {fmtAnteile(d.anteile)} Anteile × {fmt(d.kurs)}
            {d.kurs_datum && ` – Kurs vom ${tagMonatJahr(d.kurs_datum)}`}
          </div>
          {/* Kursschwelle zur Nulllinie – darunter steht der Bestand im Minus. */}
          {d.breakeven_kurs != null && (
            <div className="text-gray-400">
              Gewinn ab Kurs {fmtKurs(d.breakeven_kurs)}
            </div>
          )}
        </div>
      ) : (
        <div className="text-xs text-amber-600 mt-2">
          Nur eingezahlte Summe – für den Depotwert fehlen Anteile und Kurs.{' '}
          <Link to="/konten" className="underline">In den Konten ergänzen</Link>
          {d.breakeven_kurs != null && (
            <div className="text-gray-400 mt-0.5">
              Bei {fmtAnteile(d.anteile)} Anteilen läge die Gewinnschwelle bei Kurs {fmtKurs(d.breakeven_kurs)}.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SaldoCard({ title, value, sub }) {
  return (
    <div className="card p-3 sm:p-4">
      <div className="text-xs text-gray-500 mb-0.5">{title}</div>
      {sub && <div className="text-xs text-gray-400">{sub}</div>}
      <div className={`${BETRAG} ${value < 0 ? 'text-red-600' : 'text-gray-900'}`}>
        {value !== undefined ? fmt(value) : '…'}
      </div>
    </div>
  )
}

// ── Erinnerungen ────────────────────────────────────────────────────────────
// Eine Zeile je Art mit Anzahl; die Einzelheiten stehen auf der Zielseite.
// Sonst waechst die Karte mit jedem vergessenen Posten, und das Dashboard
// faengt oben mit einer Endlosliste an.

function Erinnerungen({ eintraege }) {
  const [eingeklappt, setEingeklappt] = useState(false)
  if (eintraege.length === 0) return null

  return (
    <div className="card border-amber-200 bg-amber-50 space-y-2">
      <button
        className="flex items-center gap-2 text-sm font-medium text-amber-800 w-full text-left"
        onClick={() => setEingeklappt((e) => !e)}
      >
        <span className="text-gray-500">{eingeklappt ? '▸' : '▾'}</span>
        {eintraege.length === 1 ? 'Eine Sache wartet' : `${eintraege.length} Sachen warten`}
      </button>

      {!eingeklappt && (
        <ul className="space-y-1 text-sm">
          {eintraege.map((e) => (
            <li key={e.art} className="flex flex-wrap items-baseline gap-x-2">
              <Link to={e.ziel} className="text-amber-800 font-medium underline underline-offset-2">
                {e.text}
              </Link>
              {e.zusatz && <span className="text-gray-600">{e.zusatz}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
