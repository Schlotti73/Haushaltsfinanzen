import { useEffect, useState } from 'react'
import { kategorienApi } from '../api'
import { useAuth } from '../AuthContext'
import { useConfirm } from '../components/useConfirm'
import Modal from '../components/Modal'
import { PencilIcon } from '../components/icons'

const ARTEN = ['ausgabe', 'einnahme', 'beides']

export default function Kategorien() {
  const { confirm, dialog } = useConfirm()
  const { user } = useAuth()
  const [tree, setTree] = useState([])
  const [katForm, setKatForm] = useState(null)
  const isAdmin = user?.rolle === 'admin'

  const load = () => {
    kategorienApi.tree().then((r) => setTree(r.data))
  }
  useEffect(load, [])

  const saveKat = async (e) => {
    e.preventDefault()
    if (katForm.id) await kategorienApi.update(katForm.id, katForm)
    else await kategorienApi.create(katForm)
    setKatForm(null)
    load()
  }

  const delKat = async (id) => {
    if (!await confirm('Kategorie löschen?')) return
    await kategorienApi.delete(id)
    load()
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-bold">Kategorien</h2>

      <div className="max-w-2xl space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Kategorien</h3>
          {isAdmin && (
            <button className="btn-primary btn-sm" onClick={() => setKatForm({ name: '', art: 'ausgabe', uebergeordnet_id: null })}>
              + Neu
            </button>
          )}
        </div>
        <div className="card p-0 divide-y">
          {tree.map((top) => (
            <KatTree key={top.id} k={top} isAdmin={isAdmin} onEdit={setKatForm} onDel={delKat} indent={0} />
          ))}
        </div>
      </div>

      {katForm && (
        <form onSubmit={saveKat}>
          <Modal
            onClose={() => setKatForm(null)}
            title={katForm.id ? 'Kategorie bearbeiten' : 'Neue Kategorie'}
            maxWidth="max-w-sm"
            footer={
              <div className="flex gap-2">
                <button type="submit" className="btn-primary flex-1 justify-center">Speichern</button>
                <button type="button" className="btn-secondary" onClick={() => setKatForm(null)}>Abbrechen</button>
              </div>
            }
          >
            <div><label className="label">Name*</label><input className="input" required autoFocus value={katForm.name} onChange={(e) => setKatForm({ ...katForm, name: e.target.value })} /></div>
            <div>
              <label className="label">Art</label>
              <select className="input" value={katForm.art} onChange={(e) => setKatForm({ ...katForm, art: e.target.value })}>
                {ARTEN.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Übergeordnete Kategorie</label>
              <select className="input" value={katForm.uebergeordnet_id ?? ''} onChange={(e) => setKatForm({ ...katForm, uebergeordnet_id: e.target.value ? parseInt(e.target.value) : null })}>
                <option value="">– keine (Obergruppe) –</option>
                {flachMitEbene(tree)
                  .filter((o) => o.id !== katForm.id)
                  .map((o) => (
                    <option key={o.id} value={o.id}>{' '.repeat(o.ebene * 3)}{o.name}</option>
                  ))}
              </select>
            </div>
            {katForm.id && (
              <div className="flex items-center gap-2">
                <input type="checkbox" id="aktiv" checked={katForm.aktiv ?? true} onChange={(e) => setKatForm({ ...katForm, aktiv: e.target.checked })} />
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

// Baum flach + mit Ebene (für den Übergeordnet-Dropdown, beliebige Tiefe)
function flachMitEbene(nodes, ebene = 0, acc = []) {
  for (const n of nodes) {
    acc.push({ id: n.id, name: n.name, ebene })
    if (n.kinder?.length) flachMitEbene(n.kinder, ebene + 1, acc)
  }
  return acc
}

// Rekursives Rendern beliebig tiefer Kategoriebäume
function KatTree({ k, isAdmin, onEdit, onDel, indent }) {
  return (
    <>
      <KatRow k={k} isAdmin={isAdmin} onEdit={onEdit} onDel={onDel} indent={indent} />
      {k.kinder?.map((kind) => (
        <KatTree key={kind.id} k={kind} isAdmin={isAdmin} onEdit={onEdit} onDel={onDel} indent={indent + 1} />
      ))}
    </>
  )
}

function KatRow({ k, isAdmin, onEdit, onDel, indent }) {
  return (
    <div
      className="flex items-center justify-between px-3 py-2 hover:bg-gray-50"
      style={indent ? { paddingLeft: `${0.75 + indent * 1.25}rem` } : undefined}
    >
      <div className="flex items-center gap-2">
        {indent > 0 && <span className="text-gray-300">·</span>}
        <span className={indent === 0 ? 'font-medium' : ''}>{k.name}</span>
        <span className={`badge text-xs ${k.art === 'einnahme' ? 'badge-green' : k.art === 'ausgabe' ? 'badge-red' : 'badge-gray'}`}>{k.art}</span>
        {!k.aktiv && <span className="badge badge-gray">inaktiv</span>}
      </div>
      {isAdmin && (
        <div className="flex gap-1">
          <button className="btn-secondary btn-icon" title="Bearbeiten" aria-label="Bearbeiten" onClick={() => onEdit({ ...k })}><PencilIcon /></button>
          <button className="btn-danger btn-icon" title="Löschen" aria-label="Löschen" onClick={() => onDel(k.id)}>×</button>
        </div>
      )}
    </div>
  )
}
