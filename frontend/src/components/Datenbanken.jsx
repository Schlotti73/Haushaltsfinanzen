import { useEffect, useState } from 'react'
import { einstellungenApi } from '../api'
import { useConfirm } from './useConfirm'
import Modal from './Modal'

function formatGroesse(bytes) {
  if (bytes == null) return '–'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function Datenbanken() {
  const { confirm, dialog } = useConfirm()
  const [datenbanken, setDatenbanken] = useState([])
  const [laden, setLaden] = useState(true)
  const [meldung, setMeldung] = useState(null) // {typ, text}
  const [neuOffen, setNeuOffen] = useState(false)
  const [neuName, setNeuName] = useState('')
  const [anlegen, setAnlegen] = useState(false)
  const [wechselBestaetigen, setWechselBestaetigen] = useState(null) // id
  const [aktionLaeuft, setAktionLaeuft] = useState(null) // id der DB mit laufender Aktion

  const lade = () => {
    setLaden(true)
    einstellungenApi.dbListe()
      .then(r => setDatenbanken(r.data))
      .catch(() => setMeldung({ typ: 'fehler', text: 'Datenbanken konnten nicht geladen werden.' }))
      .finally(() => setLaden(false))
  }
  useEffect(lade, [])

  const onAnlegen = async () => {
    if (!neuName.trim()) return
    setAnlegen(true); setMeldung(null)
    try {
      await einstellungenApi.dbErstellen(neuName.trim())
      setNeuName(''); setNeuOffen(false)
      lade()
      setMeldung({ typ: 'ok', text: `Datenbank „${neuName.trim()}" angelegt.` })
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Anlegen fehlgeschlagen.' })
    } finally {
      setAnlegen(false)
    }
  }

  const onWechselnBestaetigt = async (db) => {
    setWechselBestaetigen(null)
    setAktionLaeuft(db.id)
    setMeldung(null)
    try {
      const r = await einstellungenApi.dbWechseln(db.id)
      if (r.data.ok) {
        setMeldung({ typ: 'ok', text: r.data.meldung })
        lade()
      } else {
        setMeldung({ typ: 'fehler', text: r.data.meldung })
      }
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Wechseln fehlgeschlagen.' })
    } finally {
      setAktionLaeuft(null)
    }
  }

  const onEntfernen = async (db) => {
    if (!await confirm(`„${db.name}" aus der Liste entfernen? Die Datei bleibt dabei erhalten.`, { knopf: 'Entfernen' })) return
    setAktionLaeuft(db.id)
    try {
      await einstellungenApi.dbEntfernen(db.id)
      lade()
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Entfernen fehlgeschlagen.' })
    } finally {
      setAktionLaeuft(null)
    }
  }

  const onDateiLoeschen = async (db) => {
    if (!await confirm(`„${db.name}" inkl. Datei endgültig löschen? Das kann nicht rückgängig gemacht werden.`)) return
    setAktionLaeuft(db.id)
    try {
      await einstellungenApi.dbDateiLoeschen(db.id)
      lade()
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail ?? 'Löschen fehlgeschlagen.' })
    } finally {
      setAktionLaeuft(null)
    }
  }

  if (laden) return <div className="text-sm text-gray-400">Lade Datenbanken…</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-700">Datenbanken</h3>
          <p className="text-xs text-gray-400 mt-1">
            Zwischen mehreren Datenbanken wechseln oder eine neue, leere Datenbank mit
            generischen Grund-Kategorien anlegen. Vor jedem Wechsel wird automatisch ein
            Backup der bisherigen aktiven Datenbank erstellt. Ein Wechsel wird erst nach
            einem Server-Neustart wirksam.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setNeuOffen(true)}>+ Neue Datenbank</button>
      </div>

      {meldung && (
        <div className={`rounded px-3 py-2 text-sm ${meldung.typ === 'ok' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {meldung.text}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
              <th className="pb-2 font-medium">Name</th>
              <th className="pb-2 font-medium">Datei</th>
              <th className="pb-2 font-medium">Größe</th>
              <th className="pb-2 font-medium">Status</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {datenbanken.map(db => (
              <tr key={db.id} className={wechselBestaetigen === db.id ? 'bg-amber-50' : 'hover:bg-gray-50'}>
                <td className="py-2 pr-4 font-medium">{db.name}</td>
                <td className="py-2 pr-4 font-mono text-xs text-gray-500">{db.dateipfad}</td>
                <td className="py-2 pr-4 text-gray-500">{formatGroesse(db.groesse)}</td>
                <td className="py-2 pr-4">
                  {db.aktiv ? <span className="badge badge-green">aktiv</span> : <span className="badge badge-gray">inaktiv</span>}
                </td>
                <td className="py-2 text-right whitespace-nowrap">
                  {wechselBestaetigen === db.id ? (
                    <span className="inline-flex items-center gap-2 text-xs">
                      <span className="text-amber-800 font-medium">Backup + Wechsel – sicher?</span>
                      <button type="button" className="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-700 text-white font-medium" onClick={() => onWechselnBestaetigt(db)}>
                        Ja, wechseln
                      </button>
                      <button type="button" className="px-2 py-0.5 rounded bg-gray-200 hover:bg-gray-300 text-gray-700" onClick={() => setWechselBestaetigen(null)}>
                        Abbrechen
                      </button>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-3 text-xs">
                      <button
                        type="button"
                        className="text-blue-600 hover:text-blue-800 disabled:text-gray-400"
                        onClick={() => setWechselBestaetigen(db.id)}
                        disabled={db.aktiv || aktionLaeuft !== null}
                      >
                        {aktionLaeuft === db.id ? 'Läuft…' : 'Wechseln zu'}
                      </button>
                      <button
                        type="button"
                        className="text-gray-500 hover:text-gray-700 disabled:text-gray-300"
                        onClick={() => onEntfernen(db)}
                        disabled={db.aktiv || aktionLaeuft !== null}
                      >
                        Aus Liste entfernen
                      </button>
                      <button
                        type="button"
                        className="text-red-600 hover:text-red-800 disabled:text-gray-300"
                        onClick={() => onDateiLoeschen(db)}
                        disabled={db.aktiv || aktionLaeuft !== null}
                      >
                        Datei löschen
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {neuOffen && (
        <Modal
          onClose={() => setNeuOffen(false)}
          title="Neue Datenbank"
          maxWidth="max-w-sm"
          footer={
            <div className="flex gap-2">
              <button className="btn-primary flex-1 justify-center" onClick={onAnlegen} disabled={!neuName.trim() || anlegen}>
                {anlegen ? 'Legt an…' : 'Anlegen'}
              </button>
              <button className="btn-secondary" onClick={() => setNeuOffen(false)}>Abbrechen</button>
            </div>
          }
        >
          <div>
            <label className="label">Name*</label>
            <input className="input w-full" autoFocus value={neuName} onChange={e => setNeuName(e.target.value)} placeholder="z.B. Test 2026" />
            <p className="text-[11px] text-gray-400 mt-1">
              Legt eine neue, leere Datenbank mit generischen Grund-Kategorien an. Wird nur
              der Liste hinzugefügt, nicht automatisch aktiviert. Login in der neuen Datenbank:
              Benutzer „Admin", Passwort „admin123" (nach dem Wechsel bitte ändern).
            </p>
          </div>
        </Modal>
      )}
      {dialog}
    </div>
  )
}
