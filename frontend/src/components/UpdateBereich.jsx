import { useEffect, useRef, useState } from 'react'
import { updateApi } from '../api'
import { ladeBetriebsart } from '../betriebsart'

// Nur herunterladen, nie installieren: update.ps1 stoppt den Dienst, der diese
// Seite ausliefert, und braucht Adminrechte. Darum endet der Bereich mit dem
// fertigen Befehl zum Kopieren statt mit einem Knopf.
//
// Im Container gibt es kein Paket: das Image traegt das Programm, der Tag ist
// die Version. Dort entfaellt der Download-Knopf, und der Befehl steht sofort
// neben dem Hinweis auf die neue Fassung - er braucht keinen Download, auf den
// er sich beziehen koennte. Den Wortlaut liefert der Server
// (status.update_befehl), damit Oberflaeche und docs/docker.md nicht
// auseinanderlaufen.

function formatGroesse(bytes) {
  if (!bytes) return ''
  const mb = bytes / 1024 / 1024
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`
}

function formatDatum(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('de-DE')
}

export default function UpdateBereich() {
  const [cfg, setCfg] = useState(null)
  const [repo, setRepo] = useState('')
  const [aktiviert, setAktiviert] = useState(true)
  const [token, setToken] = useState('')
  const [stand, setStand] = useState(null)
  const [prueft, setPrueft] = useState(false)
  const [speichert, setSpeichert] = useState(false)
  const [dl, setDl] = useState(null)
  const [meldung, setMeldung] = useState(null)
  const [art, setArt] = useState('standard')
  const timer = useRef(null)

  useEffect(() => { ladeBetriebsart().then(setArt) }, [])

  useEffect(() => {
    updateApi.einstellungen()
      .then(r => { setCfg(r.data); setRepo(r.data.repo); setAktiviert(r.data.aktiviert) })
      .catch(() => setCfg({ repo: '', aktiviert: true, token_hinterlegt: false }))
    updateApi.status().then(r => setStand(r.data)).catch(() => {})
    updateApi.downloadStand().then(r => { if (r.data.status !== 'leer') setDl(r.data) }).catch(() => {})
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [])

  // Waehrend des Downloads den Fortschritt abfragen. Der Browser laedt nichts
  // selbst - das Paket wandert direkt von GitHub in den Datenordner des
  // Servers, auf dem es anschliessend installiert wird.
  const beobachte = () => {
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(async () => {
      try {
        const r = await updateApi.downloadStand()
        setDl(r.data)
        if (r.data.status !== 'laeuft') { clearInterval(timer.current); timer.current = null }
      } catch {
        clearInterval(timer.current); timer.current = null
      }
    }, 1000)
  }

  const speichern = async () => {
    setSpeichert(true); setMeldung(null)
    try {
      // token nur mitschicken, wenn wirklich ein neues eingetippt wurde -
      // sonst wuerde das Speichern der Repo-Angabe das hinterlegte loeschen.
      const r = await updateApi.speichern({ repo, aktiviert, ...(token ? { token } : {}) })
      setCfg(r.data); setToken('')
      setMeldung({ typ: 'ok', text: 'Gespeichert.' })
      const s = await updateApi.status(true)
      setStand(s.data)
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail || 'Speichern fehlgeschlagen.' })
    } finally { setSpeichert(false) }
  }

  const pruefen = async () => {
    setPrueft(true); setMeldung(null)
    try {
      const r = await updateApi.status(true)
      setStand(r.data)
      if (!r.data.fehler && !r.data.neuer) {
        setMeldung({ typ: 'ok', text: 'Die laufende Version ist die neueste.' })
      }
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail || 'Pruefung fehlgeschlagen.' })
    } finally { setPrueft(false) }
  }

  const herunterladen = async () => {
    setMeldung(null)
    try {
      const r = await updateApi.downloadStarten()
      setDl(r.data)
      beobachte()
    } catch (e) {
      setMeldung({ typ: 'fehler', text: e.response?.data?.detail || 'Download konnte nicht starten.' })
    }
  }

  if (!cfg) return null

  const prozent = dl?.gesamt ? Math.round((dl.geladen / dl.gesamt) * 100) : 0

  return (
    <div className="card p-5 space-y-4">
      <h3 className="font-semibold text-gray-700">Programm-Update</h3>

      {meldung && (
        <div className={`rounded px-3 py-2 text-sm ${meldung.typ === 'ok'
          ? 'bg-green-50 text-green-800 border border-green-200'
          : 'bg-red-50 text-red-800 border border-red-200'}`}>
          {meldung.text}
        </div>
      )}

      {/* Stand */}
      <div className="text-sm text-gray-700 space-y-1">
        <div>Laufende Version: <span className="font-medium">{stand?.aktuelle_version || '–'}</span></div>
        {stand?.neuere_version && (
          <div>
            Neuestes Release: <span className="font-medium">{stand.neuere_version}</span>
            {stand.veroeffentlicht_am && <span className="text-gray-400"> · {formatDatum(stand.veroeffentlicht_am)}</span>}
            {stand.release_url && (
              <a href={stand.release_url} target="_blank" rel="noreferrer"
                 className="ml-2 text-xs text-blue-600 hover:text-blue-800">Release ansehen</a>
            )}
          </div>
        )}
      </div>

      {stand?.neuer && (
        <div className="rounded border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900 space-y-2">
          <div>
            Version {stand.neuere_version} ist verfügbar
            {art !== 'docker' && stand.asset_groesse ? ` (${formatGroesse(stand.asset_groesse)})` : ''}.
          </div>
          {art === 'docker' && (
            <>
              <div className="text-xs text-blue-800">
                Einspielen im Ordner mit der <code>compose.yaml</code>. Der Container wird dabei
                kurz gestoppt; ändert sich das Datenbank-Schema, legt der Start vorher eine
                Sicherung in <code>daten/backups</code> an.
              </div>
              <code className="block bg-gray-900 text-gray-100 rounded px-3 py-2 text-xs break-all">
                {stand.update_befehl}
              </code>
            </>
          )}
        </div>
      )}

      {stand?.fehler && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {stand.fehler}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button type="button" className="btn-secondary" onClick={pruefen}
                disabled={prueft || !cfg.repo}>
          {prueft ? 'Prüft…' : 'Jetzt prüfen'}
        </button>
        {stand?.neuer && art !== 'docker' && (
          <button type="button" className="btn-primary" onClick={herunterladen}
                  disabled={dl?.status === 'laeuft'}>
            {dl?.status === 'laeuft' ? 'Lädt…' : 'Paket herunterladen'}
          </button>
        )}
      </div>

      {/* Download */}
      {dl && dl.status !== 'leer' && (
        <div className="text-sm space-y-2">
          {dl.status === 'laeuft' && (
            <>
              <div className="h-2 rounded bg-gray-200 overflow-hidden">
                <div className="h-full bg-blue-600 transition-all" style={{ width: `${prozent}%` }} />
              </div>
              <div className="text-xs text-gray-500">
                {prozent}% – {formatGroesse(dl.geladen)} von {formatGroesse(dl.gesamt)}
              </div>
            </>
          )}
          {dl.status === 'fertig' && (
            <div className="rounded border border-green-200 bg-green-50 px-3 py-2 space-y-2">
              <div className="text-green-900">
                Paket {dl.version} liegt bereit – die Prüfsumme stimmt.
              </div>
              <div className="text-xs text-gray-600 break-all">{dl.pfad}</div>
              {/* Drei Wege, absteigend bequem. Der erzeugte Starter im
                  Programmordner ist der Normalfall. Fehlt er – nach einem
                  Rollback auf eine Fassung von vor dem Starter –, tut es die
                  update.cmd aus dem Paket, auf die man die ZIP zieht; leer
                  doppelklicken darf man sie nicht, sie nähme sonst die
                  laufende Version als Quelle. Die Konsole steht in jedem Fall
                  daneben: für Fernwartung und Fehlersuche bleibt sie der
                  richtige Ort. */}
              <div>
                {dl.starter ? (
                  <>
                    <div className="text-xs text-gray-600 mb-1">
                      Installieren per Doppelklick – die Administratorrechte fragt der Starter
                      selbst ab. Der Dienst wird dabei kurz gestoppt.
                    </div>
                    <code className="block bg-gray-900 text-gray-100 rounded px-3 py-2 text-xs break-all">
                      {dl.starter}
                    </code>
                    <div className="text-xs text-gray-400 mt-2 break-all">
                      Oder in einer Administrator-PowerShell im Ordner <code>scripts\prod</code>:{' '}
                      {dl.befehl}
                    </div>
                  </>
                ) : dl.paket_cmd ? (
                  <>
                    <div className="text-xs text-gray-600 mb-1">
                      Installieren ohne Konsole: die Paketdatei oben auf diese Datei ziehen – die
                      Administratorrechte fragt sie selbst ab. Der Dienst wird dabei kurz gestoppt.
                      Einfaches Doppelklicken genügt hier nicht.
                    </div>
                    <code className="block bg-gray-900 text-gray-100 rounded px-3 py-2 text-xs break-all">
                      {dl.paket_cmd}
                    </code>
                    <div className="text-xs text-gray-400 mt-2 break-all">
                      Oder in einer Administrator-PowerShell im Ordner <code>scripts\prod</code>:{' '}
                      {dl.befehl}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-xs text-gray-600 mb-1">
                      Installieren in einer Administrator-PowerShell im Ordner <code>scripts\prod</code> der
                      Installation. Der Dienst wird dabei kurz gestoppt.
                    </div>
                    <code className="block bg-gray-900 text-gray-100 rounded px-3 py-2 text-xs break-all">
                      {dl.befehl}
                    </code>
                  </>
                )}
              </div>
            </div>
          )}
          {dl.status === 'fehler' && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-red-800">
              {dl.fehler}
            </div>
          )}
        </div>
      )}

      {/* Zugang */}
      <details className="border-t border-gray-200 pt-3">
        <summary className="text-sm text-gray-600 cursor-pointer select-none">
          Herkunft der Pakete
        </summary>
        <div className="mt-3 space-y-3">
          <p className="text-xs text-gray-400">
            Die Pakete liegen in einem eigenen, öffentlichen Repository – die Prüfung kommt
            darum ohne Zugangsdaten aus und kann nicht ablaufen.
          </p>
          <label className="block text-sm text-gray-700">
            Repository
            <input className="input mt-1" value={repo} placeholder="benutzer/projekt"
                   onChange={(e) => setRepo(e.target.value)} />
          </label>
          <label className="block text-sm text-gray-700">
            Token <span className="text-xs text-gray-400">
              {cfg.token_hinterlegt
                ? '(hinterlegt – nur ausfüllen, um es zu ersetzen)'
                : '(nur nötig, falls die Pakete privat liegen)'}
            </span>
            <input className="input mt-1" type="password" value={token} autoComplete="off"
                   placeholder={cfg.token_hinterlegt ? '••••••••' : 'leer lassen'}
                   onChange={(e) => setToken(e.target.value)} />
            <span className="block text-xs text-gray-400 mt-0.5">
              Wird in der Einstellungsdatei des Datenordners abgelegt, niemals in der
              Datenbank, und hier nie wieder angezeigt.
            </span>
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" role="switch" className="schieber"
                   checked={aktiviert} onChange={(e) => setAktiviert(e.target.checked)} />
            Beim Start auf neue Versionen prüfen
          </label>
          <button type="button" className="btn-primary" onClick={speichern} disabled={speichert}>
            {speichert ? 'Speichert…' : 'Speichern'}
          </button>
        </div>
      </details>
    </div>
  )
}
