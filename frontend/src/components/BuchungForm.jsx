import { useState, useEffect, useRef } from 'react'
import { buchungenApi, empfaengerApi, haushaltsbuchApi } from '../api'
import { useHilfe } from '../HilfeContext'
import KategorieSelect from './KategorieSelect'
import CurrencyInput from './CurrencyInput'
import Modal from './Modal'
import ImportRegelForm from './ImportRegelForm'
import { auswaehlbareKonten } from '../kontoAuswahl'


function fmtBetrag(n) {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(n)
}

export default function BuchungForm({ initial, konten, kategorien, projekte, onSave, onClose }) {
  const { openHilfe } = useHilfe()
  const [empfaengerList, setEmpfaengerList] = useState([])
  const [notizList, setNotizList] = useState([])
  const [regelForm, setRegelForm] = useState(null)   // Vorbelegung der Inline-Regelanlage
  const [empfaengerVorschlaege, setEmpfaengerVorschlaege] = useState([])
  const [showVorschlaege, setShowVorschlaege] = useState(false)
  const vorschlaegeRef = useRef(null)

  // Phase 8.5.2: nach Anlegen einer neuen Ausgaben-Buchung prüfen, ob ein
  // offener Haushaltsbuch-Eintrag dazu passt (statt direkt zu schließen)
  const [matchBuchungId, setMatchBuchungId] = useState(null)
  const [matchKandidaten, setMatchKandidaten] = useState([])
  const [verknuepfenLaden, setVerknuepfenLaden] = useState(null)
  const [empfAnlegen, setEmpfAnlegen] = useState(false)
  const [showVZ, setShowVZ] = useState(!!(initial?.verwendungszweck || initial?.import_verwendungszweck))

  useEffect(() => {
    buchungenApi.empfaenger().then((r) => setEmpfaengerList(r.data)).catch(() => {})
    // Auswahlliste für die Notiz: definierte Händlernamen aus Import-Regeln und
    // Geschäften plus die bereits vergebenen Notizen.
    buchungenApi.notizVorschlaege().then((r) => setNotizList(r.data)).catch(() => {})
  }, [])

  const handleEmpfaengerChange = async (val) => {
    setF('empfaenger', val)
    if (val.length >= 2) {
      try {
        const r = await empfaengerApi.vorschlaege(val, 8)
        setEmpfaengerVorschlaege(r.data)
        setShowVorschlaege(r.data.length > 0)
      } catch { setShowVorschlaege(false) }
    } else {
      setShowVorschlaege(false)
    }
  }

  // Regel-Anlage aus der Buchung heraus: Vorbelegung aus dem markierten Text,
  // sonst aus dem Rohtext der Bank. Genau hier sieht man den Müll, den die Regel
  // beseitigen soll – ihn erst in die Einstellungen zu kopieren wäre Umweg.
  const oeffneRegelForm = (stufe) => {
    const markiert = (window.getSelection?.().toString() || '').trim()
    const roh = initial?.import_empfaenger || ''
    const vorgabe = markiert || (stufe === 'anbieter'
      ? roh.split(/\s+/).slice(0, 2).join(' ')
      : roh)
    setRegelForm({
      stufe,
      name: vorgabe,
      schluesselwoerter: vorgabe,
      empfaenger_id: stufe === 'anbieter' ? (form.empfaenger_id ?? '') : '',
      kategorie_id: form.kategorie_id ? Number(form.kategorie_id) : null,
    })
  }

  // Die frisch gespeicherte Regel sofort auf die offene Buchung anwenden – so
  // siehst du direkt, ob sie greift, statt den Import erneut laufen zu lassen.
  const wendeRegelAn = (regel) => {
    setForm(f => ({
      ...f,
      empfaenger: regel.empfaenger_name || f.empfaenger,
      empfaenger_id: regel.empfaenger_id ?? f.empfaenger_id,
      kategorie_id: regel.kategorie_id ? String(regel.kategorie_id) : f.kategorie_id,
      notiz: regel.stufe === 'haendler' ? (regel.notiz_text || regel.name) : f.notiz,
    }))
    setRegelForm(null)
    buchungenApi.notizVorschlaege().then((r) => setNotizList(r.data)).catch(() => {})
  }

  const waehleEmpfaenger = (e) => {
    setForm(f => ({
      ...f,
      empfaenger: e.name,
      empfaenger_id: e.id,
      kategorie_id: e.kategorie_id ? String(e.kategorie_id) : f.kategorie_id,
    }))
    setShowVorschlaege(false)
  }

  const [form, setForm] = useState({
    konto_id: initial?.konto_id ?? '',
    datum: initial?.datum ?? new Date().toISOString().slice(0, 10),
    betrag: initial?.betrag ?? '',
    empfaenger: initial?.empfaenger ?? '',
    empfaenger_id: initial?.empfaenger_id ?? null,
    kategorie_id: initial?.kategorie_id ?? '',
    projekt_id: initial?.projekt_id ?? '',
    notiz: initial?.notiz ?? '',
    verwendungszweck: initial?.verwendungszweck || initial?.import_verwendungszweck || '',
    status: initial?.status ?? 'gebucht',
    quelle: initial?.quelle ?? 'manuell',
  })
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const setF = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        ...form,
        betrag: Number(form.betrag),
        konto_id: form.konto_id ? parseInt(form.konto_id) : null,
        kategorie_id: form.kategorie_id ? parseInt(form.kategorie_id) : null,
        projekt_id: form.projekt_id ? parseInt(form.projekt_id) : null,
        empfaenger_id: form.empfaenger_id || null,
      }
      if (initial?.id) {
        const r = await buchungenApi.update(initial.id, payload)
        onSave(r.data)
        return
      }
      const r = await buchungenApi.create(payload)
      const neue = r.data
      if (neue.betrag < 0) {
        try {
          const kr = await haushaltsbuchApi.abgleichKandidaten({
            datum: neue.datum,
            betrag: neue.betrag,
            empfaenger_text: neue.empfaenger,
            empfaenger_id: neue.empfaenger_id,
            verwendungszweck: neue.verwendungszweck ?? neue.import_verwendungszweck,
          })
          if (kr.data.length > 0) {
            setMatchBuchungId(neue.id)
            setMatchKandidaten(kr.data)
            return
          }
        } catch { /* Abgleich ist optional, Speichern ist bereits erfolgt */ }
      }
      onSave()
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const waehleMatch = async (eintragId) => {
    setVerknuepfenLaden(eintragId)
    try {
      await haushaltsbuchApi.verknuepfen(eintragId, matchBuchungId)
    } catch { /* Verknüpfung optional fehlgeschlagen, Buchung bleibt offen verknüpfbar */ }
    setVerknuepfenLaden(null)
    onSave()
  }

  const zeigeMatch = matchKandidaten.length > 0

  return (
    <>
    <form onSubmit={submit}>
      <Modal
        onClose={zeigeMatch ? onSave : onClose}
        title={zeigeMatch ? 'Passender Haushaltsbuch-Eintrag?' : initial?.id ? 'Buchung bearbeiten' : 'Neue Buchung'}
        maxWidth="max-w-lg"
        footer={
          zeigeMatch ? (
            <button type="button" className="btn-secondary w-full justify-center" onClick={onSave}>Überspringen</button>
          ) : (
            <>
              {error && <p className="text-red-600 text-xs">{error}</p>}
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center" disabled={saving}>
                  {saving ? 'Speichert…' : 'Speichern'}
                </button>
                <button type="button" className="btn-secondary" onClick={onClose}>Abbrechen</button>
              </div>
            </>
          )
        }
      >
        {zeigeMatch ? (
          <>
            <p className="text-sm text-gray-600">
              Diese Buchung passt im Betrag/Datum zu folgenden offenen Haushaltsbuch-Einträgen. Verknüpfen ersetzt die Platzhalter-Buchung des Eintrags durch diese Buchung.
            </p>
            <ul className="space-y-1.5">
              {matchKandidaten.map(k => (
                <li key={k.id} className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded px-3 py-2 text-sm">
                  <span>
                    {k.geschaeft?.name || 'Ohne Geschäft'} · {k.datum} · {fmtBetrag(-k.betrag_gesamt)}
                    {k.notiz && <span className="text-gray-400"> · {k.notiz}</span>}
                  </span>
                  <button
                    type="button"
                    className="text-blue-600 hover:underline text-xs disabled:opacity-50"
                    disabled={verknuepfenLaden === k.id}
                    onClick={() => waehleMatch(k.id)}
                  >
                    {verknuepfenLaden === k.id ? 'Verknüpfe…' : 'Verknüpfen'}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="space-y-3">
            {initial?.quelle === 'import' && (
              <div className="rounded-md bg-sky-50 border border-sky-200 px-3 py-2 text-xs text-sky-800 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold">↓ Via Kontoauszug importiert</div>
                  <button
                    type="button"
                    onClick={() => openHilfe('import-regeln')}
                    className="text-sky-700 hover:underline shrink-0"
                  >
                    Hilfe zu Regeln
                  </button>
                </div>

                {/* Originaler Bankempfänger */}
                {initial.import_empfaenger && (
                  <div className="text-sky-700 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span>
                      <span className="font-medium">Bankempfänger: </span>
                      {initial.import_empfaenger}
                      {initial.import_iban && (
                        <span className="ml-1 font-mono text-sky-600">{initial.import_iban}</span>
                      )}
                    </span>
                    <span className="flex gap-1.5">
                      <button
                        type="button"
                        className="px-1.5 py-0.5 rounded bg-sky-200 hover:bg-sky-300 text-sky-900 font-medium"
                        title="Bankempfänger in das Empfänger-Feld übernehmen"
                        onClick={() => {
                          setForm(f => ({ ...f, empfaenger: initial.import_empfaenger, empfaenger_id: null }))
                          setShowVorschlaege(false)
                        }}
                      >
                        ← übernehmen
                      </button>
                      <button
                        type="button"
                        className="px-1.5 py-0.5 rounded bg-sky-200 hover:bg-sky-300 text-sky-900 font-medium disabled:opacity-50"
                        title="Neuen Empfänger-Eintrag aus Bankdaten anlegen und verknüpfen"
                        disabled={empfAnlegen}
                        onClick={async () => {
                          setEmpfAnlegen(true)
                          try {
                            const r = await empfaengerApi.create({
                              name: initial.import_empfaenger,
                              iban: initial.import_iban || null,
                            })
                            setForm(f => ({ ...f, empfaenger: r.data.name, empfaenger_id: r.data.id }))
                          } catch {
                            // Name schon vorhanden → per Match holen
                            try {
                              const m = await empfaengerApi.match(initial.import_empfaenger, initial.import_iban)
                              if (m.data) setForm(f => ({ ...f, empfaenger: m.data.name, empfaenger_id: m.data.id }))
                            } catch { /* ignorieren */ }
                          } finally {
                            setEmpfAnlegen(false)
                          }
                        }}
                      >
                        {empfAnlegen ? '…' : '+ als Empfänger anlegen'}
                      </button>
                      <button
                        type="button"
                        className="px-1.5 py-0.5 rounded bg-sky-200 hover:bg-sky-300 text-sky-900 font-medium"
                        title="Anbieter-Regel anlegen – markierter Text wird als Schlüsselwort übernommen"
                        onClick={() => oeffneRegelForm('anbieter')}
                      >
                        + Anbieter-Regel
                      </button>
                      <button
                        type="button"
                        className="px-1.5 py-0.5 rounded bg-sky-200 hover:bg-sky-300 text-sky-900 font-medium"
                        title="Händler-Regel anlegen – markierter Text wird als Schlüsselwort übernommen"
                        onClick={() => oeffneRegelForm('haendler')}
                      >
                        + Händler-Regel
                      </button>
                    </span>
                  </div>
                )}

                {/* Originaler Verwendungszweck vom Kontoauszug, nur bei Abweichung vom Feld unten */}
                {initial.import_verwendungszweck && form.verwendungszweck !== initial.import_verwendungszweck && (
                  <div className="text-sky-700 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span>
                      <span className="font-medium">Verwendungszweck lt. Kontoauszug: </span>
                      {initial.import_verwendungszweck}
                    </span>
                    <button
                      type="button"
                      className="px-1.5 py-0.5 rounded bg-sky-200 hover:bg-sky-300 text-sky-900 font-medium"
                      title="Verwendungszweck in das Feld übernehmen"
                      onClick={() => {
                        setF('verwendungszweck', initial.import_verwendungszweck)
                        setShowVZ(true)
                      }}
                    >
                      ← übernehmen
                    </button>
                  </div>
                )}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Datum*</label>
                <input className="input" type="date" value={form.datum} onChange={(e) => setF('datum', e.target.value)} required autoFocus />
              </div>
              <div>
                <label className="label">Betrag (€)*</label>
                <CurrencyInput required placeholder="-45,50" value={form.betrag} onChange={(n) => setF('betrag', n ?? '')} />
              </div>
            </div>
            <div className="relative">
              <div className="flex items-center justify-between">
                <label className="label">Empfänger</label>
                <button
                  type="button"
                  onClick={() => setShowVZ(v => !v)}
                  className="text-xs text-blue-600 hover:text-blue-800 mb-1"
                  title={showVZ ? 'Verwendungszweck ausblenden' : 'Verwendungszweck einblenden'}
                >
                  {showVZ ? 'Zweck ▴' : 'Zweck ▾'}
                </button>
              </div>
              <input
                className="input"
                value={form.empfaenger}
                onChange={(e) => handleEmpfaengerChange(e.target.value)}
                onBlur={() => setTimeout(() => setShowVorschlaege(false), 150)}
                autoComplete="off"
                list="empfaenger-list"
              />
              <datalist id="empfaenger-list">
                {empfaengerList.map((e) => <option key={e} value={e} />)}
              </datalist>
              {showVorschlaege && (
                <div ref={vorschlaegeRef} className="absolute z-50 left-0 right-0 bg-white border border-gray-200 rounded-b shadow-lg max-h-48 overflow-y-auto">
                  {empfaengerVorschlaege.map(e => (
                    <button
                      key={e.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-blue-50 text-sm flex items-center justify-between"
                      onMouseDown={() => waehleEmpfaenger(e)}
                    >
                      <span>{e.name}</span>
                      {e.kategorie_id && <span className="text-xs text-gray-400">Kat. vorbelegt</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {showVZ && (
              <div>
                <textarea
                  className="input resize-none"
                  rows={3}
                  value={form.verwendungszweck}
                  onChange={(e) => {
                    setF('verwendungszweck', e.target.value)
                    if (e.target.value.trim()) setShowVZ(true)
                  }}
                  placeholder="z. B. Miete Januar 2026"
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Konto</label>
                <select className="input" value={form.konto_id} onChange={(e) => setF('konto_id', e.target.value)}>
                  <option value="">– kein –</option>
                  {auswaehlbareKonten(konten, form.konto_id).map((k) => (
                    <option key={k.id} value={k.id}>{k.name}{k.aktiv ? '' : ' (inaktiv)'}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Kategorie</label>
                <KategorieSelect
                  kategorien={kategorien}
                  value={form.kategorie_id}
                  onChange={id => setF('kategorie_id', id)}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Projekt</label>
                <select className="input" value={form.projekt_id} onChange={(e) => setF('projekt_id', e.target.value)}>
                  <option value="">– keins –</option>
                  {projekte.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Status</label>
                <select className="input" value={form.status} onChange={(e) => setF('status', e.target.value)}>
                  <option value="gebucht">Gebucht</option>
                  <option value="geplant">Geplant</option>
                </select>
              </div>
            </div>
            <div>
              <label className="label">Notiz</label>
              <input
                className="input"
                value={form.notiz}
                onChange={(e) => setF('notiz', e.target.value)}
                list="notiz-list"
                autoComplete="off"
              />
              {/* Auswahlliste, aber bewusst als datalist: die Notiz bleibt Freitext,
                  ein Sonderfall soll keinen Stammdatensatz erzwingen. */}
              <datalist id="notiz-list">
                {notizList.map((n) => <option key={n} value={n} />)}
              </datalist>
            </div>
          </div>
        )}
      </Modal>
    </form>

    {/* Regel-Anlage aus der Buchung heraus. Bewusst außerhalb des <form> oben:
        verschachtelte Formulare sind ungültiges HTML. */}
    {regelForm && (
      <Modal
        title="Import-Regel anlegen"
        maxWidth="max-w-lg"
        onClose={() => setRegelForm(null)}
      >
        <ImportRegelForm
          initial={regelForm}
          kompakt
          onGespeichert={wendeRegelAn}
          onAbbrechen={() => setRegelForm(null)}
        />
      </Modal>
    )}
    </>
  )
}
