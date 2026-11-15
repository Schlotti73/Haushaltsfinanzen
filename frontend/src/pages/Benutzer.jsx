import { useEffect, useState } from 'react'
import { authApi } from '../api'
import { useAuth } from '../AuthContext'
import { useNavigate } from 'react-router-dom'
import { useConfirm } from '../components/useConfirm'
import Modal from '../components/Modal'
import { PencilIcon } from '../components/icons'

export default function Benutzer() {
  const { confirm, dialog } = useConfirm()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [form, setForm] = useState(null)

  useEffect(() => {
    if (user?.rolle !== 'admin') { navigate('/'); return }
    authApi.benutzer().then((r) => setUsers(r.data))
  }, [user])

  const load = () => authApi.benutzer().then((r) => setUsers(r.data))

  const save = async (e) => {
    e.preventDefault()
    if (form.id) {
      const payload = { rolle: form.rolle, aktiv: form.aktiv }
      if (form.passwort) payload.passwort = form.passwort
      await authApi.updateBenutzer(form.id, payload)
    } else {
      await authApi.createBenutzer({ name: form.name, passwort: form.passwort, rolle: form.rolle })
    }
    setForm(null)
    load()
  }

  const del = async (id) => {
    if (!await confirm('Benutzer löschen?')) return
    await authApi.deleteBenutzer(id)
    load()
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Benutzerverwaltung</h2>
        <button className="btn-primary" onClick={() => setForm({ name: '', passwort: '', rolle: 'bearbeiter' })}>+ Neu</button>
      </div>

      <div className="card p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b bg-gray-50 uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Rolle</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b odd:bg-white even:bg-gray-50 hover:bg-blue-50">
                <td className="px-3 py-2 font-medium">{u.name}</td>
                <td className="px-3 py-2"><span className={`badge ${u.rolle === 'admin' ? 'badge-blue' : 'badge-gray'}`}>{u.rolle}</span></td>
                <td className="px-3 py-2">{u.aktiv ? <span className="badge badge-green">aktiv</span> : <span className="badge badge-gray">inaktiv</span>}</td>
                <td className="px-3 py-2 whitespace-nowrap text-right">
                  <button className="btn-secondary btn-icon mr-1" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => setForm({ ...u, passwort: '' })}><PencilIcon /></button>
                  {u.id !== user?.id && <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => del(u.id)}>×</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {form && (
        <form onSubmit={save}>
          <Modal
            onClose={() => setForm(null)}
            title={form.id ? 'Benutzer bearbeiten' : 'Neuer Benutzer'}
            maxWidth="max-w-sm"
            footer={
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
                <button type="button" className="btn-secondary" onClick={() => setForm(null)}>Abbrechen</button>
              </div>
            }
          >
            {!form.id && <div><label className="label">Benutzername*</label><input className="input" required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>}
            <div><label className="label">{form.id ? 'Neues Passwort (leer = unverändert)' : 'Passwort*'}</label><input className="input" type="password" required={!form.id} autoFocus={!!form.id} value={form.passwort} onChange={(e) => setForm({ ...form, passwort: e.target.value })} /></div>
            <div>
              <label className="label">Rolle</label>
              <select className="input" value={form.rolle} onChange={(e) => setForm({ ...form, rolle: e.target.value })}>
                <option value="bearbeiter">Bearbeiter</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            {form.id && (
              <div className="flex items-center gap-2">
                <input type="checkbox" role="switch" className="schieber" id="aktiv" checked={form.aktiv ?? true} onChange={(e) => setForm({ ...form, aktiv: e.target.checked })} />
                <label htmlFor="aktiv" className="text-sm">Aktiv</label>
              </div>
            )}
          </Modal>
        </form>
      )}
      {dialog}
    </div>
  )
}
