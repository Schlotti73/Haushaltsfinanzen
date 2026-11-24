import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  vertraegeApi, kontenApi, kategorienApi, empfaengerApi, wiederkehrendApi, belegeApi,
  fahrzeugeApi,
} from '../api'
import { useConfirm } from '../components/useConfirm'
import KategorieSelect from '../components/KategorieSelect'
import { PencilIcon } from '../components/icons'

function fmt(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n ?? 0)
}

function fmtDatum(iso) {
  if (!iso) return '–'
  const [j, m, t] = iso.slice(0, 10).split('-')
  return `${t}.${m}.${j}`
}

const EINHEIT_LABEL = { tage: 'Tage', wochen: 'Wochen', monate: 'Monate' }
const EINHEIT_EINZAHL = { tage: 'Tag', wochen: 'Woche', monate: 'Monat' }

/** "3 Monate", aber "1 Monat" - die Frist steht an jeder zweiten Stelle. */
function fristText(anzahl, einheit) {
  if (!anzahl) return null
  const wort = anzahl === 1 ? EINHEIT_EINZAHL[einheit] : EINHEIT_LABEL[einheit]
  return `${anzahl} ${wort || ''}`.trim()
}
const RHYTHMUS_LABEL = {
  monatlich: 'monatlich', zweimonatlich: 'alle 2 Monate',
  quartal: 'quartalsweise', jaehrlich: 'jährlich',
}

const LEER = {
  name: '', anbieter: '', vertragsnummer: '', kundennummer: '',
  kategorie_id: '', konto_id: '', empfaenger_id: '', mandatsreferenz: '', fahrzeug_id: '',
  beginn: '', laufzeit_bis: '', kuendigungsfrist: '',
  kuendigungsfrist_einheit: 'monate', verlaengerung_monate: '', notiz: '', aktiv: true,
}

/**
 * Wie die Frist in der Liste und im Kopf des Vertrags erscheint.
 *
 * `kuendigen_bis` kommt gerechnet vom Server und ist leer, wenn es keinen
 * Termin gibt, auf den man warten muss. Leer heisst aber dreierlei, und das
 * trennt diese Funktion: gekuendigt, unbefristet (jederzeit kuendbar) oder die
 * Laufzeit laeuft ohne Verlaengerung aus.
 */
function terminAnsicht(v) {
  if (v.gekuendigt_am) {
    return {
      text: 'gekündigt', art: 'aus',
      zusatz: v.endet_am ? `läuft aus zum ${fmtDatum(v.endet_am)}` : `gekündigt am ${fmtDatum(v.gekuendigt_am)}`,
    }
  }
  const frist = v.kuendigungsfrist
    ? `${fristText(v.kuendigungsfrist, v.kuendigungsfrist_einheit)} Frist`
    : 'keine Frist hinterlegt'
  if (!v.laufzeit_bis) {
    return { text: 'jederzeit', art: 'ruhig', zusatz: `${frist}, keine Laufzeit` }
  }
  if (!v.kuendigen_bis) {
    return { text: 'läuft aus', art: 'aus', zusatz: `Laufzeit bis ${fmtDatum(v.laufzeit_bis)}` }
  }
  const tage = v.tage_bis_kuendigung
  const verl = v.verlaengerung_monate
    ? `verlängert um ${fristText(v.verlaengerung_monate, 'monate')}`
    : 'ohne Verlängerung'
  return {
    text: fmtDatum(v.kuendigen_bis),
    art: tage <= 14 ? 'eilig' : tage <= 60 ? 'warn' : 'ruhig',
    zusatz: `in ${tage} Tagen · ${frist}, ${verl}`,
  }
}

const TERMIN_KLASSE = {
  eilig: 'bg-red-100 text-red-800',
  warn: 'bg-amber-100 text-amber-800',
  aus: 'bg-gray-100 text-gray-600',
  ruhig: 'bg-gray-100 text-gray-700',
}

// ── Formular ────────────────────────────────────────────────────────────────
function VertragForm({ initial, kategorien, konten, empfaenger, fahrzeuge, onSave, onCancel }) {
  const [f, setF] = useState(initial || LEER)
  const [fehler, setFehler] = useState('')
  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }))

  // Dieselbe Rechnung wie im Backend, nur fuer die Vorschau waehrend des
  // Tippens: Laufzeitende minus Frist, bei verstrichenem Termin so oft um die
  // Verlaengerung weiter, bis er in der Zukunft liegt.
  const vorschau = useMemo(() => {
    const frist = Number(f.kuendigungsfrist)
    if (!f.laufzeit_bis || !frist) return null
    const heute = new Date()
    heute.setHours(0, 0, 0, 0)
    let ende = new Date(`${f.laufzeit_bis}T00:00:00`)
    if (Number.isNaN(ende.getTime())) return null
    const minusFrist = (d) => {
      const x = new Date(d)
      if (f.kuendigungsfrist_einheit === 'tage') x.setDate(x.getDate() - frist)
      else if (f.kuendigungsfrist_einheit === 'wochen') x.setDate(x.getDate() - frist * 7)
      else x.setMonth(x.getMonth() - frist)
      return x
    }
    let termin = minusFrist(ende)
    const verl = Number(f.verlaengerung_monate)
    let schritte = 0
    while (termin < heute && verl > 0 && schritte < 200) {
      ende = new Date(ende)
      ende.setMonth(ende.getMonth() + verl)
      termin = minusFrist(ende)
      schritte += 1
    }
    if (termin < heute) return { ausgelaufen: true }
    // Von Hand und nicht mit toISOString(): das rechnet nach UTC um und
    // schiebt in unserer Zeitzone jedes Datum einen Tag zurueck.
    const iso = (d) => [
      d.getFullYear(),
      String(d.getMonth() + 1).padStart(2, '0'),
      String(d.getDate()).padStart(2, '0'),
    ].join('-')
    return { termin: iso(termin), ende: iso(ende) }
  }, [f.laufzeit_bis, f.kuendigungsfrist, f.kuendigungsfrist_einheit, f.verlaengerung_monate])

  const zahl = (wert) => (wert === '' || wert === null ? null : Number(wert))

  const handleSubmit = async e => {
    e.preventDefault()
    setFehler('')
    try {
      await onSave({
        ...f,
        anbieter: f.anbieter || null,
        vertragsnummer: f.vertragsnummer || null,
        kundennummer: f.kundennummer || null,
        kategorie_id: zahl(f.kategorie_id),
        konto_id: zahl(f.konto_id),
        empfaenger_id: zahl(f.empfaenger_id),
        fahrzeug_id: zahl(f.fahrzeug_id),
        mandatsreferenz: f.mandatsreferenz || null,
        beginn: f.beginn || null,
        laufzeit_bis: f.laufzeit_bis || null,
        kuendigungsfrist: zahl(f.kuendigungsfrist),
        verlaengerung_monate: zahl(f.verlaengerung_monate),
        notiz: f.notiz || null,
      })
    } catch (err) {
      // 409 ist der haeufige Fall: die Mandatsreferenz steht an einem anderen
      // Vertrag. Die Meldung des Servens nennt welchen - sie ist brauchbarer
      // als alles, was hier stehen koennte.
      setFehler(err?.response?.data?.detail || 'Speichern fehlgeschlagen.')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <p className="font-semibold text-gray-800 mb-2 text-sm">Wer und was</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Bezeichnung *</label>
            <input className="input" required autoFocus value={f.name} onChange={e => set('name', e.target.value)} />
          </div>
          <div>
            <label className="label">Anbieter</label>
            <input className="input" value={f.anbieter || ''} onChange={e => set('anbieter', e.target.value)} />
          </div>
          <div>
            <label className="label">Kategorie</label>
            <KategorieSelect kategorien={kategorien} value={f.kategorie_id} onChange={id => set('kategorie_id', id ?? '')} />
            <p className="text-xs text-gray-500 mt-1">Derselbe Baum wie bei den Buchungen – kein zweites Ordnungssystem.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Vertragsnummer</label>
              <input className="input" value={f.vertragsnummer || ''} onChange={e => set('vertragsnummer', e.target.value)} />
            </div>
            <div>
              <label className="label">Kundennummer</label>
              <input className="input" value={f.kundennummer || ''} onChange={e => set('kundennummer', e.target.value)} />
            </div>
          </div>
          <div>
            <label className="label">Fahrzeug</label>
            <select className="input" value={f.fahrzeug_id || ''} onChange={e => set('fahrzeug_id', e.target.value)}>
              <option value="">– keines –</option>
              {(fahrzeuge || []).map(fz => <option key={fz.id} value={fz.id}>{fz.name}</option>)}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Versicherung, Steuer oder Leasing: der Vertrag bleibt hier, das Fahrzeug ist nur
              seine Kostenstelle und zeigt ihn mit an.
            </p>
          </div>
        </div>
      </div>

      <div>
        <p className="font-semibold text-gray-800 mb-2 text-sm">Laufzeit und Frist</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Beginn</label>
            <input className="input" type="date" value={f.beginn || ''} onChange={e => set('beginn', e.target.value)} />
          </div>
          <div>
            <label className="label">Laufzeit bis</label>
            <input className="input" type="date" value={f.laufzeit_bis || ''} onChange={e => set('laufzeit_bis', e.target.value)} />
            <p className="text-xs text-gray-500 mt-1">Leer lassen heißt: unbefristet, jederzeit mit Frist kündbar.</p>
          </div>
          <div>
            <label className="label">Kündigungsfrist</label>
            <div className="flex gap-2">
              <input className="input w-24" type="number" min="0" value={f.kuendigungsfrist ?? ''}
                     onChange={e => set('kuendigungsfrist', e.target.value)} />
              <select className="input" aria-label="Einheit der Frist" value={f.kuendigungsfrist_einheit}
                      onChange={e => set('kuendigungsfrist_einheit', e.target.value)}>
                <option value="monate">Monate</option>
                <option value="wochen">Wochen</option>
                <option value="tage">Tage</option>
              </select>
            </div>
          </div>
          <div>
            <label className="label">Verlängert sich um (Monate)</label>
            <input className="input" type="number" min="0" placeholder="leer = gar nicht"
                   value={f.verlaengerung_monate ?? ''} onChange={e => set('verlaengerung_monate', e.target.value)} />
          </div>
        </div>

        {vorschau && (
          <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-3">
            <p className="text-xs font-semibold text-blue-900">Daraus folgt</p>
            {vorschau.ausgelaufen ? (
              <p className="text-sm text-blue-900 mt-1">
                Der Termin ist verstrichen und ohne Verlängerung läuft der Vertrag aus.
              </p>
            ) : (
              <p className="text-sm text-blue-900 mt-1">
                Kündigen bis <strong className="tabular-nums">{fmtDatum(vorschau.termin)}</strong>
                {' '}– sonst läuft der Vertrag bis zum {fmtDatum(vorschau.ende)} weiter.
              </p>
            )}
            <p className="text-xs text-blue-800 mt-1">
              Das Datum wird nicht gespeichert, sondern bei jedem Abruf aus diesen drei Feldern gerechnet –
              so kann es nach einer Verlängerung nicht veralten.
            </p>
          </div>
        )}
      </div>

      <div>
        <p className="font-semibold text-gray-800 mb-2 text-sm">Zahlungen erkennen</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Mandatsreferenz der Lastschrift</label>
            <input className="input font-mono text-[13px]" value={f.mandatsreferenz || ''}
                   onChange={e => set('mandatsreferenz', e.target.value)} />
            <p className="text-xs text-gray-500 mt-1">
              Steht im CSV-Export der Bank und ist pro Vertrag stabil – ein härteres Kriterium als jedes
              Textmuster. Leer lassen und die nächste passende Buchung zum Lernen anbieten.
            </p>
          </div>
          <div>
            <label className="label">Konto</label>
            <select className="input" value={f.konto_id || ''} onChange={e => set('konto_id', e.target.value)}>
              <option value="">– keines –</option>
              {konten.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
            </select>
            <label className="label mt-3">Empfänger</label>
            <select className="input" value={f.empfaenger_id || ''} onChange={e => set('empfaenger_id', e.target.value)}>
              <option value="">– keiner –</option>
              {empfaenger.map(e2 => <option key={e2.id} value={e2.id}>{e2.name}</option>)}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Das weichere Merkmal – es trägt die Zuordnung, wenn der Vertrag über PayPal &amp; Co. bezahlt wird.
            </p>
          </div>
        </div>
      </div>

      <div>
        <label className="label">Notiz</label>
        <textarea className="input" rows={2} value={f.notiz || ''} onChange={e => set('notiz', e.target.value)} />
      </div>

      {fehler && <p className="text-sm text-red-600">{fehler}</p>}

      <div className="flex gap-2">
        <button type="submit" className="btn btn-primary btn-sm">Speichern</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  )
}

// ── Kündigung eintragen ─────────────────────────────────────────────────────
function KuendigungForm({ vertrag, onSave, onCancel }) {
  const [am, setAm] = useState(new Date().toISOString().slice(0, 10))
  const [endet, setEndet] = useState(vertrag.laufzeit_bis || '')

  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={e => { e.preventDefault(); onSave({ gekuendigt_am: am, endet_am: endet || null }) }}
    >
      <div>
        <label className="label">Gekündigt am</label>
        <input className="input" type="date" required value={am} onChange={e => setAm(e.target.value)} />
      </div>
      <div>
        <label className="label">Endet am</label>
        <input className="input" type="date" value={endet} onChange={e => setEndet(e.target.value)} />
      </div>
      <button type="submit" className="btn btn-primary btn-sm">Eintragen</button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Abbrechen</button>
    </form>
  )
}

// ── Detailansicht ───────────────────────────────────────────────────────────
function Detail({ vertrag, raten, kategorien, konten, empfaenger, fahrzeuge, onZurueck, onAendern, onNeuLaden }) {
  const { confirm, dialog } = useConfirm()
  const [zahlungen, setZahlungen] = useState([])
  const [dokumente, setDokumente] = useState([])
  const [bearbeiten, setBearbeiten] = useState(false)
  const [kuendigen, setKuendigen] = useState(false)
  const [freieRaten, setFreieRaten] = useState([])
  const [rateWaehlen, setRateWaehlen] = useState(false)

  const termin = terminAnsicht(vertrag)

  const ladeAnhaenge = useCallback(() => {
    vertraegeApi.zahlungen(vertrag.id).then(r => setZahlungen(r.data))
    belegeApi.listVertrag(vertrag.id).then(r => setDokumente(r.data))
  }, [vertrag.id])

  useEffect(() => { ladeAnhaenge() }, [ladeAnhaenge])

  const hochladen = async e => {
    const datei = e.target.files?.[0]
    if (!datei) return
    await belegeApi.uploadVertrag(vertrag.id, datei)
    e.target.value = ''
    ladeAnhaenge()
    onNeuLaden()
  }

  const dokumentLoeschen = async beleg => {
    if (!await confirm(`„${beleg.dateiname}" wirklich löschen?`)) return
    await belegeApi.deleteVertrag(vertrag.id, beleg.id)
    ladeAnhaenge()
    onNeuLaden()
  }

  const rateAnhaengen = async wkId => {
    await vertraegeApi.rateAnhaengen(vertrag.id, wkId)
    setRateWaehlen(false)
    onNeuLaden()
  }

  const rateLoesen = async rate => {
    if (!await confirm('Rate vom Vertrag lösen? Die wiederkehrende Buchung selbst bleibt bestehen.')) return
    await vertraegeApi.rateLoesen(vertrag.id, rate.id)
    onNeuLaden()
  }

  const rateWaehlenOeffnen = async () => {
    const r = await wiederkehrendApi.list()
    setFreieRaten(r.data.filter(wb => !wb.vertrag_id))
    setRateWaehlen(true)
  }

  const abweichung = Math.abs((vertrag.soll_jahr || 0) - (vertrag.ist_12monate || 0))

  if (bearbeiten) {
    return (
      <div className="p-6">
        <button className="text-sm text-blue-600 hover:underline" onClick={() => setBearbeiten(false)}>‹ Zurück zum Vertrag</button>
        <div className="card p-4 mt-3 max-w-4xl">
          <h2 className="font-semibold text-gray-800 mb-3">{vertrag.name} bearbeiten</h2>
          <VertragForm
            initial={{
              ...vertrag,
              kategorie_id: vertrag.kategorie_id ?? '',
              konto_id: vertrag.konto_id ?? '',
              empfaenger_id: vertrag.empfaenger_id ?? '',
              fahrzeug_id: vertrag.fahrzeug_id ?? '',
            }}
            kategorien={kategorien}
            konten={konten}
            empfaenger={empfaenger}
            fahrzeuge={fahrzeuge}
            onSave={async data => { await onAendern(vertrag.id, data); setBearbeiten(false) }}
            onCancel={() => setBearbeiten(false)}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4 max-w-5xl">
      <div>
        <button className="text-sm text-blue-600 hover:underline" onClick={onZurueck}>‹ Alle Verträge</button>
        <div className="flex flex-wrap items-baseline gap-3 mt-1">
          <h1 className="text-xl font-bold text-gray-900">{vertrag.name}</h1>
          <span className={`text-xs px-2 py-0.5 rounded font-medium ${
            vertrag.status === 'gekuendigt' ? 'bg-gray-100 text-gray-600' : 'bg-green-100 text-green-700'
          }`}>{vertrag.status === 'gekuendigt' ? 'gekündigt' : 'laufend'}</span>
          <span className="text-sm text-gray-600">
            {[vertrag.anbieter, vertrag.kategorie_name].filter(Boolean).join(' · ')}
          </span>
        </div>
      </div>

      {/* Frist-Kopf: die einzige Zahl, deren Versäumnis Geld kostet. */}
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-amber-800">Kündigen bis</p>
            <p className="text-2xl font-bold tabular-nums text-amber-900">{termin.text}</p>
            <p className="text-xs text-amber-800 mt-0.5">{termin.zusatz}</p>
          </div>
          <div className="flex-1 min-w-[320px]">
            <p className="text-xs font-semibold text-amber-800 mb-1">So kommt das Datum zustande</p>
            <p className="text-xs leading-relaxed text-amber-800">
              {vertrag.gekuendigt_am
                ? 'Der Vertrag ist gekündigt – es gibt keinen Termin mehr, auf den zu achten wäre.'
                : !vertrag.laufzeit_bis
                  ? 'Ohne Laufzeitende gilt nur die Frist: der Vertrag ist jederzeit kündbar, und es gibt keinen Termin, der verfallen könnte.'
                  : `Laufzeit bis ${fmtDatum(vertrag.laufzeit_bis)} minus ${fristText(vertrag.kuendigungsfrist, vertrag.kuendigungsfrist_einheit) || 'keine'} Kündigungsfrist.`}
              {' '}Gerechnet wird bei jedem Abruf; gespeichert ist nur, was in den Stammdaten steht.
            </p>
          </div>
          {!vertrag.gekuendigt_am && !kuendigen && (
            <button className="btn btn-secondary btn-sm" onClick={() => setKuendigen(true)}>Kündigung eintragen</button>
          )}
        </div>
        {kuendigen && (
          <div className="mt-3 border-t border-amber-200 pt-3">
            <KuendigungForm
              vertrag={vertrag}
              onCancel={() => setKuendigen(false)}
              onSave={async data => { await onAendern(vertrag.id, data); setKuendigen(false) }}
            />
          </div>
        )}
        {vertrag.gekuendigt_am && (
          <div className="mt-3 border-t border-amber-200 pt-3 flex flex-wrap items-center gap-3 text-xs text-amber-800">
            <span>Gekündigt am {fmtDatum(vertrag.gekuendigt_am)}{vertrag.endet_am ? `, endet am ${fmtDatum(vertrag.endet_am)}` : ''}.</span>
            <button className="text-blue-700 hover:underline"
                    onClick={() => onAendern(vertrag.id, { gekuendigt_am: null, endet_am: null })}>
              Kündigung zurücknehmen
            </button>
          </div>
        )}
      </div>

      <div className="card p-4">
        <div className="flex items-baseline justify-between gap-3 mb-3">
          <p className="font-semibold text-gray-800 text-sm">Stammdaten</p>
          <button className="text-xs text-blue-600 hover:underline font-medium" onClick={() => setBearbeiten(true)}>Bearbeiten</button>
        </div>
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {[
            ['Vertragsnummer', vertrag.vertragsnummer],
            ['Kundennummer', vertrag.kundennummer],
            ['Beginn', vertrag.beginn ? fmtDatum(vertrag.beginn) : null],
            ['Laufzeit bis', vertrag.laufzeit_bis ? fmtDatum(vertrag.laufzeit_bis) : 'unbefristet'],
            ['Kündigungsfrist', fristText(vertrag.kuendigungsfrist, vertrag.kuendigungsfrist_einheit)],
            ['Verlängert um', vertrag.verlaengerung_monate
              ? fristText(vertrag.verlaengerung_monate, 'monate') : 'gar nicht'],
            ['Kategorie', vertrag.kategorie_name],
            ['Konto', vertrag.konto_name],
            ['Fahrzeug', vertrag.fahrzeug_name],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-gray-500">{k}</dt>
              <dd className="font-medium">{v || '–'}</dd>
            </div>
          ))}
          <div className="col-span-2">
            <dt className="text-xs text-gray-500">Mandatsreferenz</dt>
            <dd className="font-mono text-[13px]">{vertrag.mandatsreferenz || '– noch keine gelernt'}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-gray-500">Empfänger</dt>
            <dd className="font-medium">{vertrag.empfaenger_name || '–'}</dd>
          </div>
          {vertrag.notiz && (
            <div className="col-span-2 md:col-span-4">
              <dt className="text-xs text-gray-500">Notiz</dt>
              <dd className="text-gray-700 whitespace-pre-wrap">{vertrag.notiz}</dd>
            </div>
          )}
        </dl>
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 px-4 pt-4 pb-2">
          <p className="font-semibold text-gray-800 text-sm">
            Raten <span className="font-normal text-gray-500">— wiederkehrende Buchungen am Vertrag</span>
          </p>
          {rateWaehlen ? (
            <div className="flex items-center gap-2">
              <select className="input input-sm" defaultValue="" onChange={e => e.target.value && rateAnhaengen(Number(e.target.value))}>
                <option value="">Vorlage wählen…</option>
                {freieRaten.map(wb => (
                  <option key={wb.id} value={wb.id}>
                    {wb.empfaenger || 'ohne Empfänger'} · {fmt(wb.betrag)} {RHYTHMUS_LABEL[wb.rhythmus]}
                  </option>
                ))}
              </select>
              <button className="btn btn-secondary btn-sm" onClick={() => setRateWaehlen(false)}>Abbrechen</button>
            </div>
          ) : (
            <button className="text-xs text-blue-600 hover:underline font-medium" onClick={rateWaehlenOeffnen}>
              Vorhandene Vorlage anhängen
            </button>
          )}
        </div>
        {raten.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-gray-500">
            Keine Rate. Der Vertrag zeigt dann nur die Ist-Spalte – richtig, wenn die Kosten jedes Jahr anders ausfallen.
          </p>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Empfänger</th>
                <th className="px-4 py-2 text-left">Rhythmus</th>
                <th className="px-4 py-2 text-right">Betrag</th>
                <th className="px-4 py-2 text-left">Start</th>
                <th className="px-4 py-2 text-center">Aktiv</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {raten.map(r => (
                <tr key={r.id} className={r.aktiv ? '' : 'opacity-50'}>
                  <td className="px-4 py-2 font-medium">{r.empfaenger || '–'}</td>
                  <td className="px-4 py-2 text-gray-600">{RHYTHMUS_LABEL[r.rhythmus]}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt(r.betrag)}</td>
                  <td className="px-4 py-2 text-gray-500">{fmtDatum(r.start_datum)}</td>
                  <td className="px-4 py-2 text-center text-xs">{r.aktiv ? 'ja' : 'nein'}</td>
                  <td className="px-4 py-2 text-right">
                    <button className="text-xs text-gray-500 hover:text-red-600" onClick={() => rateLoesen(r)}>lösen</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="px-4 py-3 text-xs leading-relaxed text-gray-600 border-t">
          Ein Vertrag darf mehrere Raten halten – Strom etwa den monatlichen Abschlag und die Jahresabrechnung.
          Der Betrag wird an der Vorlage geändert; eine Preishistorie führt das Modul nicht.
        </p>
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 px-4 pt-4 pb-2">
          <p className="font-semibold text-gray-800 text-sm">Zahlungen der letzten zwölf Monate</p>
          <p className="text-xs text-gray-600">
            Ist <strong className="tabular-nums">{fmt(Math.abs(vertrag.ist_12monate))}</strong>
            {/* Ohne Rate gibt es kein Soll, und damit auch keine Abweichung -
                die Zahl waere dann nur die Ist-Summe mit umgekehrtem Vorzeichen. */}
            {vertrag.raten_anzahl > 0 && (
              <>
                {' · '}Soll <strong className="tabular-nums">{fmt(Math.abs(vertrag.soll_jahr))}</strong>
                {abweichung < 0.01
                  ? ' — keine Abweichung'
                  : ` — ${fmt(Math.abs(abweichung))} ${
                      Math.abs(vertrag.ist_12monate) > Math.abs(vertrag.soll_jahr) ? 'mehr' : 'weniger'
                    } als geplant`}
              </>
            )}
          </p>
        </div>
        {zahlungen.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-gray-500">
            Noch keine Zahlung zugeordnet. Über die Mandatsreferenz geschieht das beim Import von selbst.
          </p>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Datum</th>
                <th className="px-4 py-2 text-left">Verwendungszweck</th>
                <th className="px-4 py-2 text-right">Betrag</th>
                <th className="px-4 py-2 text-left">Zugeordnet über</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {zahlungen.map(z => (
                <tr key={z.id}>
                  <td className="px-4 py-2 tabular-nums text-gray-600">{fmtDatum(z.datum)}</td>
                  <td className="px-4 py-2 text-gray-700">{z.verwendungszweck || z.empfaenger || '–'}</td>
                  <td className="px-4 py-2 text-right font-mono">{fmt(z.betrag)}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      z.herkunft === 'mandatsreferenz' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {z.herkunft === 'mandatsreferenz' ? 'Mandatsreferenz'
                        : z.herkunft === 'vorlage' ? 'Vorlage' : 'manuell'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3 mb-3">
          <p className="font-semibold text-gray-800 text-sm">Dokumente</p>
          <label className="btn btn-secondary btn-sm cursor-pointer">
            Datei hinzufügen
            <input type="file" className="hidden" accept="image/*,application/pdf" onChange={hochladen} />
          </label>
        </div>
        {dokumente.length === 0 ? (
          <p className="text-sm text-gray-500">
            Police, Nachtrag, Preiserhöhung, Kündigungsschreiben – sie gehören zum Vertrag und nicht zu einer
            einzelnen Zahlung. Die Dateien liegen in derselben Ablage wie Belege und werden mitgesichert.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {dokumente.map(d => (
              <div key={d.id} className="flex items-center gap-2 border rounded-md p-2">
                <a href={belegeApi.dateUrlVertrag(vertrag.id, d.id)} target="_blank" rel="noreferrer"
                   className="flex-1 min-w-0 text-[13px] font-medium truncate" title={d.dateiname}>
                  {d.dateiname}
                </a>
                <button className="text-gray-400 hover:text-red-600 text-lg leading-none"
                        title="Löschen" aria-label="Löschen" onClick={() => dokumentLoeschen(d)}>×</button>
              </div>
            ))}
          </div>
        )}
      </div>
      {dialog}
    </div>
  )
}

// ── Zuordnung offener Zahlungen ─────────────────────────────────────────────
function Zuordnung({ konten, onFertig, onNeuLaden }) {
  const [vorschlaege, setVorschlaege] = useState(null)
  const [index, setIndex] = useState(0)
  const [kontoFilter, setKontoFilter] = useState('')
  const [wahl, setWahl] = useState(null)
  const [merken, setMerken] = useState(true)
  const [rueckwirkend, setRueckwirkend] = useState(true)
  const [fehler, setFehler] = useState('')

  const laden = useCallback(() => {
    setVorschlaege(null)
    vertraegeApi.offeneZuordnungen(kontoFilter ? Number(kontoFilter) : undefined)
      .then(r => { setVorschlaege(r.data); setIndex(0) })
  }, [kontoFilter])

  useEffect(() => { laden() }, [laden])

  const aktuell = vorschlaege?.[index]

  // Vorauswahl nur beim eindeutigen Treffer über die Mandatsreferenz. Bei
  // mehreren Kandidaten wird ein vorausgewählter Vorschlag weggeklickt, und
  // der Fehler fällt erst Monate später in der Auswertung auf.
  useEffect(() => {
    if (!aktuell) return
    setWahl(aktuell.eindeutig ? aktuell.kandidaten[0]?.vertrag_id ?? null : null)
    setMerken(aktuell.referenz_lernbar && !aktuell.eindeutig)
    setRueckwirkend(aktuell.rueckwirkend_anzahl > 0)
    setFehler('')
  }, [aktuell])

  const weiter = () => {
    if (index + 1 < (vorschlaege?.length || 0)) setIndex(index + 1)
    else laden()
  }

  const zuordnen = async () => {
    setFehler('')
    try {
      await vertraegeApi.zuordnen(aktuell.buchung_id, {
        vertrag_id: wahl,
        referenz_merken: merken && aktuell.referenz_lernbar,
        rueckwirkend: rueckwirkend && aktuell.rueckwirkend_anzahl > 0 && !!aktuell.mandatsreferenz,
      })
      onNeuLaden()
      weiter()
    } catch (err) {
      setFehler(err?.response?.data?.detail || 'Zuordnen fehlgeschlagen.')
    }
  }

  return (
    <div className="p-6 max-w-3xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <button className="text-sm text-blue-600 hover:underline" onClick={onFertig}>‹ Alle Verträge</button>
          <h1 className="text-xl font-bold text-gray-900 mt-1">Zahlung einem Vertrag zuordnen</h1>
          <p className="text-sm text-gray-600">
            Gebuchte Zahlungen ohne Vertrag, zu denen ein Vertrag passen könnte
            {vorschlaege?.length ? ` · ${index + 1} von ${vorschlaege.length}` : ''}
          </p>
        </div>
        <div>
          <label className="label">Konto</label>
          <select className="input" value={kontoFilter} onChange={e => setKontoFilter(e.target.value)}>
            <option value="">Alle</option>
            {konten.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
          </select>
        </div>
      </div>

      {vorschlaege === null && <p className="text-gray-400">Lade…</p>}

      {vorschlaege && !aktuell && (
        <div className="card p-6 text-center text-gray-500">
          Nichts offen. Jede gebuchte Zahlung, zu der ein Vertrag passt, ist zugeordnet.
        </div>
      )}

      {aktuell && (
        <>
          <div className="card p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-2">Die Buchung</p>
            <div className="flex flex-wrap items-baseline gap-4">
              <span className="tabular-nums text-gray-600">{fmtDatum(aktuell.datum)}</span>
              <span className="font-semibold">{aktuell.empfaenger || '–'}</span>
              {aktuell.konto_name && <span className="text-xs text-gray-500">{aktuell.konto_name}</span>}
              <span className="ml-auto font-mono font-semibold text-red-700">{fmt(aktuell.betrag)}</span>
            </div>
            {aktuell.verwendungszweck && <p className="text-[13px] text-gray-600 mt-2">{aktuell.verwendungszweck}</p>}
            <div className="flex flex-wrap gap-2 mt-2">
              {aktuell.mandatsreferenz && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-blue-100 text-blue-800 font-mono">
                  {aktuell.mandatsreferenz}
                </span>
              )}
              {aktuell.mandatsreferenz && !aktuell.referenz_lernbar && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-amber-100 text-amber-800">
                  Referenz nicht lernbar
                </span>
              )}
            </div>
          </div>

          <div className={`rounded-lg border p-4 ${
            aktuell.eindeutig ? 'border-blue-200 bg-blue-50' : 'border-amber-200 bg-amber-50'
          }`}>
            {aktuell.eindeutig ? (
              <p className="text-xs font-medium uppercase tracking-wide text-blue-900 mb-2">Vorschlag</p>
            ) : (
              <p className="text-sm text-amber-900 mb-3">
                {aktuell.kandidaten.length === 1 ? (
                  <>
                    <strong>Ein Vertrag passt</strong> – über Empfänger oder Betrag, und das kann danebengehen.
                    Deshalb wird bestätigt statt stillschweigend zugeordnet.
                  </>
                ) : (
                  <>
                    <strong>Kein Vorschlag.</strong> Es passen {aktuell.kandidaten.length} Verträge, aber kein
                    Merkmal entscheidet. Also wählt die Anwendung nicht, sondern fragt – einmal je Vertrag.
                  </>
                )}
              </p>
            )}

            <fieldset>
              <legend className="sr-only">Zu welchem Vertrag gehört diese Zahlung?</legend>
              <div className="space-y-2">
                {aktuell.kandidaten.map(k => (
                  <label key={k.vertrag_id}
                         className="flex gap-3 items-start bg-white border rounded-md p-3 cursor-pointer">
                    <input type="radio" name="vertrag" className="mt-1"
                           checked={wahl === k.vertrag_id} onChange={() => setWahl(k.vertrag_id)} />
                    <span className="flex-1 min-w-0">
                      <span className="block font-semibold">{k.name}</span>
                      <span className="block text-xs text-gray-500">
                        {[
                          k.anbieter,
                          k.rate != null ? `${fmt(k.rate)} ${RHYTHMUS_LABEL[k.rhythmus] || ''}` : null,
                          k.grund === 'mandatsreferenz' ? 'Mandatsreferenz stimmt'
                            : k.grund === 'empfaenger' ? 'Empfänger stimmt' : 'Betrag und Konto stimmen',
                          k.gelernte_referenz ? 'Referenz bereits gelernt' : 'noch keine Referenz gelernt',
                        ].filter(Boolean).join(' · ')}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="mt-3 space-y-2">
              {aktuell.referenz_lernbar && aktuell.mandatsreferenz ? (
                <label className="flex gap-2 items-start text-sm">
                  <input type="checkbox" className="mt-1" checked={merken} onChange={e => setMerken(e.target.checked)} />
                  <span>
                    Mandatsreferenz am gewählten Vertrag merken
                    <span className="block text-xs text-gray-600">
                      Danach ordnet der Import jede Lastschrift mit <code className="font-mono">{aktuell.mandatsreferenz}</code> ohne
                      Rückfrage zu. Die Referenz ist über alle Verträge eindeutig und kann nicht versehentlich auch am anderen landen.
                    </span>
                  </span>
                </label>
              ) : (
                <p className="text-xs text-gray-600">
                  {aktuell.referenz_sperrgrund || 'Ohne Mandatsreferenz gibt es nichts zu lernen – diese Zahlung wird nur einzeln zugeordnet.'}
                </p>
              )}

              {aktuell.rueckwirkend_anzahl > 0 && (
                <label className="flex gap-2 items-start text-sm">
                  <input type="checkbox" className="mt-1" checked={rueckwirkend} onChange={e => setRueckwirkend(e.target.checked)} />
                  <span>
                    {aktuell.rueckwirkend_anzahl} ältere {aktuell.rueckwirkend_anzahl === 1 ? 'Buchung' : 'Buchungen'} mit derselben Referenz mitnehmen
                    <span className="block text-xs text-gray-600">
                      Damit stimmt die Ist-Spalte auch für die Vergangenheit. Mitgenommen wird nur, was genau
                      diese Referenz trägt – nie etwas nach Empfänger und Betrag.
                    </span>
                  </span>
                </label>
              )}
            </div>

            {fehler && <p className="text-sm text-red-600 mt-2">{fehler}</p>}

            <div className="flex flex-wrap gap-2 mt-3">
              <button className="btn btn-primary btn-sm" disabled={!wahl} onClick={zuordnen}>Zuordnen</button>
              <button className="btn btn-secondary btn-sm" onClick={weiter}>Überspringen</button>
            </div>
          </div>

          <div className="card p-4">
            <p className="font-semibold text-gray-800 text-sm mb-1">Warum gefragt und nicht stillschweigend zugeordnet</p>
            <p className="text-xs leading-relaxed text-gray-600">
              Empfänger und Betrag können danebengehen – zwei Verträge beim gleichen Anbieter sehen gleich aus.
              Die Mandatsreferenz dagegen ist eindeutig; sobald sie am Vertrag steht, läuft es ohne Rückfrage.
              Zieht der Anbieter mehrere Verträge als <em>eine</em> Lastschrift ein, gehört die Buchung zu zwei
              Verträgen – das kann <code className="font-mono">buchungen.vertrag_id</code> nicht abbilden, sie bleibt
              dann besser unzugeordnet.
            </p>
          </div>
        </>
      )}
    </div>
  )
}

// ── Seite ───────────────────────────────────────────────────────────────────
export default function Vertraege() {
  const { confirm, dialog } = useConfirm()
  const [liste, setListe] = useState([])
  const [raten, setRaten] = useState([])
  const [kategorien, setKategorien] = useState([])
  const [konten, setKonten] = useState([])
  const [empfaenger, setEmpfaenger] = useState([])
  const [fahrzeuge, setFahrzeuge] = useState([])
  const [filter, setFilter] = useState('laufend')
  const [neu, setNeu] = useState(false)
  const [detailId, setDetailId] = useState(null)
  const [ansicht, setAnsicht] = useState('liste')   // liste | detail | zuordnung
  const [offenAnzahl, setOffenAnzahl] = useState(0)

  const load = useCallback(async () => {
    const [v, wb] = await Promise.all([vertraegeApi.list(), wiederkehrendApi.list(false)])
    setListe(v.data)
    setRaten(wb.data.filter(r => r.vertrag_id))
  }, [])

  useEffect(() => {
    load()
    kategorienApi.flat().then(r => setKategorien(r.data))
    kontenApi.list().then(r => setKonten(r.data))
    empfaengerApi.list().then(r => setEmpfaenger(r.data))
    fahrzeugeApi.list().then(r => setFahrzeuge(r.data)).catch(() => {})
    vertraegeApi.offeneZuordnungen().then(r => setOffenAnzahl(r.data.length)).catch(() => {})
  }, [load])

  const sichtbar = useMemo(
    () => liste.filter(v => filter === 'alle' || (filter === 'gekuendigt' ? v.gekuendigt_am : !v.gekuendigt_am)),
    [liste, filter],
  )

  const summe = useMemo(() => {
    const laufend = liste.filter(v => !v.gekuendigt_am)
    return {
      laufend: laufend.length,
      gekuendigt: liste.length - laufend.length,
      jahr: laufend.reduce((s, v) => s + (v.soll_jahr || 0), 0),
      fristen: laufend.filter(v => v.tage_bis_kuendigung != null && v.tage_bis_kuendigung <= 60).length,
    }
  }, [liste])

  const anlegen = async data => {
    const r = await vertraegeApi.create(data)
    await load()
    setNeu(false)
    setDetailId(r.data.id)
    setAnsicht('detail')
  }

  const aendern = async (id, data) => {
    await vertraegeApi.update(id, data)
    await load()
  }

  const loeschen = async v => {
    if (!await confirm(
      `Vertrag „${v.name}" löschen? Die zugeordneten Buchungen und Raten bleiben erhalten und verlieren nur `
      + 'die Verknüpfung. Dokumente am Vertrag werden mit gelöscht.'
    )) return
    await vertraegeApi.delete(v.id)
    setAnsicht('liste')
    await load()
  }

  const detail = liste.find(v => v.id === detailId)

  if (ansicht === 'zuordnung') {
    return (
      <>
        <Zuordnung
          konten={konten}
          onFertig={() => { setAnsicht('liste'); vertraegeApi.offeneZuordnungen().then(r => setOffenAnzahl(r.data.length)) }}
          onNeuLaden={load}
        />
        {dialog}
      </>
    )
  }

  if (ansicht === 'detail' && detail) {
    return (
      <>
        <Detail
          vertrag={detail}
          raten={raten.filter(r => r.vertrag_id === detail.id)}
          kategorien={kategorien}
          konten={konten}
          empfaenger={empfaenger}
          fahrzeuge={fahrzeuge}
          onZurueck={() => setAnsicht('liste')}
          onAendern={aendern}
          onNeuLaden={load}
        />
        <div className="px-6 pb-6">
          <button className="btn-danger btn-sm" onClick={() => loeschen(detail)}>Vertrag löschen</button>
        </div>
        {dialog}
      </>
    )
  }

  return (
    <div className="p-6">
      <div className="flex items-end justify-between mb-4 gap-2 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Verträge</h1>
          <p className="text-sm text-gray-600">
            {summe.laufend} laufend · {summe.gekuendigt} gekündigt · {fmt(Math.abs(summe.jahr))} im Jahr
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn btn-secondary btn-sm" onClick={() => setAnsicht('zuordnung')}>
            Zahlungen zuordnen{offenAnzahl ? ` (${offenAnzahl})` : ''}
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setNeu(true)}>+ Neuer Vertrag</button>
        </div>
      </div>

      {summe.fristen > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 mb-4">
          <p className="text-sm font-semibold text-amber-900">
            {summe.fristen === 1
              ? 'Bei einem Vertrag läuft die Kündigungsfrist in den nächsten 60 Tagen ab.'
              : `Bei ${summe.fristen} Verträgen läuft die Kündigungsfrist in den nächsten 60 Tagen ab.`}
          </p>
          <p className="text-xs leading-relaxed text-amber-800 mt-0.5">
            Gerechnet aus Laufzeitende und Frist, nicht gespeichert – der Hinweis verschwindet, wenn der Vertrag
            gekündigt oder das Laufzeitende weitergeschoben ist. Die ganze Art lässt sich in den Einstellungen abschalten.
          </p>
        </div>
      )}

      {neu && (
        <div className="card p-4 mb-4 max-w-4xl">
          <h2 className="font-semibold text-gray-800 mb-3">Neuer Vertrag</h2>
          <p className="text-xs text-gray-500 mb-3">Die Rate kommt danach, als wiederkehrende Buchung.</p>
          <VertragForm
            kategorien={kategorien} konten={konten} empfaenger={empfaenger} fahrzeuge={fahrzeuge}
            onSave={anlegen} onCancel={() => setNeu(false)}
          />
        </div>
      )}

      <div className="flex flex-wrap gap-2 items-center mb-3">
        <div role="group" aria-label="Filter" className="inline-flex rounded-md border overflow-hidden bg-white">
          {[['laufend', 'Laufend'], ['gekuendigt', 'Gekündigt'], ['alle', 'Alle']].map(([id, text]) => (
            <button key={id} type="button" aria-pressed={filter === id} onClick={() => setFilter(id)}
                    className={`px-3 py-1.5 text-[13px] font-medium border-r last:border-r-0 ${
                      filter === id ? 'bg-blue-700 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'
                    }`}>
              {text}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-500">{sichtbar.length === 1 ? '1 Vertrag' : `${sichtbar.length} Verträge`}</span>
      </div>

      <div className="card overflow-hidden">
        {sichtbar.length === 0 ? (
          <div className="p-6 text-center text-gray-400">
            {liste.length === 0
              ? 'Noch keine Verträge. Versicherungen, Strom, Mobilfunk, Abos – alles mit Laufzeit und Frist.'
              : 'Keine Treffer in diesem Filter.'}
          </div>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-2 text-left">Vertrag</th>
                <th className="px-4 py-2 text-left">Kategorie</th>
                <th className="px-4 py-2 text-right">Soll / Jahr</th>
                <th className="px-4 py-2 text-right">Ist 12 Mon.</th>
                <th className="px-4 py-2 text-left">Kündigen bis</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sichtbar.map(v => {
                const t = terminAnsicht(v)
                return (
                  <tr key={v.id} className="odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                    <td className="px-4 py-2">
                      <button className="font-medium text-blue-700 hover:underline text-left"
                              onClick={() => { setDetailId(v.id); setAnsicht('detail') }}>
                        {v.name}
                      </button>
                      <div className="text-xs text-gray-500">{v.anbieter || '–'}</div>
                    </td>
                    <td className="px-4 py-2 text-gray-600">{v.kategorie_name || '–'}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-700">
                      {v.raten_anzahl === 0 ? '–' : fmt(Math.abs(v.soll_jahr))}
                      <div className="text-xs text-gray-500">
                        {v.raten_anzahl === 0 ? 'keine Rate'
                          : v.raten_anzahl === 1 ? '1 Rate' : `${v.raten_anzahl} Raten`}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-gray-700">{fmt(Math.abs(v.ist_12monate))}</td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex text-xs px-2 py-0.5 rounded font-medium tabular-nums ${TERMIN_KLASSE[t.art]}`}>
                        {t.text}
                      </span>
                      <div className="text-xs text-gray-500">{t.zusatz}</div>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten"
                              onClick={() => { setDetailId(v.id); setAnsicht('detail') }}>
                        <PencilIcon />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card p-4 mt-4">
        <p className="font-semibold text-gray-800 text-sm mb-1">Soll und Ist kommen aus zwei Quellen</p>
        <p className="text-xs leading-relaxed text-gray-600">
          <strong>Soll</strong> ist die Summe der wiederkehrenden Buchungen am Vertrag, auf ein Jahr gerechnet –
          Strom hat zwei davon, den monatlichen Abschlag und die Jahresabrechnung.
          <strong> Ist</strong> sind die echten Buchungen der letzten zwölf Monate mit dieser{' '}
          <code className="font-mono">vertrag_id</code>, gleich ob der Generator sie angelegt oder der Import sie
          über die Mandatsreferenz zugeordnet hat. Weicht beides auseinander, steht die Vorlage auf einem alten
          Preis – eine Preishistorie führt das Modul nicht, der Betrag wird an der Vorlage geändert.
        </p>
      </div>
      {dialog}
    </div>
  )
}
