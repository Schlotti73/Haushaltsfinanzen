import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', passwort: '', code: '' })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  // Das Codefeld erscheint erst, wenn das Backend es verlangt – im Heimnetz
  // bleibt die Anmeldung damit unverändert
  const [codeNoetig, setCodeNoetig] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await login(form.name, form.passwort, form.code || undefined)
      navigate('/')
    } catch (err) {
      const meldung = err?.response?.data?.detail
      if (meldung === 'MFA-Code erforderlich') {
        setCodeNoetig(true)
        setError('Bitte den Code aus deiner Authenticator-App eingeben.')
      } else if (err?.response?.status === 403) {
        setError(meldung)
      } else if (meldung === 'MFA-Code falsch') {
        setCodeNoetig(true)
        setError('Der Code stimmt nicht.')
      } else {
        setError('Name oder Passwort falsch')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="card w-full max-w-sm">
        <h1 className="text-lg font-bold mb-5 text-center">Haushaltsfinanzen</h1>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">Benutzername</label>
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus required />
          </div>
          <div>
            <label className="label">Passwort</label>
            <input className="input" type="password" value={form.passwort} onChange={(e) => setForm({ ...form, passwort: e.target.value })} required />
          </div>
          {codeNoetig && (
            <div>
              <label className="label">Code aus der Authenticator-App</label>
              <input
                className="input tracking-widest"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                autoFocus
              />
              <p className="text-xs text-gray-400 mt-1">
                Ersatzweise einer deiner Wiederherstellungscodes.
              </p>
            </div>
          )}
          {error && <p className="text-red-600 text-xs">{error}</p>}
          <button className="btn-primary w-full justify-center" type="submit" disabled={loading}>
            {loading ? 'Anmelden…' : 'Anmelden'}
          </button>
        </form>
      </div>
    </div>
  )
}
