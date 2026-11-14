import { useState, useCallback } from 'react'

// Rueckfrage mit Ja/Nein. Die Vorgabe ist der haeufigste Fall - Loeschen, rot -,
// deshalb muessen die vielen Loesch-Aufrufe nichts mitgeben. Alles andere nennt
// seine Beschriftung selbst: ein roter "Loeschen"-Knopf unter der Frage
// "9 Buchungen: 1 Feld aendern?" sagt etwas anderes als die Frage darueber.
export function useConfirm() {
  const [state, setState] = useState({ open: false, message: '', knopf: 'Löschen', gefahr: true, resolve: null })

  const confirm = useCallback((message, { knopf = 'Löschen', gefahr = true } = {}) => {
    return new Promise((resolve) => {
      setState({ open: true, message, knopf, gefahr, resolve })
    })
  }, [])

  const handle = (result) => {
    setState((s) => { s.resolve(result); return { ...s, open: false, message: '', resolve: null } })
  }

  const dialog = state.open ? (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70]">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm w-full mx-4">
        <p className="text-gray-800 mb-5">{state.message}</p>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={() => handle(false)}>Abbrechen</button>
          <button className={state.gefahr ? 'btn-danger' : 'btn-primary'} onClick={() => handle(true)}>
            {state.knopf}
          </button>
        </div>
      </div>
    </div>
  ) : null

  return { confirm, dialog }
}
