import { useEffect } from 'react'
import { useHilfe } from '../HilfeContext'
import { HILFE_ABSCHNITTE } from '../data/hilfeInhalte'

export default function HilfePanel() {
  const { aktiverAnker, closeHilfe } = useHilfe()
  const abschnitt = HILFE_ABSCHNITTE.find(a => a.id === aktiverAnker)

  useEffect(() => {
    if (!abschnitt) return
    const onKey = (e) => { if (e.key === 'Escape') closeHilfe() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [abschnitt, closeHilfe])

  if (!abschnitt) return null
  const { titel, Inhalt } = abschnitt

  return (
    <div className="fixed inset-0 z-[70] flex items-end md:items-stretch md:justify-end">
      <div className="fixed inset-0 bg-black/40" onClick={closeHilfe} />
      <aside className="relative w-full md:w-[420px] max-w-full bg-white shadow-xl flex flex-col max-h-[80vh] md:max-h-none md:h-full rounded-t-lg md:rounded-none">
        <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
          <h3 className="font-semibold">{titel}</h3>
          <button
            onClick={closeHilfe}
            aria-label="Hilfe schließen"
            className="text-gray-400 hover:text-gray-700 p-1 -mr-1"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="px-4 py-4 space-y-2.5 text-sm text-gray-600 overflow-y-auto">
          <Inhalt />
        </div>
      </aside>
    </div>
  )
}
