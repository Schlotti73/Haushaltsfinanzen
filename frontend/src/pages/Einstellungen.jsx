import { useEffect, useState } from 'react'
import { useAuth } from '../AuthContext'
import { useNavigate } from 'react-router-dom'
import { einstellungenApi } from '../api'
import KontoauszugMuster from '../components/KontoauszugMuster'
import KassenzettelMuster from '../components/KassenzettelMuster'
import ImportRegeln from '../components/ImportRegeln'
import Datenbanken from '../components/Datenbanken'
import { navItems } from '../components/Layout'
import { gespeichertesTheme, setzeTheme } from '../theme'
import MfaBereich from '../components/MfaBereich'
import UpdateBereich from '../components/UpdateBereich'
import { ladeBetriebsart } from '../betriebsart'

const DEFAULT = {
  aktiviert: true,
  ziel_ordner: '',
  uhrzeit: '02:00',
  behalten: 30,
  task_name: 'HaushaltsfinanzBackup',
}

// Fallback, bis der Server die gespeicherten Werte geliefert hat – die
// maßgeblichen Defaults stehen in backend/app/services/einstellungen.py.
const ABGLEICH_DEFAULT = { betrag_toleranz: 5, tage_toleranz: 5 }

function formatGroesse(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDatum(name) {
  // YYYY-MM-DD_HH-MM → DD.MM.YYYY HH:MM
  const m = name.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})$/)
  if (!m) return name
  return `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}`
}

export default function Einstellungen() {
  const { user } = useAuth()
  const navigate = useNavigate()
  // Im Container gibt es keine Windows-Aufgabenplanung: das Backup loest ein
  // zweiter Container aus, der dieselbe backup.json liest. Die Uhrzeit wirkt
  // dort also sofort, der Aufgabenname gar nicht - und ein Feld, das nichts
  // bewirkt, ist schlimmer als keines.
  const [art, setArt] = useState('standard')
  useEffect(() => { ladeBetriebsart().then(setArt) }, [])
  const [form, setForm] = useState(DEFAULT)
  const [laden, setLaden] = useState(true)
  const [speichern, setSpeichern] = useState(false)
  const [backupLaeuft, setBackupLaeuft] = useState(false)
  const [meldung, setMeldung] = useState(null) // { typ: 'ok'|'fehler', text }
  const [backups, setBackups] = useState([])
  const [backupsLaden, setBackupsLaden] = useState(false)
  const [restoring, setRestoring] = useState(null)   // name des laufenden Restores
  const [confirm, setConfirm] = useState(null)       // name des zu bestätigenden Backups
  const [theme, setTheme] = useState(gespeichertesTheme)
  const [versteckt, setVersteckt] = useState(() => {
    try { return JSON.parse(localStorage.getItem('versteckte_module') || '[]') } catch { return [] }
  })
  const [abgleich, setAbgleich] = useState(ABGLEICH_DEFAULT)
  const [abgleichSpeichern, setAbgleichSpeichern] = useState(false)
  const [dashboard, setDashboard] = useState({
    finanzsaldo: false, erinnerung_import_tage: 35, erinnerung_vorlauf_monate: 3,
    // Alle Erinnerungen an: scheitert das Laden, soll die Seite nicht den
    // Eindruck erwecken, es sei etwas abgeschaltet.
    erinnerung_ablesungen_an: true, erinnerung_import_an: true,
    erinnerung_vorlauf_an: true, erinnerung_ueberfaellig_an: true,
  })
  const [dashboardSpeichern, setDashboardSpeichern] = useState(false)

  const ladeBackups = () => {
    setBackupsLaden(true)
    einstellungenApi.backupListe()
      .then(r => setBackups(r.data))
      .catch(err => {
        console.error('backupListe Fehler:', err)
        setBackups([])
      })
      .finally(() => setBackupsLaden(false))
  }

  useEffect(() => {
    if (user?.rolle !== 'admin') { navigate('/'); return }
    einstellungenApi.getBackup()
      .then(r => setForm(r.data))
      .catch(() => setMeldung({ typ: 'fehler', text: 'Einstellungen konnten nicht geladen werden.' }))
      .finally(() => setLaden(false))
    einstellungenApi.getImportAbgleich()
      .then(r => setAbgleich(r.data))
      .catch(() => { /* Fallback-Werte bleiben stehen */ })
    einstellungenApi.getDashboard()
      .then(r => setDashboard(r.data))
      .catch(() => { /* Fallback-Werte bleiben stehen */ })
    ladeBackups()
  }, [user])

  const onAbgleichSpeichern = async (e) => {
    e.preventDefault()
    setAbgleichSpeichern(true)
    setMeldung(null)
    try {
      const r = await einstellungenApi.putImportAbgleich({
        betrag_toleranz: Number(abgleich.betrag_toleranz),
        tage_toleranz: Number(abgleich.tage_toleranz),
      })
      setAbgleich(r.data)
      setMeldung({ typ: 'ok', text: 'Abgleich-Toleranzen gespeichert.' })
    } catch {
      setMeldung({ typ: 'fehler', text: 'Fehler beim Speichern der Abgleich-Toleranzen.' })
    } finally {
      setAbgleichSpeichern(false)
    }
  }

  // Kein eigener Speichern-Knopf – Umlegen bzw. Verlassen des Feldes speichert
  // direkt. Immer das ganze Objekt senden: das PUT setzt alle Felder, ein
  // einzelner Wert wuerde die uebrigen auf ihre Vorgabe zuruecksetzen.
  const speichereDashboard = async (aenderung) => {
    setDashboardSpeichern(true)
    setMeldung(null)
    try {
      const r = await einstellungenApi.putDashboard({ ...dashboard, ...aenderung })
      setDashboard(r.data)
    } catch {
      setMeldung({ typ: 'fehler', text: 'Fehler beim Speichern der Dashboard-Einstellung.' })
    } finally {
      setDashboardSpeichern(false)
    }
  }

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  // Speichern und Benachrichtigen stehen bewusst NEBEN setVersteckt und nicht im
  // Updater: React darf einen Updater waehrend des Renderns aufrufen, das Event
  // wuerde dann im Layout mitten im Render State setzen ("Cannot update a
  // component while rendering a different component"). Der Aufruf kommt aus
  // einem onChange, also ist versteckt hier der aktuelle Stand.
  const toggleModul = (to) => {
    const next = versteckt.includes(to) ? versteckt.filter(x => x !== to) : [...versteckt, to]
    setVersteckt(next)
    localStorage.setItem('versteckte_module', JSON.stringify(next))
    window.dispatchEvent(new Event('versteckte_module_geaendert'))
  }

  const onSpeichern = async (e) => {
    e.preventDefault()
    setSpeichern(true)
    setMeldung(null)
    try {
      await einstellungenApi.putBackup(form)
      setMeldung({ typ: 'ok', text: 'Einstellungen gespeichert.' })
    } catch {
      setMeldung({ typ: 'fehler', text: 'Fehler beim Speichern.' })
    } finally {
      setSpeichern(false)
    }
  }

  const onBackupJetzt = async () => {
    setBackupLaeuft(true)
    setMeldung(null)
    try {
      const r = await einstellungenApi.backupJetzt()
      if (r.data.ok) {
        setMeldung({ typ: 'ok', text: `Backup erstellt: ${r.data.meldung}` })
        ladeBackups()
      } else {
        setMeldung({ typ: 'fehler', text: `Backup fehlgeschlagen: ${r.data.meldung}` })
      }
    } catch {
      setMeldung({ typ: 'fehler', text: 'Backup konnte nicht gestartet werden.' })
    } finally {
      setBackupLaeuft(false)
    }
  }

  const onWiederherstellenBestaetigt = async (name, erzwingen = false) => {
    setConfirm(null)
    setRestoring(name)
    setMeldung(null)
    try {
      const r = await einstellungenApi.backupWiederherstellen(name, erzwingen)
      if (r.data.ok) {
        setMeldung({ typ: 'ok', text: r.data.meldung })
      } else {
        setMeldung({ typ: 'fehler', text: `Wiederherstellung fehlgeschlagen: ${r.data.meldung}` })
      }
    } catch {
      setMeldung({ typ: 'fehler', text: 'Wiederherstellung konnte nicht gestartet werden.' })
    } finally {
      setRestoring(null)
    }
  }

  if (laden) return <div className="p-6 text-gray-400">Lade…</div>

  return (
    <div className="p-6 max-w-6xl space-y-6">
      <h2 className="text-xl font-bold">Einstellungen</h2>

      {meldung && (
        <div className={`rounded px-4 py-3 text-sm ${meldung.typ === 'ok' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {meldung.text}
        </div>
      )}

      <MfaBereich />

      <UpdateBereich />

      {/* Darstellung */}
      <div className="card p-5 space-y-3">
        <h3 className="font-semibold text-gray-700">Darstellung</h3>
        <p className="text-xs text-gray-400">
          Gilt nur für diesen Browser – Handy und Rechner dürfen sich unterscheiden.
        </p>
        <div className="flex gap-2 flex-wrap">
          {[['system', 'Systemvorgabe'], ['hell', 'Hell'], ['dunkel', 'Dunkel']].map(([wert, text]) => (
            <button
              key={wert}
              type="button"
              className={theme === wert ? 'btn-primary' : 'btn-secondary'}
              onClick={() => { setTheme(wert); setzeTheme(wert) }}
            >
              {text}
            </button>
          ))}
        </div>
      </div>

      {/* Module in der Navigation. Der Schalter zeigt "sichtbar", gespeichert wird
          weiter die Liste der versteckten Module - ein Schieber, dessen An-Zustand
          "ausgeblendet" bedeutet, liest sich verkehrt. */}
      <div className="card p-5 space-y-4">
        <h3 className="font-semibold text-gray-700">Module in der Navigation</h3>
        <p className="text-xs text-gray-400">Ausgeschaltete Module erscheinen nicht in der Navigation.</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {navItems.filter(item => item.to !== '/').map(item => (
            <label key={item.to} className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                role="switch"
                checked={!versteckt.includes(item.to)}
                onChange={() => toggleModul(item.to)}
                className="schieber"
              />
              <span className="text-sm text-gray-700">{item.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Anzeigeoptionen des Dashboards */}
      <div className="card p-5 space-y-3">
        <h3 className="font-semibold text-gray-700">Dashboard</h3>
        <label className="flex items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            role="switch"
            className="schieber mt-0.5"
            checked={dashboard.finanzsaldo}
            onChange={e => speichereDashboard({ finanzsaldo: e.target.checked })}
            disabled={dashboardSpeichern}
          />
          <span>
            Finanzsaldo (ohne Sachwerte) anzeigen
            <span className="block text-xs text-gray-400">
              Summe aller Konten abzüglich der Restschulden aus Darlehen und Krediten. Sachwerte wie
              Immobilien sind nicht erfasst – bei einem laufenden Baudarlehen ist die Zahl deshalb
              dauerhaft stark negativ.
            </span>
          </span>
        </label>

        <div className="pt-2 border-t border-gray-100">
          <h4 className="text-sm font-medium text-gray-700">Erinnerungen</h4>
          <p className="text-xs text-gray-400 mb-1">
            Worauf das Dashboard hinweist und ab wann. Eine Erinnerung verschwindet von selbst,
            sobald ihre Ursache weg ist – einzeln zurückstellen lässt sie sich nicht, eine ganze
            Art hier abschalten schon. Das gilt dann für alle Benutzer dieser Datenbank.
          </p>
          <div className="divide-y divide-gray-100">
            <ErinnerungsZeile
              label="Konten ohne Kontoauszug-Import"
              an={dashboard.erinnerung_import_an}
              gesperrt={dashboardSpeichern}
              onSchalter={(v) => speichereDashboard({ erinnerung_import_an: v })}
            >
              <InlineZahl
                vorsatz="nach" nachsatz="Tagen"
                wert={dashboard.erinnerung_import_tage}
                min={1} max={365}
                gesperrt={dashboardSpeichern || !dashboard.erinnerung_import_an}
                blass={!dashboard.erinnerung_import_an}
                onFertig={(v) => speichereDashboard({ erinnerung_import_tage: v })}
              />
            </ErinnerungsZeile>
            <ErinnerungsZeile
              label="Wiederkehrende Buchungen ohne genug Vorlauf"
              an={dashboard.erinnerung_vorlauf_an}
              gesperrt={dashboardSpeichern}
              onSchalter={(v) => speichereDashboard({ erinnerung_vorlauf_an: v })}
            >
              <InlineZahl
                vorsatz="weniger als" nachsatz="Monate"
                wert={dashboard.erinnerung_vorlauf_monate}
                min={1} max={24}
                gesperrt={dashboardSpeichern || !dashboard.erinnerung_vorlauf_an}
                blass={!dashboard.erinnerung_vorlauf_an}
                onFertig={(v) => speichereDashboard({ erinnerung_vorlauf_monate: v })}
              />
            </ErinnerungsZeile>
            <ErinnerungsZeile
              label="Überfällige geplante Buchungen"
              hinweis="Termin liegt in der Vergangenheit."
              an={dashboard.erinnerung_ueberfaellig_an}
              gesperrt={dashboardSpeichern}
              onSchalter={(v) => speichereDashboard({ erinnerung_ueberfaellig_an: v })}
            />
            <ErinnerungsZeile
              label="Fehlende Jahresablesungen"
              hinweis="Nur bei erfassten Zählern im Modul Gebäude."
              an={dashboard.erinnerung_ablesungen_an}
              gesperrt={dashboardSpeichern}
              onSchalter={(v) => speichereDashboard({ erinnerung_ablesungen_an: v })}
            />
          </div>
        </div>
      </div>

      {/* Toleranzen für den Abgleich in der Kontoauszug-Import-Vorschau */}
      <form onSubmit={onAbgleichSpeichern} className="card p-5 space-y-4">
        <h3 className="font-semibold text-gray-700">Import-Abgleich</h3>
        <p className="text-xs text-gray-400">
          Wie weit Datum und Betrag abweichen dürfen, damit die Import-Vorschau eine vorhandene
          Buchung als möglichen Treffer anzeigt. Das ist nur ein Hinweis – als „Verdacht" gilt eine
          Zeile weiterhin nur bei exakt gleichem Betrag und höchstens einem Tag Abstand, und
          automatisch verknüpft wird ausschließlich bei exakter Übereinstimmung.
        </p>

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-sm text-gray-700">Betragstoleranz (€)</label>
            <input
              type="number" min="0" max="100" step="0.01"
              value={abgleich.betrag_toleranz}
              onChange={e => setAbgleich(a => ({ ...a, betrag_toleranz: e.target.value }))}
              className="input w-full"
            />
            <p className="text-xs text-gray-400">0 = nur exakt gleiche Beträge. Maximal 100 €.</p>
          </div>

          <div className="space-y-1">
            <label className="text-sm text-gray-700">Datumstoleranz (Tage)</label>
            <input
              type="number" min="0" max="30" step="1"
              value={abgleich.tage_toleranz}
              onChange={e => setAbgleich(a => ({ ...a, tage_toleranz: e.target.value }))}
              className="input w-full"
            />
            <p className="text-xs text-gray-400">
              Gilt auch für die Kandidatenliste in der Vorschau – große Werte machen sie lang und
              die Vorschau langsam. Maximal 30 Tage.
            </p>
          </div>
        </div>

        <button type="submit" className="btn-primary" disabled={abgleichSpeichern}>
          {abgleichSpeichern ? 'Speichere…' : 'Speichern'}
        </button>
      </form>

      {/* Kontoauszug-Muster */}
      <div className="card p-5">
        <KontoauszugMuster />
      </div>

      {/* Import-Regeln (Bankrohtext normalisieren) */}
      <div className="card p-5">
        <ImportRegeln />
      </div>

      {/* Kassenzettel-Muster (Foto-Import) */}
      <div className="card p-5">
        <KassenzettelMuster />
      </div>

      {/* Datenbanken (Mehrfach-DB-Verwaltung) */}
      <div className="card p-5">
        <Datenbanken />
      </div>

      {/* Automatisches Backup */}
      <form onSubmit={onSpeichern} className="card p-5 space-y-5">
        <h3 className="font-semibold text-gray-700">Automatisches Backup</h3>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            role="switch"
            checked={form.aktiviert}
            onChange={e => set('aktiviert', e.target.checked)}
            className="schieber"
          />
          <span className="text-sm">Tägliches Backup aktiviert</span>
        </label>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-600">Uhrzeit</label>
          <input
            type="time"
            value={form.uhrzeit}
            onChange={e => set('uhrzeit', e.target.value)}
            className="input w-36"
            disabled={!form.aktiviert}
          />
          <p className="text-xs text-gray-400">
            {art === 'docker'
              ? 'Der Backup-Container prüft die Einstellung laufend – eine Änderung wirkt ohne Neustart.'
              : 'Windows-Aufgabenplaner – nach Änderung register_backup_task.ps1 erneut ausführen.'}
          </p>
        </div>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-600">Zielordner</label>
          <input
            type="text"
            value={form.ziel_ordner}
            onChange={e => set('ziel_ordner', e.target.value)}
            placeholder={art === 'docker' ? 'leer = /daten/backups' : 'leer = <Projekt>\\backups'}
            className="input w-full"
          />
          {art === 'docker' && (
            <p className="text-xs text-gray-400">
              Pfad im Container. Alles ausserhalb von <code>/daten</code> ist nach dem nächsten
              Update weg – ein Ziel auf einem NAS mountet der Host nach <code>/daten</code>.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-600">Anzahl aufzubewahrender Backups</label>
          <input
            type="number"
            min={1}
            max={365}
            value={form.behalten}
            onChange={e => set('behalten', Number(e.target.value))}
            className="input w-24"
          />
        </div>

        {art !== 'docker' && (
          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-600">Aufgabenname (Aufgabenplaner)</label>
            <input
              type="text"
              value={form.task_name}
              onChange={e => set('task_name', e.target.value)}
              className="input w-full"
            />
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <button type="submit" className="btn-primary" disabled={speichern}>
            {speichern ? 'Speichert…' : 'Speichern'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={onBackupJetzt}
            disabled={backupLaeuft}
          >
            {backupLaeuft ? 'Backup läuft…' : 'Jetzt sichern'}
          </button>
        </div>
      </form>

      {/* Backup-Liste */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-700">Vorhandene Backups</h3>
          <button
            type="button"
            className="btn-secondary text-xs px-3 py-1"
            onClick={ladeBackups}
            disabled={backupsLaden}
          >
            {backupsLaden ? 'Lädt…' : 'Aktualisieren'}
          </button>
        </div>

        {backups.length === 0 ? (
          <p className="text-sm text-gray-400">Keine Backups gefunden.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                  <th className="pb-2 font-medium">Datum</th>
                  <th className="pb-2 font-medium">Datenbank</th>
                  <th className="pb-2 font-medium">Größe</th>
                  <th className="pb-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {backups.map(b => (
                  <tr key={b.name} className={confirm === b.name ? 'bg-amber-50' : 'hover:bg-gray-50'}>
                    <td className="py-2 pr-4 font-mono text-gray-700">{formatDatum(b.name)}</td>
                    <td className="py-2 pr-4 text-gray-500">
                      {b.datenbank_name || <span className="text-gray-400">unbekannt</span>}
                      {b.fremd && (
                        <span className="ml-1.5 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-xs font-medium">
                          fremde DB
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-4 text-gray-500">{formatGroesse(b.db_groesse)}</td>
                    <td className="py-2 text-right">
                      {confirm === b.name ? (
                        <span className="inline-flex items-center gap-2 text-xs">
                          <span className="text-amber-800 font-medium">
                            {b.fremd
                              ? `Backup aus „${b.datenbank_name || 'anderer DB'}“ überschreibt die aktive DB – sicher?`
                              : 'DB wird überschrieben – sicher?'}
                          </span>
                          <button
                            type="button"
                            className="px-2 py-0.5 rounded bg-red-600 hover:bg-red-700 text-white font-medium"
                            onClick={() => onWiederherstellenBestaetigt(b.name, b.fremd)}
                          >
                            {b.fremd ? 'Trotzdem wiederherstellen' : 'Ja, wiederherstellen'}
                          </button>
                          <button
                            type="button"
                            className="px-2 py-0.5 rounded bg-gray-200 hover:bg-gray-300 text-gray-700"
                            onClick={() => setConfirm(null)}
                          >
                            Abbrechen
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400"
                          onClick={() => setConfirm(b.name)}
                          disabled={restoring !== null}
                        >
                          {restoring === b.name ? 'Stellt wieder her…' : 'Wiederherstellen'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// Eine Zeile je Erinnerungsart: Schalter links, Schwelle - falls es eine gibt -
// rechts in derselben Zeile. Das Zahlenfeld steht bewusst NEBEN dem <label> und
// nicht darin: sonst wuerde ein Klick ins Eingabefeld den Schalter umlegen.
function ErinnerungsZeile({ label, hinweis, an, gesperrt, onSchalter, children }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 py-2">
      <label className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer">
        <input
          type="checkbox"
          role="switch"
          className="schieber mt-0.5"
          checked={an}
          disabled={gesperrt}
          onChange={(e) => onSchalter(e.target.checked)}
        />
        <span className={an ? '' : 'text-gray-400'}>
          {label}
          {hinweis && <span className="block text-xs text-gray-400">{hinweis}</span>}
        </span>
      </label>
      {children}
    </div>
  )
}

// Zahlenfeld, das erst beim Verlassen speichert - sonst ginge pro Tastendruck
// eine Anfrage raus. Ausserhalb der Grenzen wird auf den letzten gueltigen
// Wert zurueckgesetzt, damit nicht stumm etwas anderes gespeichert wird.
//
// Bei abgeschalteter Erinnerung bleibt es stehen, nur gesperrt und blass: so
// ist sichtbar, auf welchen Wert das Wiedereinschalten zurueckkehrt, und der
// Block springt beim Umschalten nicht in der Hoehe.
function InlineZahl({ vorsatz, nachsatz, wert, min, max, gesperrt, blass, onFertig }) {
  const [text, setText] = useState(String(wert))

  useEffect(() => { setText(String(wert)) }, [wert])

  const uebernehmen = () => {
    const zahl = Number(text)
    if (!Number.isInteger(zahl) || zahl < min || zahl > max) {
      setText(String(wert))
      return
    }
    if (zahl !== wert) onFertig(zahl)
  }

  return (
    <span className={`flex items-center gap-1.5 text-sm whitespace-nowrap ${
      blass ? 'text-gray-400 opacity-60' : 'text-gray-700'}`}>
      {vorsatz}
      <input
        type="number"
        className="input w-20 py-1"
        value={text}
        min={min}
        max={max}
        disabled={gesperrt}
        onChange={(e) => setText(e.target.value)}
        onBlur={uebernehmen}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
      />
      {nachsatz}
    </span>
  )
}
