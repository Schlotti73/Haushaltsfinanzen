/**
 * Fahrzeuge als Kostenstelle.
 *
 * Aufbau wie beim Gebäude, nur ohne Zähler: ein Fahrzeug hat genau einen, und
 * der ist der Kilometerstand. Eingetragen wird darum immer der **Stand**, nie
 * die gefahrene Strecke — die rechnet der Server als Differenz, und eine
 * korrigierte Zahl kann so nie zu einer widersprüchlichen Fahrleistung führen.
 *
 * Der Reiter „Tankungen“ erscheint nur, wenn am Fahrzeug „Tankungen erfassen“
 * eingeschaltet ist. Niemand muss an der Zapfsäule den Kilometerstand
 * abschreiben; ohne Tankungen bleibt Kraftstoff eine Kostenart aus den
 * Buchungen, und Fahrleistung und Kosten je Kilometer entstehen trotzdem,
 * solange der Stand einmal im Jahr eingetragen wird.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { fahrzeugeApi, kategorienApi, kontenApi, belegeApi } from '../api'
import { useAuth } from '../AuthContext'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'
import { PencilIcon } from '../components/icons'

function euro(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n ?? 0)
}

function zahl(n, stellen = 0) {
  if (n == null) return '–'
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: stellen, maximumFractionDigits: stellen,
  }).format(n)
}

function fmtDatum(iso) {
  if (!iso) return '–'
  const [j, m, t] = iso.slice(0, 10).split('-')
  return `${t}.${m}.${j}`
}

function fmtMonat(jm) {
  if (!jm) return '–'
  const [j, m] = jm.split('-')
  const namen = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
  return `${namen[Number(m) - 1]} ${j}`
}

const ANTRIEB_LABEL = {
  benzin: 'Benzin', diesel: 'Diesel', elektro: 'Elektro',
  hybrid: 'Hybrid', plugin: 'Plug-in-Hybrid',
}

// Welche Einheit die Tankung vorbelegt. Der Plug-in-Hybrid tankt beides und
// entscheidet je Tankung selbst.
const EINHEIT_VORGABE = { elektro: 'kwh', benzin: 'liter', diesel: 'liter', hybrid: 'liter', plugin: 'liter' }
const EINHEIT_LABEL = { liter: 'l', kwh: 'kWh' }

const LEER = {
  name: '', kennzeichen: '', fahrgestellnummer: '', hersteller_modell: '',
  antrieb: 'benzin', erstzulassung: '', konto_id: '', tankungen_erfassen: false,
  notiz: '', aktiv: true, stand_km: '', stand_datum: '',
}

/** Heute als ISO-Datum, von Hand: toISOString() rechnet nach UTC um. */
function heuteIso() {
  const d = new Date()
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0')].join('-')
}

/**
 * Wie dringend ein Termin ist — und woran das liegt.
 *
 * Ein Termin hat zwei Maßstäbe: Datum und Kilometer. Angezeigt wird der, der
 * zuerst erreicht wird, denn genau der entscheidet.
 */
function terminLage(t) {
  if (t.ueberfaellig) {
    const grund = t.rest_tage != null && t.rest_tage < 0
      ? `seit ${Math.abs(t.rest_tage)} Tagen`
      : `seit ${zahl(Math.abs(t.rest_km))} km`
    return { art: 'eilig', text: 'überfällig', zusatz: grund }
  }
  const kandidaten = []
  if (t.rest_tage != null) kandidaten.push({ wert: t.rest_tage, text: `in ${t.rest_tage} Tagen`, mass: 'tage' })
  if (t.rest_km != null) kandidaten.push({ wert: t.rest_km, text: `in ${zahl(t.rest_km)} km`, mass: 'km' })
  if (kandidaten.length === 0) {
    return { art: 'ruhig', text: 'kein Termin', zusatz: 'kein Intervall hinterlegt' }
  }
  // Tage und Kilometer sind nicht vergleichbar: dringend ist, was knapp ist,
  // je Maßstab mit eigener Schwelle.
  const knapp = kandidaten.some((k) => (k.mass === 'tage' ? k.wert <= 30 : k.wert <= 1000))
  const bald = kandidaten.some((k) => (k.mass === 'tage' ? k.wert <= 60 : k.wert <= 2000))
  const naechster = kandidaten.sort((a, b) => a.wert - b.wert)[0]
  return {
    art: knapp ? 'eilig' : bald ? 'warn' : 'ruhig',
    text: naechster.text,
    zusatz: t.faellig_am && naechster.mass === 'tage'
      ? `fällig ${fmtDatum(t.faellig_am)}`
      : t.faellig_km != null ? `fällig bei ${zahl(t.faellig_km)} km` : '',
  }
}

const LAGE_KLASSE = {
  eilig: 'bg-red-100 text-red-800',
  warn: 'bg-amber-100 text-amber-800',
  ruhig: 'bg-gray-100 text-gray-700',
}

export default function Fahrzeuge() {
  const { user } = useAuth()
  const istAdmin = user?.rolle === 'admin'
  const { confirm, dialog } = useConfirm()

  const [fahrzeuge, setFahrzeuge] = useState([])
  const [gewaehltId, setGewaehltId] = useState(null)
  const [reiter, setReiter] = useState('uebersicht')
  const [uebersicht, setUebersicht] = useState(null)
  const [termine, setTermine] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [konten, setKonten] = useState([])
  const [laedt, setLaedt] = useState(false)
  const [zeigeInaktive, setZeigeInaktive] = useState(false)
  const [neuesFahrzeug, setNeuesFahrzeug] = useState(false)

  const fahrzeugeLaden = useCallback((waehle) => (
    fahrzeugeApi.list(!zeigeInaktive).then((r) => {
      setFahrzeuge(r.data)
      setGewaehltId((id) => {
        const ziel = waehle ?? id
        return r.data.some((f) => f.id === ziel) ? ziel : (r.data[0]?.id ?? null)
      })
      return r.data
    })
  ), [zeigeInaktive])

  useEffect(() => { fahrzeugeLaden() }, [fahrzeugeLaden])

  useEffect(() => {
    kategorienApi.flat().then((r) => setKategorien(r.data))
    kontenApi.list().then((r) => setKonten(r.data))
  }, [])

  const laden = useCallback(() => {
    if (!gewaehltId) { setUebersicht(null); setTermine([]); return }
    setLaedt(true)
    Promise.all([fahrzeugeApi.uebersicht(gewaehltId), fahrzeugeApi.termine(gewaehltId)])
      .then(([u, t]) => { setUebersicht(u.data); setTermine(t.data) })
      .finally(() => setLaedt(false))
  }, [gewaehltId])

  useEffect(() => { laden() }, [laden])

  // Nach jeder Änderung an Ständen, Tankungen oder Terminen stimmen auch die
  // Kennzahlen in der Liste nicht mehr - sie sind alle gerechnet.
  const allesLaden = useCallback(() => {
    fahrzeugeLaden()
    laden()
  }, [fahrzeugeLaden, laden])

  const gewaehlt = fahrzeuge.find((f) => f.id === gewaehltId)
  const reiterListe = [
    ['uebersicht', 'Übersicht'],
    ...(gewaehlt?.tankungen_erfassen ? [['tankungen', 'Tankungen']] : []),
    ['kosten', 'Kosten'],
    ['termine', 'Termine'],
    ['stammdaten', 'Stammdaten'],
  ]

  // Ein abgeschalteter Reiter darf nicht offen stehen bleiben, wenn der
  // Schalter gerade umgelegt wurde.
  useEffect(() => {
    if (reiter === 'tankungen' && gewaehlt && !gewaehlt.tankungen_erfassen) setReiter('uebersicht')
  }, [reiter, gewaehlt])

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-7xl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-bold mr-1">Fahrzeuge</h2>
          {fahrzeuge.map((f) => (
            <button
              key={f.id}
              onClick={() => { setGewaehltId(f.id); setNeuesFahrzeug(false) }}
              className={`px-3 py-1.5 rounded-full text-sm border ${
                f.id === gewaehltId && !neuesFahrzeug
                  ? 'bg-blue-600 border-blue-600 text-white'
                  : 'bg-white border-gray-300 text-gray-700 hover:border-gray-400'
              }`}
            >
              {f.name}
              {f.kennzeichen && (
                <span className={`ml-2 text-xs ${f.id === gewaehltId && !neuesFahrzeug ? 'text-blue-100' : 'text-gray-500'}`}>
                  {f.kennzeichen}
                </span>
              )}
              {!f.aktiv && <span className="ml-2 text-xs">(deaktiviert)</span>}
            </button>
          ))}
          {istAdmin && (
            <button
              className="btn-secondary btn-sm"
              onClick={() => { setNeuesFahrzeug(true); setReiter('stammdaten') }}
            >+ Fahrzeug</button>
          )}
        </div>
        {gewaehlt && !neuesFahrzeug && (
          <span className="text-sm text-gray-500">
            {[gewaehlt.hersteller_modell, ANTRIEB_LABEL[gewaehlt.antrieb],
              gewaehlt.erstzulassung ? `EZ ${fmtDatum(gewaehlt.erstzulassung)}` : null]
              .filter(Boolean).join(' · ')}
          </span>
        )}
      </div>

      {!neuesFahrzeug && (
        <TerminBalken
          termine={termine}
          onSpringen={() => setReiter('termine')}
        />
      )}

      <div className="flex gap-1 border-b border-gray-200">
        {reiterListe.map(([wert, text]) => (
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
      {!laedt && !gewaehltId && !neuesFahrzeug && reiter !== 'stammdaten' && (
        <div className="card text-sm text-gray-500">
          Noch kein Fahrzeug angelegt. Unter „Stammdaten“ legst du eines an – der
          Kilometerstand von heute reicht als Anfang.
        </div>
      )}

      {!laedt && gewaehltId && !neuesFahrzeug && reiter === 'uebersicht' && uebersicht && (
        <Uebersicht
          fahrzeug={gewaehlt}
          daten={uebersicht}
          istAdmin={istAdmin}
          confirm={confirm}
          onAenderung={allesLaden}
        />
      )}
      {!laedt && gewaehltId && !neuesFahrzeug && reiter === 'tankungen' && (
        <Tankungen
          fahrzeug={gewaehlt}
          confirm={confirm}
          onAenderung={allesLaden}
        />
      )}
      {!laedt && gewaehltId && !neuesFahrzeug && reiter === 'kosten' && uebersicht && (
        <Kosten
          fahrzeug={gewaehlt}
          daten={uebersicht}
          kategorien={kategorien}
          istAdmin={istAdmin}
          onAenderung={allesLaden}
        />
      )}
      {!laedt && gewaehltId && !neuesFahrzeug && reiter === 'termine' && (
        <Termine
          fahrzeug={gewaehlt}
          termine={termine}
          istAdmin={istAdmin}
          confirm={confirm}
          onAenderung={allesLaden}
        />
      )}
      {reiter === 'stammdaten' && (
        <Stammdaten
          fahrzeug={neuesFahrzeug ? null : gewaehlt}
          neu={neuesFahrzeug}
          konten={konten}
          istAdmin={istAdmin}
          confirm={confirm}
          zeigeInaktive={zeigeInaktive}
          setZeigeInaktive={setZeigeInaktive}
          onNeuAbbrechen={() => setNeuesFahrzeug(false)}
          onGespeichert={(id) => { setNeuesFahrzeug(false); fahrzeugeLaden(id) }}
          onGeloescht={() => { setNeuesFahrzeug(false); setReiter('uebersicht'); fahrzeugeLaden() }}
          onAenderung={allesLaden}
        />
      )}
      {dialog}
    </div>
  )
}

// ── Hinweisbalken über den Reitern ──────────────────────────────────────────
// Was ansteht, soll man sehen, ohne den Reiter zu öffnen - wie die offenen
// Jahresablesungen beim Gebäude.
function TerminBalken({ termine, onSpringen }) {
  const dringend = termine.filter((t) => {
    if (!t.aktiv) return false
    const lage = terminLage(t)
    return lage.art === 'eilig' || lage.art === 'warn'
  })
  if (dringend.length === 0) return null

  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-amber-900">
            {dringend.length === 1 ? 'Ein Termin steht an' : `${dringend.length} Termine stehen an`}
          </p>
          <ul className="mt-1 space-y-0.5">
            {dringend.map((t) => {
              const lage = terminLage(t)
              return (
                <li key={t.id} className="text-sm text-amber-900">
                  <strong>{t.name}</strong> – {lage.text}
                  {lage.zusatz && <span className="text-amber-800"> ({lage.zusatz})</span>}
                </li>
              )
            })}
          </ul>
        </div>
        <button className="btn-secondary btn-sm" onClick={onSpringen}>Termine öffnen</button>
      </div>
    </div>
  )
}

// ── Übersicht ───────────────────────────────────────────────────────────────
function Uebersicht({ fahrzeug, daten, istAdmin, confirm, onAenderung }) {
  const jahr = new Date().getFullYear()
  const einheit = EINHEIT_LABEL[daten.verbrauch_einheit] || 'l'

  const kennzahlen = [
    {
      titel: `Fahrleistung ${jahr}`,
      wert: fahrzeug.fahrleistung_jahr != null ? `${zahl(fahrzeug.fahrleistung_jahr)} km` : '–',
      fuss: fahrzeug.stand_km != null
        ? `Stand ${zahl(fahrzeug.stand_km)} km am ${fmtDatum(fahrzeug.stand_datum)}`
        : 'noch kein Kilometerstand',
    },
    {
      titel: `Kosten ${jahr}`,
      wert: euro(fahrzeug.kosten_jahr),
      fuss: 'aus den Buchungen der Kostenarten',
    },
    {
      titel: 'Je Kilometer',
      wert: fahrzeug.je_km != null ? `${zahl(fahrzeug.je_km, 2).replace(',00', ',00')} €` : '–',
      fuss: fahrzeug.je_km != null ? `Kosten ${jahr} geteilt durch die Fahrleistung` : 'erst mit Fahrleistung und Kosten',
    },
    fahrzeug.tankungen_erfassen
      ? {
        titel: 'Verbrauch',
        wert: fahrzeug.verbrauch != null ? `${zahl(fahrzeug.verbrauch, 1)} ${einheit}/100 km` : '–',
        fuss: fahrzeug.verbrauch != null
          ? 'zwischen zwei Volltankungen gerechnet'
          : 'erst ab der zweiten Volltankung',
      }
      : (() => {
        const kraftstoff = kostenartSumme(daten, jahr, KRAFTSTOFF_WOERTER)
        return {
          titel: `Kraftstoff ${jahr}`,
          wert: kraftstoff == null ? '–' : euro(kraftstoff),
          fuss: kraftstoff == null
            ? 'keine Kraftstoff-Kategorie hinterlegt'
            : 'nur aus den Buchungen – Tankungen sind abgeschaltet',
        }
      })(),
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {kennzahlen.map((k) => (
          <div key={k.titel} className="card">
            <p className="text-xs uppercase tracking-wide text-gray-500">{k.titel}</p>
            <p className="text-xl font-bold mt-1 tabular-nums">{k.wert}</p>
            <p className="text-xs text-gray-500 mt-1">{k.fuss}</p>
          </div>
        ))}
      </div>

      <Jahrestabelle daten={daten} mitVerbrauch={fahrzeug.tankungen_erfassen} />

      <div className="grid lg:grid-cols-2 gap-4">
        <VertraegeAmFahrzeug vertraege={daten.vertraege} />
        <Dokumente fahrzeugId={fahrzeug.id} istAdmin={istAdmin} confirm={confirm} onAenderung={onAenderung} />
      </div>
    </div>
  )
}

// Woran eine Kraftstoff-Kostenart zu erkennen ist, wenn Tankungen abgeschaltet
// sind. Nur fuer diese eine Kachel - gerechnet wird nirgends damit.
const KRAFTSTOFF_WOERTER = ['kraftstoff', 'tanken', 'benzin', 'diesel', 'sprit', 'strom', 'laden']

/**
 * Summe der Kostenarten eines Jahres, deren Name auf eines der Wörter passt.
 *
 * `null`, wenn keine Kategorie passt: eine 0 behauptete, es sei nichts
 * getankt worden, dabei ist nur nichts hinterlegt.
 */
function kostenartSumme(daten, jahr, woerter) {
  const i = daten.jahre.indexOf(jahr)
  if (i < 0) return null
  const treffer = daten.kostenarten.filter((a) => woerter.some((w) => a.name.toLowerCase().includes(w)))
  if (treffer.length === 0) return null
  return treffer.reduce((summe, a) => summe + (a.betraege[i] ?? 0), 0)
}

function Jahrestabelle({ daten, mitVerbrauch }) {
  const einheit = EINHEIT_LABEL[daten.verbrauch_einheit] || 'l'
  if (daten.jahre.length === 0) {
    return (
      <div className="card text-sm text-gray-500">
        Noch keine Zahlen. Die Kosten kommen aus den Buchungen der Kostenarten – im
        Reiter „Kosten“ hinterlegst du, welche Kategorien zu diesem Fahrzeug gehören.
      </div>
    )
  }
  return (
    <div className="card overflow-x-auto">
      <p className="font-semibold text-gray-800 mb-2">Jahresvergleich</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 border-b border-gray-200">
            <th className="text-left font-medium py-1.5">Kostenart</th>
            {daten.jahre.map((j) => (
              <th key={j} className="text-right font-medium py-1.5 px-2 tabular-nums">{j}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {daten.kostenarten.map((a) => (
            <tr key={a.kategorie_id ?? a.name} className="border-b border-gray-100">
              <td className="py-1.5">{a.name}</td>
              {a.betraege.map((b, i) => (
                <td key={i} className="text-right py-1.5 px-2 tabular-nums">{b ? euro(b) : '–'}</td>
              ))}
            </tr>
          ))}
          <tr className="border-b-2 border-gray-300 font-semibold">
            <td className="py-1.5">Summe</td>
            {daten.summe.map((b, i) => (
              <td key={i} className="text-right py-1.5 px-2 tabular-nums">{euro(b)}</td>
            ))}
          </tr>
          <tr className="text-gray-600">
            <td className="py-1.5">Fahrleistung</td>
            {daten.fahrleistung.map((k, i) => (
              <td key={i} className="text-right py-1.5 px-2 tabular-nums">{k != null ? `${zahl(k)} km` : '–'}</td>
            ))}
          </tr>
          <tr className="text-gray-600">
            <td className="py-1.5">Je Kilometer</td>
            {daten.je_km.map((w, i) => (
              <td key={i} className="text-right py-1.5 px-2 tabular-nums">{w != null ? `${zahl(w, 2)} €` : '–'}</td>
            ))}
          </tr>
          {/* Ist die Erfassung abgeschaltet, verspricht der Schalter "kein
              Verbrauch". Alte Tankungen bleiben in der Datenbank und tauchen
              wieder auf, sobald er wieder an ist - eine Zahl zu zeigen, die
              man nirgends mehr nachsehen kann, waere schlechter. */}
          {mitVerbrauch && daten.verbrauch.some((v) => v != null) && (
            <tr className="text-gray-600">
              <td className="py-1.5">Verbrauch</td>
              {daten.verbrauch.map((v, i) => (
                <td key={i} className="text-right py-1.5 px-2 tabular-nums">
                  {v != null ? `${zahl(v, 1)} ${einheit}` : '–'}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
      <p className="text-xs text-gray-500 mt-2">
        Fahrleistung und Kosten je Kilometer sind gerechnet, nicht gespeichert. Fehlt der
        Kilometerstand zum 31.12., ist das Jahr zu kurz gerechnet – darum mahnt das Dashboard ihn an.
      </p>
    </div>
  )
}

function VertraegeAmFahrzeug({ vertraege }) {
  return (
    <div className="card">
      <p className="font-semibold text-gray-800 mb-2">Verträge am Fahrzeug</p>
      {vertraege.length === 0 ? (
        <p className="text-sm text-gray-500">
          Keiner zugeordnet. Versicherung, Steuer oder Leasing bleiben Verträge und werden
          dort gepflegt – im Vertrag wählst du dieses Fahrzeug als Kostenstelle.
        </p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {vertraege.map((v) => (
              <tr key={v.vertrag_id} className="border-b border-gray-100 last:border-0">
                <td className="py-1.5">
                  <a className="text-blue-700 hover:underline" href={`/vertraege?id=${v.vertrag_id}`}>{v.name}</a>
                  {v.anbieter && <span className="text-gray-500 text-xs ml-2">{v.anbieter}</span>}
                </td>
                <td className="py-1.5 text-right tabular-nums">{euro(v.soll_jahr)}<span className="text-gray-500 text-xs">/Jahr</span></td>
                <td className="py-1.5 text-right text-xs text-gray-500">
                  {v.status === 'gekuendigt' ? 'gekündigt'
                    : v.kuendigen_bis ? `kündbar bis ${fmtDatum(v.kuendigen_bis)}` : 'läuft'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── Dokumente ───────────────────────────────────────────────────────────────
// Fahrzeugschein, HU-Bericht, Werkstattrechnung. Mehrere je Fahrzeug: ein
// Fahrzeug sammelt seine Unterlagen über Jahre.
function Dokumente({ fahrzeugId, istAdmin, confirm, onAenderung }) {
  const [belege, setBelege] = useState([])
  const [laedtHoch, setLaedtHoch] = useState(false)
  const [fehler, setFehler] = useState('')

  const laden = useCallback(() => {
    belegeApi.listFahrzeug(fahrzeugId).then((r) => setBelege(r.data))
  }, [fahrzeugId])

  useEffect(() => { laden() }, [laden])

  const hochladen = async (datei) => {
    if (!datei) return
    setFehler('')
    setLaedtHoch(true)
    try {
      await belegeApi.uploadFahrzeug(fahrzeugId, datei)
      laden()
      onAenderung?.()
    } catch (err) {
      setFehler(err?.response?.data?.detail || 'Hochladen fehlgeschlagen.')
    } finally {
      setLaedtHoch(false)
    }
  }

  const loeschen = async (b) => {
    if (!await confirm(`„${b.dateiname}“ endgültig löschen?`)) return
    await belegeApi.deleteFahrzeug(fahrzeugId, b.id)
    laden()
    onAenderung?.()
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <p className="font-semibold text-gray-800">Dokumente</p>
        {istAdmin && (
          <label className="btn-secondary btn-sm cursor-pointer">
            {laedtHoch ? 'lädt…' : '+ Datei'}
            <input
              type="file" className="hidden" accept="image/jpeg,image/png,image/webp,application/pdf"
              onChange={(e) => { hochladen(e.target.files?.[0]); e.target.value = '' }}
            />
          </label>
        )}
      </div>
      {fehler && <p className="text-sm text-red-700 mb-2">{fehler}</p>}
      {belege.length === 0 ? (
        <p className="text-sm text-gray-500">
          Fahrzeugschein, HU-Bericht, Werkstattrechnung – sie gehören zum Fahrzeug und
          nicht zu einer einzelnen Zahlung.
        </p>
      ) : (
        <ul className="space-y-1">
          {belege.map((b) => (
            <li key={b.id} className="flex items-center justify-between text-sm">
              <a
                className="text-blue-700 hover:underline truncate"
                href={belegeApi.dateUrlFahrzeug(fahrzeugId, b.id)}
                target="_blank" rel="noreferrer"
              >{b.dateiname}</a>
              {istAdmin && (
                <button className="btn-danger btn-icon-sm ml-2" title="Löschen" onClick={() => loeschen(b)}>×</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Tankungen ───────────────────────────────────────────────────────────────
function Tankungen({ fahrzeug, confirm, onAenderung }) {
  const [tankungen, setTankungen] = useState([])
  const [staende, setStaende] = useState([])
  const [offen, setOffen] = useState([])
  const [neu, setNeu] = useState({
    datum: heuteIso(), km: '', menge: '',
    einheit: EINHEIT_VORGABE[fahrzeug.antrieb] || 'liter', voll: true, buchung_id: '', betrag: '',
  })
  const [fehler, setFehler] = useState('')

  const laden = useCallback(() => {
    Promise.all([
      fahrzeugeApi.tankungen(fahrzeug.id),
      fahrzeugeApi.staende(fahrzeug.id),
      fahrzeugeApi.kraftstoffOffen(fahrzeug.id),
    ]).then(([t, s, o]) => { setTankungen(t.data); setStaende(s.data); setOffen(o.data) })
  }, [fahrzeug.id])

  useEffect(() => { laden() }, [laden])

  const speichern = async () => {
    setFehler('')
    try {
      await fahrzeugeApi.tankungCreate(fahrzeug.id, {
        datum: neu.datum,
        km: Number(neu.km),
        menge: Number(String(neu.menge).replace(',', '.')),
        einheit: neu.einheit,
        voll: neu.voll,
        buchung_id: neu.buchung_id ? Number(neu.buchung_id) : null,
        betrag: neu.betrag ? Number(String(neu.betrag).replace(',', '.')) : null,
      })
      setNeu((n) => ({ ...n, km: '', menge: '', buchung_id: '', betrag: '' }))
      laden()
      onAenderung()
    } catch (err) {
      setFehler(err?.response?.data?.detail || 'Speichern fehlgeschlagen.')
    }
  }

  const loeschen = async (t) => {
    if (!await confirm(
      `Tankung vom ${fmtDatum(t.datum)} löschen? Die Buchung bleibt bestehen.`,
    )) return
    await fahrzeugeApi.tankungDelete(t.id)
    laden()
    onAenderung()
  }

  const einheitLabel = EINHEIT_LABEL[neu.einheit] || 'l'

  return (
    <div className="space-y-4">
      <div className="card">
        <p className="font-semibold text-gray-800 mb-2">Tankung eintragen</p>
        <div className="grid grid-cols-2 md:grid-cols-7 gap-2 items-end">
          <div>
            <label className="label">Datum</label>
            <input className="input" type="date" value={neu.datum}
                   onChange={(e) => setNeu({ ...neu, datum: e.target.value })} />
          </div>
          <div>
            <label className="label">Kilometerstand</label>
            <input className="input tabular-nums" type="number" inputMode="numeric" value={neu.km}
                   onChange={(e) => setNeu({ ...neu, km: e.target.value })} />
          </div>
          <div>
            <label className="label">Menge</label>
            <div className="flex gap-1">
              <input className="input tabular-nums" value={neu.menge}
                     onChange={(e) => setNeu({ ...neu, menge: e.target.value })} />
              {fahrzeug.antrieb === 'plugin' ? (
                <select className="input w-20" aria-label="Einheit" value={neu.einheit}
                        onChange={(e) => setNeu({ ...neu, einheit: e.target.value })}>
                  <option value="liter">l</option>
                  <option value="kwh">kWh</option>
                </select>
              ) : (
                <span className="self-center text-sm text-gray-500 px-1">{einheitLabel}</span>
              )}
            </div>
          </div>
          <div>
            <label className="label">Buchung</label>
            <select className="input" value={neu.buchung_id}
                    onChange={(e) => setNeu({ ...neu, buchung_id: e.target.value })}>
              <option value="">– keine –</option>
              {offen.map((o) => (
                <option key={o.buchung_id} value={o.buchung_id}>
                  {fmtDatum(o.datum)} · {euro(Math.abs(o.betrag))} · {o.empfaenger || 'ohne Empfänger'}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Betrag</label>
            <input className="input tabular-nums" placeholder={neu.buchung_id ? 'aus Buchung' : ''}
                   disabled={!!neu.buchung_id} value={neu.buchung_id ? '' : neu.betrag}
                   onChange={(e) => setNeu({ ...neu, betrag: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm pb-2">
            <input type="checkbox" checked={neu.voll}
                   onChange={(e) => setNeu({ ...neu, voll: e.target.checked })} />
            Volltankung
          </label>
          <button className="btn-primary" disabled={!neu.km || !neu.menge} onClick={speichern}>Eintragen</button>
        </div>
        {fehler && <p className="text-sm text-red-700 mt-2">{fehler}</p>}
        <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-3">
          <p className="text-xs font-semibold text-blue-900">Warum „Volltankung“ wichtig ist</p>
          <p className="text-sm text-blue-900 mt-1">
            Der Verbrauch entsteht nur zwischen zwei vollen Tanks – erst dann ist bekannt, wie viel
            auf die gefahrenen Kilometer wirklich hineingegangen ist. Eine Teilbetankung zählt mit,
            bekommt aber keinen eigenen Wert; ihre Menge fließt in die nächste Volltankung ein.
          </p>
          <p className="text-xs text-blue-800 mt-1">
            Das Geld steht schon im Kontoauszug: wähle die Buchung, statt den Betrag abzuschreiben.
          </p>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <p className="font-semibold text-gray-800 mb-2">Tankungen</p>
        {tankungen.length === 0 ? (
          <p className="text-sm text-gray-500">Noch keine Tankung erfasst.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-200">
                <th className="text-left font-medium py-1.5">Datum</th>
                <th className="text-right font-medium py-1.5 px-2">Stand</th>
                <th className="text-right font-medium py-1.5 px-2"
                    title="Strecke seit der vorigen Tankung. Der Verbrauch rechnet dagegen von einem vollen Tank zum naechsten.">
                  Gefahren
                </th>
                <th className="text-right font-medium py-1.5 px-2">Menge</th>
                <th className="text-right font-medium py-1.5 px-2">Verbrauch</th>
                <th className="text-right font-medium py-1.5 px-2">Preis</th>
                <th className="text-right font-medium py-1.5 px-2">Betrag</th>
                <th className="text-left font-medium py-1.5 px-2">Herkunft</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tankungen.map((t) => (
                <tr key={t.id} className="border-b border-gray-100">
                  <td className="py-1.5">{fmtDatum(t.datum)}</td>
                  <td className="text-right py-1.5 px-2 tabular-nums">{zahl(t.km)}</td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-600">
                    {t.gefahren != null ? `${zahl(t.gefahren)} km` : '–'}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums">
                    {zahl(t.menge, 2)} {EINHEIT_LABEL[t.einheit]}
                    {!t.voll && <span className="text-amber-700 text-xs ml-1" title="Teilbetankung">teil</span>}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums">
                    {t.verbrauch != null ? zahl(t.verbrauch, 2) : '–'}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums text-gray-600">
                    {t.preis_je_einheit != null ? `${zahl(t.preis_je_einheit, 3)} €` : '–'}
                  </td>
                  <td className="text-right py-1.5 px-2 tabular-nums">{t.betrag != null ? euro(t.betrag) : '–'}</td>
                  <td className="py-1.5 px-2 text-xs text-gray-500">
                    {t.buchung_id ? (t.buchung_empfaenger || 'Buchung') : 'von Hand'}
                  </td>
                  <td className="py-1.5 text-right">
                    <button className="btn-danger btn-icon-sm" title="Löschen" onClick={() => loeschen(t)}>×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Jahresstand
        fahrzeug={fahrzeug}
        staende={staende}
        weitereDaten={tankungen.map((t) => t.datum)}
        confirm={confirm}
        onAenderung={() => { laden(); onAenderung() }}
      />
    </div>
  )
}

// ── Kilometerstände ohne Tankung ────────────────────────────────────────────
function Jahresstand({ fahrzeug, staende, weitereDaten = [], confirm, onAenderung }) {
  const jahr = new Date().getFullYear()
  // Gemahnt wird nicht der fehlende Eintrag, sondern die Lücke, die er lässt:
  // gerechnet wird mit dem letzten Stand des Jahres, woher er auch kommt. Eine
  // Tankung am 28.12. ist so gut wie eine Ablesung am 31.12.
  const fehlt = ![...staende.map((s) => s.datum), ...weitereDaten]
    .some((d) => d >= `${jahr - 1}-12-17` && d <= `${jahr - 1}-12-31`)
  const [neu, setNeu] = useState({ datum: `${jahr - 1}-12-31`, km: '', art: 'jahr', notiz: '' })
  const [fehler, setFehler] = useState('')

  const speichern = async () => {
    setFehler('')
    try {
      await fahrzeugeApi.standCreate(fahrzeug.id, {
        datum: neu.datum,
        km: Number(neu.km),
        art: neu.art,
        notiz: neu.notiz || null,
      })
      setNeu({ ...neu, km: '', notiz: '' })
      onAenderung()
    } catch (err) {
      setFehler(err?.response?.data?.detail || 'Speichern fehlgeschlagen.')
    }
  }

  const loeschen = async (s) => {
    if (!await confirm(
      `Kilometerstand vom ${fmtDatum(s.datum)} löschen? Die Fahrleistung der betroffenen `
      + 'Jahre wird danach neu gerechnet.',
    )) return
    await fahrzeugeApi.standDelete(s.id)
    onAenderung()
  }

  return (
    <div className="card">
      <p className="font-semibold text-gray-800 mb-2">Kilometerstand ohne Tankung</p>
      {fehlt && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 mb-3 text-sm text-amber-900">
          Der Stand zum 31.12.{jahr - 1} fehlt noch. Ohne ihn ist die Fahrleistung
          von {jahr - 1} zu kurz und die Kosten je Kilometer zu hoch gerechnet.
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
        <div>
          <label className="label">Datum</label>
          <input className="input" type="date" value={neu.datum}
                 onChange={(e) => setNeu({ ...neu, datum: e.target.value })} />
        </div>
        <div>
          <label className="label">Kilometerstand</label>
          <input className="input tabular-nums" type="number" inputMode="numeric" value={neu.km}
                 onChange={(e) => setNeu({ ...neu, km: e.target.value })} />
        </div>
        <div>
          <label className="label">Art</label>
          <select className="input" value={neu.art} onChange={(e) => setNeu({ ...neu, art: e.target.value })}>
            <option value="jahr">Jahresstand (31.12.)</option>
            <option value="zwischen">Zwischenstand</option>
          </select>
        </div>
        <div>
          <label className="label">Notiz</label>
          <input className="input" value={neu.notiz} onChange={(e) => setNeu({ ...neu, notiz: e.target.value })} />
        </div>
        <button className="btn-primary" disabled={!neu.km} onClick={speichern}>Eintragen</button>
      </div>
      {fehler && <p className="text-sm text-red-700 mt-2">{fehler}</p>}
      <p className="text-xs text-gray-500 mt-2">
        Ein Jahresstand je Jahr, Zwischenstände beliebig viele – ein Werkstattbesuch oder eine
        Übernahme ist auch eine Ablesung.
      </p>

      {staende.length > 0 && (
        <table className="w-full text-sm mt-3">
          <tbody>
            {staende.map((s) => (
              <tr key={s.id} className="border-b border-gray-100 last:border-0">
                <td className="py-1.5">{fmtDatum(s.datum)}</td>
                <td className="py-1.5 tabular-nums text-right">{zahl(s.km)} km</td>
                <td className="py-1.5 px-2 text-xs text-gray-500">
                  {s.art === 'jahr' ? `Jahresstand ${s.jahr}` : 'Zwischenstand'}
                  {s.notiz ? ` · ${s.notiz}` : ''}
                </td>
                <td className="py-1.5 text-right">
                  <button className="btn-danger btn-icon-sm" title="Löschen" onClick={() => loeschen(s)}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── Kosten ──────────────────────────────────────────────────────────────────
function Kosten({ fahrzeug, daten, kategorien, istAdmin, onAenderung }) {
  const [zuordnungen, setZuordnungen] = useState([])
  const [offen, setOffen] = useState([])
  const [neueKategorie, setNeueKategorie] = useState('')
  const [fehler, setFehler] = useState('')

  const laden = useCallback(() => {
    fahrzeugeApi.kostenkategorien(fahrzeug.id).then((r) => setZuordnungen(r.data))
    if (fahrzeug.tankungen_erfassen) {
      fahrzeugeApi.kraftstoffOffen(fahrzeug.id).then((r) => setOffen(r.data))
    } else {
      setOffen([])
    }
  }, [fahrzeug.id, fahrzeug.tankungen_erfassen])

  useEffect(() => { laden() }, [laden])

  const hinzufuegen = async (kategorieId) => {
    setFehler('')
    try {
      await fahrzeugeApi.kostenkategorieAdd(fahrzeug.id, kategorieId)
      setNeueKategorie('')
      laden()
      onAenderung()
    } catch (err) {
      // Die Meldung des Servers nennt die andere Kostenstelle - sie ist
      // brauchbarer als alles, was hier stehen koennte.
      setFehler(err?.response?.data?.detail || 'Hinzufügen fehlgeschlagen.')
    }
  }

  const loesen = async (z) => {
    await fahrzeugeApi.kostenkategorieDelete(z.id)
    laden()
    onAenderung()
  }

  const jahr = new Date().getFullYear()
  const spalte = daten.jahre.indexOf(jahr)
  const fahrleistung = spalte >= 0 ? daten.fahrleistung[spalte] : null

  return (
    <div className="space-y-4">
      <div className="card">
        <p className="font-semibold text-gray-800 mb-2">Kostenarten dieses Fahrzeugs</p>
        <p className="text-sm text-gray-500 mb-3">
          Die Kosten kommen aus den Buchungen – hier steht nur, welche Kategorien zu diesem
          Fahrzeug gehören. Es gibt keine zweite Buchführung.
        </p>
        {zuordnungen.length === 0 ? (
          <p className="text-sm text-gray-500">Noch keine Kategorie hinterlegt.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-200">
                <th className="text-left font-medium py-1.5">Kategorie</th>
                {daten.jahre.map((j) => (
                  <th key={j} className="text-right font-medium py-1.5 px-2 tabular-nums">{j}</th>
                ))}
                <th className="text-right font-medium py-1.5 px-2">Je 100 km</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {zuordnungen.map((z) => {
                const reihe = daten.kostenarten.find((a) => a.kategorie_id === z.kategorie_id)
                const jahresbetrag = reihe && spalte >= 0 ? reihe.betraege[spalte] : null
                return (
                  <tr key={z.id} className="border-b border-gray-100">
                    <td className="py-1.5">{z.kategorie_name}</td>
                    {daten.jahre.map((j, i) => (
                      <td key={j} className="text-right py-1.5 px-2 tabular-nums">
                        {reihe?.betraege[i] ? euro(reihe.betraege[i]) : '–'}
                      </td>
                    ))}
                    <td className="text-right py-1.5 px-2 tabular-nums text-gray-600">
                      {jahresbetrag && fahrleistung ? euro(jahresbetrag / fahrleistung * 100) : '–'}
                    </td>
                    <td className="py-1.5 text-right">
                      {istAdmin && (
                        <button className="btn-secondary btn-sm" onClick={() => loesen(z)}>lösen</button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {istAdmin && (
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="min-w-[16rem]">
              <label className="label">Kategorie hinzufügen</label>
              <KategorieSelect
                kategorien={kategorien}
                value={neueKategorie}
                onChange={(id) => { setNeueKategorie(id ?? ''); if (id) hinzufuegen(id) }}
              />
            </div>
          </div>
        )}
        {fehler && (
          <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            {fehler}
          </div>
        )}
        <p className="text-xs text-gray-500 mt-2">
          Eine Kategorie gehört an genau eine Kostenstelle. Hängt „Kraftstoff“ an zwei Fahrzeugen
          oder zugleich am Gebäude, zählte jede Buchung zweimal.
        </p>
      </div>

      {fahrzeug.tankungen_erfassen && (
        <div className="card">
          <p className="font-semibold text-gray-800 mb-2">Abgleich Kraftstoff {jahr}</p>
          {daten.kraftstoff_buchungen == null ? (
            <p className="text-sm text-gray-500">
              Noch keine Tankung an einer Buchung. Sobald eine Tankung mit ihrer Buchung
              verknüpft ist, steht hier, welche Tankstellenbuchungen ohne Menge geblieben sind.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">Buchungen</p>
                  <p className="text-lg font-bold tabular-nums">{euro(daten.kraftstoff_buchungen)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">erfasste Tankungen</p>
                  <p className="text-lg font-bold tabular-nums">{euro(daten.kraftstoff_tankungen)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500">ohne Tankung</p>
                  <p className="text-lg font-bold tabular-nums">
                    {euro((daten.kraftstoff_buchungen ?? 0) - (daten.kraftstoff_tankungen ?? 0))}
                  </p>
                  <p className="text-xs text-gray-500">{daten.kraftstoff_offen_anzahl} Buchungen</p>
                </div>
              </div>
              {offen.length > 0 && (
                <table className="w-full text-sm mt-3">
                  <tbody>
                    {offen.slice(0, 10).map((o) => (
                      <tr key={o.buchung_id} className="border-b border-gray-100 last:border-0">
                        <td className="py-1.5">{fmtDatum(o.datum)}</td>
                        <td className="py-1.5 px-2 truncate max-w-[18rem]">{o.empfaenger || '–'}</td>
                        <td className="py-1.5 text-right tabular-nums">{euro(Math.abs(o.betrag))}</td>
                        <td className="py-1.5 text-right text-xs text-gray-500">Menge fehlt</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="text-xs text-gray-500 mt-2">
                Eine Hilfe beim Nachtragen, keine Instanz: welche Kategorie der Kraftstoff ist,
                ergibt sich aus den Buchungen, die schon an Tankungen hängen.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Termine ─────────────────────────────────────────────────────────────────
function Termine({ fahrzeug, termine, istAdmin, confirm, onAenderung }) {
  const [form, setForm] = useState(null)
  const [erledigt, setErledigt] = useState(null)
  const [fehler, setFehler] = useState('')

  const loeschen = async (t) => {
    if (!await confirm(
      `„${t.name}“ mit seiner Historie löschen? Die verknüpften Buchungen bleiben bestehen.`,
    )) return
    await fahrzeugeApi.terminDelete(t.id)
    onAenderung()
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <p className="font-semibold text-gray-800">Was ansteht</p>
          {istAdmin && (
            <button
              className="btn-secondary btn-sm"
              onClick={() => setForm({ name: '', intervall_monate: '', intervall_km: '', notiz: '', zuletzt_am: '', zuletzt_km: '' })}
            >+ Termin</button>
          )}
        </div>
        {termine.length === 0 ? (
          <p className="text-sm text-gray-500">
            Noch kein Termin. HU, Inspektion, Zahnriemen, Reifenwechsel – gespeichert wird nur
            das Intervall, der Termin selbst wird gerechnet.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-200">
                <th className="text-left font-medium py-1.5">Termin</th>
                <th className="text-left font-medium py-1.5 px-2">Intervall</th>
                <th className="text-left font-medium py-1.5 px-2">Zuletzt</th>
                <th className="text-left font-medium py-1.5 px-2">Fällig</th>
                <th className="text-left font-medium py-1.5 px-2">Rechnerisch</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {termine.map((t) => {
                const lage = terminLage(t)
                return (
                  <tr key={t.id} className={`border-b border-gray-100 ${t.aktiv ? '' : 'text-gray-400'}`}>
                    <td className="py-2">
                      <span className="font-medium">{t.name}</span>
                      {!t.aktiv && <span className="text-xs ml-2">(abgeschaltet)</span>}
                      <span className={`ml-2 px-2 py-0.5 rounded text-xs ${LAGE_KLASSE[lage.art]}`}>
                        {lage.text}
                      </span>
                      {t.notiz && <p className="text-xs text-gray-500">{t.notiz}</p>}
                    </td>
                    <td className="py-2 px-2 text-gray-600">
                      {[t.intervall_monate ? `${t.intervall_monate} Monate` : null,
                        t.intervall_km ? `${zahl(t.intervall_km)} km` : null]
                        .filter(Boolean).join(' / ') || '–'}
                    </td>
                    <td className="py-2 px-2 text-gray-600">
                      {t.zuletzt_am ? fmtDatum(t.zuletzt_am) : 'nie'}
                      {t.zuletzt_km != null && <span className="text-xs text-gray-500 ml-1">({zahl(t.zuletzt_km)} km)</span>}
                    </td>
                    <td className="py-2 px-2 text-gray-600">
                      {[t.faellig_am ? fmtDatum(t.faellig_am) : null,
                        t.faellig_km != null ? `${zahl(t.faellig_km)} km` : null]
                        .filter(Boolean).join(' / ') || '–'}
                    </td>
                    <td className="py-2 px-2 text-gray-600">
                      {t.prognose_monat ? fmtMonat(t.prognose_monat) : '–'}
                    </td>
                    <td className="py-2 text-right whitespace-nowrap">
                      <button className="btn-secondary btn-sm mr-1"
                              onClick={() => setErledigt({ termin: t, datum: heuteIso(), km: fahrzeug.stand_km ?? '', notiz: '' })}>
                        erledigt
                      </button>
                      {istAdmin && (
                        <>
                          <button className="btn-secondary btn-icon-sm mr-1" title="Bearbeiten"
                                  onClick={() => setForm({ ...t, intervall_monate: t.intervall_monate ?? '', intervall_km: t.intervall_km ?? '' })}>
                            <PencilIcon />
                          </button>
                          <button className="btn-danger btn-icon-sm" title="Löschen" onClick={() => loeschen(t)}>×</button>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-3">
          <p className="text-xs font-semibold text-blue-900">Woher „Rechnerisch“ kommt</p>
          <p className="text-sm text-blue-900 mt-1">
            Aus dem letzten Kilometerstand und dem Durchschnitt der letzten zwölf Monate. Wird
            weniger gefahren, rutscht der Monat beim nächsten Aufruf von selbst nach hinten –
            darum wird er nicht gespeichert.
          </p>
          <p className="text-xs text-blue-800 mt-1">
            Vorlauf und Abschalten der Erinnerung stehen in den Einstellungen und gelten je
            Datenbank: Vorgabe 60 Tage beziehungsweise 2.000 km.
          </p>
        </div>
      </div>

      {erledigt && (
        <div className="card">
          <p className="font-semibold text-gray-800 mb-2">„{erledigt.termin.name}“ erledigt eintragen</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 items-end">
            <div>
              <label className="label">Datum</label>
              <input className="input" type="date" value={erledigt.datum}
                     onChange={(e) => setErledigt({ ...erledigt, datum: e.target.value })} />
            </div>
            <div>
              <label className="label">Kilometerstand</label>
              <input className="input tabular-nums" type="number" value={erledigt.km}
                     onChange={(e) => setErledigt({ ...erledigt, km: e.target.value })} />
            </div>
            <div>
              <label className="label">Notiz</label>
              <input className="input" value={erledigt.notiz}
                     onChange={(e) => setErledigt({ ...erledigt, notiz: e.target.value })} />
            </div>
            <div className="flex gap-2">
              <button
                className="btn-primary"
                onClick={async () => {
                  setFehler('')
                  try {
                    await fahrzeugeApi.erledigt(erledigt.termin.id, {
                      datum: erledigt.datum,
                      km: erledigt.km === '' ? null : Number(erledigt.km),
                      notiz: erledigt.notiz || null,
                    })
                    setErledigt(null)
                    onAenderung()
                  } catch (err) {
                    setFehler(err?.response?.data?.detail || 'Speichern fehlgeschlagen.')
                  }
                }}
              >Eintragen</button>
              <button className="btn-secondary" onClick={() => setErledigt(null)}>Abbrechen</button>
            </div>
          </div>
          {fehler && <p className="text-sm text-red-700 mt-2">{fehler}</p>}
          <p className="text-xs text-gray-500 mt-2">
            Der Kilometerstand zählt gleich als Stand mit – ein Werkstattbesuch ist eine Ablesung.
            Der nächste Termin folgt aus dem Intervall.
          </p>
        </div>
      )}

      {form && istAdmin && (
        <TerminForm
          fahrzeugId={fahrzeug.id}
          initial={form}
          onFertig={() => { setForm(null); onAenderung() }}
          onAbbrechen={() => setForm(null)}
        />
      )}

      <Historie termine={termine} confirm={confirm} onAenderung={onAenderung} />
    </div>
  )
}

function TerminForm({ fahrzeugId, initial, onFertig, onAbbrechen }) {
  const [f, setF] = useState(initial)
  const [fehler, setFehler] = useState('')
  const neu = !f.id
  const set = (k, v) => setF((prev) => ({ ...prev, [k]: v }))

  const speichern = async () => {
    setFehler('')
    const koerper = {
      name: f.name,
      intervall_monate: f.intervall_monate === '' ? null : Number(f.intervall_monate),
      intervall_km: f.intervall_km === '' ? null : Number(f.intervall_km),
      notiz: f.notiz || null,
    }
    try {
      if (neu) {
        await fahrzeugeApi.terminCreate(fahrzeugId, {
          ...koerper,
          zuletzt_am: f.zuletzt_am || null,
          zuletzt_km: f.zuletzt_km === '' ? null : Number(f.zuletzt_km),
        })
      } else {
        await fahrzeugeApi.terminUpdate(f.id, { ...koerper, aktiv: f.aktiv })
      }
      onFertig()
    } catch (err) {
      setFehler(err?.response?.data?.detail || 'Speichern fehlgeschlagen.')
    }
  }

  return (
    <div className="card">
      <p className="font-semibold text-gray-800 mb-2">{neu ? 'Neuer Termin' : `Termin: ${initial.name}`}</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <label className="label">Bezeichnung *</label>
          <input className="input" autoFocus value={f.name} onChange={(e) => set('name', e.target.value)} />
        </div>
        <div>
          <label className="label">Alle … Monate</label>
          <input className="input" type="number" min="1" placeholder="leer = nicht nach Zeit"
                 value={f.intervall_monate} onChange={(e) => set('intervall_monate', e.target.value)} />
        </div>
        <div>
          <label className="label">Alle … Kilometer</label>
          <input className="input" type="number" min="1" placeholder="leer = nicht nach Strecke"
                 value={f.intervall_km} onChange={(e) => set('intervall_km', e.target.value)} />
        </div>
        <div>
          <label className="label">Notiz</label>
          <input className="input" value={f.notiz || ''} onChange={(e) => set('notiz', e.target.value)} />
        </div>
        {neu && (
          <>
            <div>
              <label className="label">Zuletzt durchgeführt am</label>
              <input className="input" type="date" value={f.zuletzt_am}
                     onChange={(e) => set('zuletzt_am', e.target.value)} />
            </div>
            <div>
              <label className="label">… bei Kilometerstand</label>
              <input className="input" type="number" value={f.zuletzt_km}
                     onChange={(e) => set('zuletzt_km', e.target.value)} />
            </div>
          </>
        )}
        {!neu && (
          <label className="flex items-center gap-2 text-sm self-end pb-2">
            <input type="checkbox" checked={f.aktiv} onChange={(e) => set('aktiv', e.target.checked)} />
            aktiv
          </label>
        )}
      </div>
      <p className="text-xs text-gray-500 mt-2">
        Beide Intervalle dürfen zusammen gelten – fällig ist dann, was zuerst erreicht wird.
        Ohne Intervall gibt es keinen Termin und keine Erinnerung, nur die Historie.
        {neu && ' „Zuletzt“ wird als erste Durchführung gespeichert, nicht als Feld am Termin.'}
      </p>
      {fehler && <p className="text-sm text-red-700 mt-2">{fehler}</p>}
      <div className="flex justify-end gap-2 mt-3">
        <button className="btn-secondary" onClick={onAbbrechen}>Abbrechen</button>
        <button className="btn-primary" disabled={!f.name} onClick={speichern}>Speichern</button>
      </div>
    </div>
  )
}

function Historie({ termine, confirm, onAenderung }) {
  const zeilen = useMemo(() => (
    termine
      .flatMap((t) => t.erledigungen.map((e) => ({ ...e, termin_name: t.name })))
      .sort((a, b) => (a.datum < b.datum ? 1 : -1))
  ), [termine])

  if (zeilen.length === 0) return null

  const loeschen = async (e) => {
    if (!await confirm(
      `Durchführung vom ${fmtDatum(e.datum)} löschen? Der nächste Termin wird danach neu gerechnet.`,
    )) return
    await fahrzeugeApi.erledigungDelete(e.id)
    onAenderung()
  }

  return (
    <div className="card">
      <p className="font-semibold text-gray-800 mb-2">Erledigt</p>
      <table className="w-full text-sm">
        <tbody>
          {zeilen.map((e) => (
            <tr key={e.id} className="border-b border-gray-100 last:border-0">
              <td className="py-1.5">{fmtDatum(e.datum)}</td>
              <td className="py-1.5 px-2">{e.termin_name}</td>
              <td className="py-1.5 px-2 tabular-nums text-right text-gray-600">
                {e.km != null ? `${zahl(e.km)} km` : '–'}
              </td>
              <td className="py-1.5 px-2 tabular-nums text-right">{e.kosten != null ? euro(e.kosten) : '–'}</td>
              <td className="py-1.5 px-2 text-xs text-gray-500">{e.notiz || ''}</td>
              <td className="py-1.5 text-right">
                <button className="btn-danger btn-icon-sm" title="Löschen" onClick={() => loeschen(e)}>×</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Stammdaten ──────────────────────────────────────────────────────────────
function Stammdaten({
  fahrzeug, neu, konten, istAdmin, confirm, zeigeInaktive, setZeigeInaktive,
  onNeuAbbrechen, onGespeichert, onGeloescht, onAenderung,
}) {
  const [f, setF] = useState(LEER)
  const [fehler, setFehler] = useState('')
  const [staende, setStaende] = useState([])

  useEffect(() => {
    if (neu) {
      setF({ ...LEER, stand_datum: heuteIso() })
    } else if (fahrzeug) {
      setF({
        ...LEER, ...fahrzeug,
        kennzeichen: fahrzeug.kennzeichen || '',
        fahrgestellnummer: fahrzeug.fahrgestellnummer || '',
        hersteller_modell: fahrzeug.hersteller_modell || '',
        erstzulassung: fahrzeug.erstzulassung || '',
        konto_id: fahrzeug.konto_id || '',
        notiz: fahrzeug.notiz || '',
      })
    }
  }, [neu, fahrzeug])

  const standLaden = useCallback(() => {
    if (neu || !fahrzeug) { setStaende([]); return }
    fahrzeugeApi.staende(fahrzeug.id).then((r) => setStaende(r.data))
  }, [neu, fahrzeug])

  useEffect(() => { standLaden() }, [standLaden])

  const set = (k, v) => setF((prev) => ({ ...prev, [k]: v }))

  const speichern = async () => {
    setFehler('')
    const koerper = {
      name: f.name,
      kennzeichen: f.kennzeichen || null,
      fahrgestellnummer: f.fahrgestellnummer || null,
      hersteller_modell: f.hersteller_modell || null,
      antrieb: f.antrieb,
      erstzulassung: f.erstzulassung || null,
      konto_id: f.konto_id === '' ? null : Number(f.konto_id),
      tankungen_erfassen: !!f.tankungen_erfassen,
      notiz: f.notiz || null,
      aktiv: !!f.aktiv,
    }
    try {
      if (neu) {
        const r = await fahrzeugeApi.create({
          ...koerper,
          stand_km: f.stand_km === '' ? null : Number(f.stand_km),
          stand_datum: f.stand_datum || null,
        })
        onGespeichert(r.data.id)
      } else {
        await fahrzeugeApi.update(fahrzeug.id, koerper)
        onGespeichert(fahrzeug.id)
        onAenderung?.()
      }
    } catch (err) {
      setFehler(err?.response?.data?.detail || 'Speichern fehlgeschlagen.')
    }
  }

  const loeschen = async () => {
    if (!await confirm(
      `„${fahrzeug.name}“ mit Kilometerständen, Tankungen, Terminen und Dokumenten löschen? `
      + 'Buchungen und Verträge bleiben bestehen – sie verlieren nur die Zuordnung.',
    )) return
    await fahrzeugeApi.delete(fahrzeug.id)
    onGeloescht()
  }

  if (!neu && !fahrzeug) {
    return (
      <div className="card text-sm text-gray-500">
        Noch kein Fahrzeug angelegt.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <p className="font-semibold text-gray-800">{neu ? 'Neues Fahrzeug' : 'Stammdaten'}</p>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" checked={zeigeInaktive} onChange={(e) => setZeigeInaktive(e.target.checked)} />
            Deaktivierte anzeigen
          </label>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <div>
            <label className="label">Bezeichnung *</label>
            <input className="input" required autoFocus value={f.name} disabled={!istAdmin}
                   onChange={(e) => set('name', e.target.value)} />
          </div>
          <div>
            <label className="label">Kennzeichen</label>
            <input className="input" value={f.kennzeichen} disabled={!istAdmin}
                   onChange={(e) => set('kennzeichen', e.target.value)} />
          </div>
          <div>
            <label className="label">Antrieb</label>
            <select className="input" value={f.antrieb} disabled={!istAdmin}
                    onChange={(e) => set('antrieb', e.target.value)}>
              {Object.entries(ANTRIEB_LABEL).map(([wert, text]) => (
                <option key={wert} value={wert}>{text}</option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">Bestimmt die Einheit der Tankungen: Liter oder kWh.</p>
          </div>
          <div>
            <label className="label">Hersteller und Modell</label>
            <input className="input" value={f.hersteller_modell} disabled={!istAdmin}
                   onChange={(e) => set('hersteller_modell', e.target.value)} />
          </div>
          <div>
            <label className="label">Erstzulassung</label>
            <input className="input" type="date" value={f.erstzulassung} disabled={!istAdmin}
                   onChange={(e) => set('erstzulassung', e.target.value)} />
          </div>
          <div>
            <label className="label">Konto</label>
            <select className="input" value={f.konto_id} disabled={!istAdmin}
                    onChange={(e) => set('konto_id', e.target.value)}>
              <option value="">– keines –</option>
              {konten.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="label">Fahrgestellnummer</label>
            <input className="input font-mono text-[13px]" maxLength={32} value={f.fahrgestellnummer}
                   disabled={!istAdmin} onChange={(e) => set('fahrgestellnummer', e.target.value.toUpperCase())} />
            <p className="text-xs text-gray-500 mt-1">
              17 Stellen aus dem Fahrzeugschein. Versicherung und Werkstatt fragen danach.
            </p>
          </div>
          <div>
            <label className="label">Notiz</label>
            <input className="input" value={f.notiz} disabled={!istAdmin}
                   onChange={(e) => set('notiz', e.target.value)} />
          </div>
        </div>

        <div className="mt-4 rounded-md border border-gray-200 p-3">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={!!f.tankungen_erfassen} disabled={!istAdmin}
                   onChange={(e) => set('tankungen_erfassen', e.target.checked)} />
            <span>
              <strong>Tankungen erfassen</strong>
              <span className="block text-gray-600">
                Aus: kein Reiter, keine Mengen, kein Verbrauch – niemand muss an der Zapfsäule den
                Kilometerstand abschreiben. Kraftstoff bleibt eine Kostenart aus den Buchungen,
                und Fahrleistung und Kosten je Kilometer entstehen trotzdem, solange der Stand
                einmal im Jahr eingetragen wird.
              </span>
            </span>
          </label>
        </div>

        {neu && (
          <div className="mt-4">
            <p className="font-semibold text-gray-800 mb-2 text-sm">Kilometerstand</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="label">Stand heute</label>
                <input className="input tabular-nums" type="number" value={f.stand_km}
                       onChange={(e) => set('stand_km', e.target.value)} />
              </div>
              <div>
                <label className="label">abgelesen am</label>
                <input className="input" type="date" value={f.stand_datum}
                       onChange={(e) => set('stand_datum', e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Freiwillig – ohne ihn beginnt die Historie mit der ersten Tankung oder Ablesung.
              Gespeichert wird immer der Stand, nie die gefahrene Strecke.
            </p>
          </div>
        )}

        {!neu && (
          <label className="flex items-center gap-2 text-sm mt-4">
            <input type="checkbox" checked={!!f.aktiv} disabled={!istAdmin}
                   onChange={(e) => set('aktiv', e.target.checked)} />
            aktiv
          </label>
        )}

        {fehler && <p className="text-sm text-red-700 mt-3">{fehler}</p>}

        {istAdmin && (
          <div className="flex justify-between items-center mt-4">
            <div>
              {!neu && (
                <button className="btn-danger" onClick={loeschen}>Fahrzeug löschen</button>
              )}
            </div>
            <div className="flex gap-2">
              {neu && <button className="btn-secondary" onClick={onNeuAbbrechen}>Abbrechen</button>}
              <button className="btn-primary" disabled={!f.name} onClick={speichern}>Speichern</button>
            </div>
          </div>
        )}
      </div>

      {!neu && !fahrzeug.tankungen_erfassen && (
        <Jahresstand
          fahrzeug={fahrzeug}
          staende={staende}
          confirm={confirm}
          onAenderung={() => { standLaden(); onAenderung?.() }}
        />
      )}
    </div>
  )
}
