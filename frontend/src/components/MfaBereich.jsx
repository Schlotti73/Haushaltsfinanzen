import { useEffect, useState } from 'react'
import { authApi } from '../api'

// Einrichtung des zweiten Faktors. Verlangt wird er nur bei Zugriff von
// ausserhalb des Heimnetzes – eingerichtet werden muss er aber vorher, und das
// geht sinnvollerweise von innen.
export default function MfaBereich() {
  const [status, setStatus] = useState(null)
  const [einrichtung, setEinrichtung] = useState(null)   // { qr_svg, secret }
  const [code, setCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState(null)
  const [passwort, setPasswort] = useState('')
  const [fehler, setFehler] = useState(null)

  const laden = () => authApi.mfaStatus().then((r) => setStatus(r.data)).catch(() => setStatus(null))
  useEffect(() => { laden() }, [])

  const starten = async () => {
    setFehler(null)
    const r = await authApi.mfaEinrichten()
    setEinrichtung(r.data)
  }

  const bestaetigen = async () => {
    setFehler(null)
    try {
      const r = await authApi.mfaBestaetigen(code)
      setRecoveryCodes(r.data.recovery_codes)
      setEinrichtung(null)
      setCode('')
      laden()
    } catch (e) {
      setFehler(e?.response?.data?.detail ?? 'Code stimmt nicht')
    }
  }

  const abschalten = async () => {
    setFehler(null)
    try {
      await authApi.mfaDeaktivieren(passwort)
      setPasswort('')
      setRecoveryCodes(null)
      laden()
    } catch (e) {
      setFehler(e?.response?.data?.detail ?? 'Passwort falsch')
    }
  }

  if (!status) return null

  return (
    <div className="card p-5 space-y-3">
      <h3 className="font-semibold text-gray-700">Zwei-Faktor-Anmeldung</h3>
      <p className="text-xs text-gray-400">
        Der Code wird nur verlangt, wenn die Anmeldung nicht aus dem Heimnetz kommt.
        Die Netze stehen in <code>config/server.json</code>.
        {status.aus_heimnetz
          ? ' Dieser Zugriff kommt aus dem Heimnetz.'
          : ' Dieser Zugriff gilt als von außen.'}
      </p>

      {status.aktiv ? (
        <>
          <div className="flex items-center gap-2 text-sm">
            <span className="badge badge-green">aktiv</span>
            <span className="text-gray-500">
              {status.offene_recovery_codes} Wiederherstellungscodes übrig
            </span>
          </div>
          {recoveryCodes && <RecoveryListe codes={recoveryCodes} />}
          <div className="flex items-end gap-2">
            <div>
              <label className="label">Zum Abschalten: eigenes Passwort</label>
              <input className="input" type="password" value={passwort}
                     onChange={(e) => setPasswort(e.target.value)} />
            </div>
            <button className="btn-danger" disabled={!passwort} onClick={abschalten}>Abschalten</button>
          </div>
        </>
      ) : einrichtung ? (
        <div className="space-y-3">
          <p className="text-sm">
            QR-Code in der Authenticator-App scannen oder den Schlüssel abtippen:
          </p>
          <div className="flex flex-wrap items-start gap-4">
            <div
              className="bg-white p-2 rounded border border-gray-200 w-40"
              dangerouslySetInnerHTML={{ __html: einrichtung.qr_svg }}
            />
            <code className="text-xs break-all bg-gray-50 px-2 py-1 rounded">{einrichtung.secret}</code>
          </div>
          <div className="flex items-end gap-2">
            <div>
              <label className="label">Code aus der App</label>
              <input className="input tracking-widest" inputMode="numeric" placeholder="123456"
                     value={code} onChange={(e) => setCode(e.target.value)} />
            </div>
            <button className="btn-primary" disabled={code.length < 6} onClick={bestaetigen}>Bestätigen</button>
            <button className="btn-secondary" onClick={() => setEinrichtung(null)}>Abbrechen</button>
          </div>
          <p className="text-xs text-gray-400">
            Aktiv wird der zweite Faktor erst nach diesem Schritt – so kann niemand ausgesperrt werden.
          </p>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 text-sm">
            <span className="badge badge-gray">nicht eingerichtet</span>
            {status.wird_verlangt && (
              <span className="text-amber-700">
                Für Zugriffe von außen ist er erforderlich.
              </span>
            )}
          </div>
          {recoveryCodes && <RecoveryListe codes={recoveryCodes} />}
          <button className="btn-primary" onClick={starten}>Einrichten</button>
        </>
      )}

      {fehler && <p className="text-red-600 text-xs">{fehler}</p>}
    </div>
  )
}

function RecoveryListe({ codes }) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded p-3 space-y-2">
      <p className="text-sm font-medium">
        Wiederherstellungscodes – jetzt notieren, sie werden nicht wieder angezeigt.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-1 font-mono text-sm">
        {codes.map((c) => <span key={c}>{c}</span>)}
      </div>
      <p className="text-xs text-gray-500">
        Jeder Code funktioniert einmal, falls die App einmal nicht zur Hand ist.
      </p>
    </div>
  )
}
