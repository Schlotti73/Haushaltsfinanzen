import { useLocation } from 'react-router-dom'
import { useHilfe } from '../HilfeContext'
import { ankerFuerPfad } from '../data/hilfeInhalte'

// Ein Knopf im Rahmen, der die Hilfe zum gerade geoeffneten Bereich zeigt. Die
// Zuordnung Route -> Abschnitt liegt in hilfeInhalte.jsx, damit eine neue Seite
// nur dort eingetragen werden muss und nicht ohne Hilfe bleibt. Die feineren
// "Hilfe dazu"-Links in den Modulen bleiben daneben bestehen: sie treffen eine
// einzelne Funktion, dieser Knopf den ganzen Bereich.
export default function HilfeKnopf({ variante = 'schwebend' }) {
  const { pathname } = useLocation()
  const { openHilfe } = useHilfe()
  const anker = ankerFuerPfad(pathname)

  // Auf der Hilfe-Seite selbst waere das Panel doppelt.
  if (!anker || pathname.startsWith('/hilfe')) {
    return variante === 'topbar' ? <div className="w-9" /> : null
  }

  const gemeinsam = {
    type: 'button',
    onClick: () => openHilfe(anker),
    title: 'Hilfe zu diesem Bereich',
    'aria-label': 'Hilfe zu diesem Bereich',
  }

  if (variante === 'topbar') {
    return (
      <button {...gemeinsam} className="w-9 h-9 flex items-center justify-center text-gray-200 hover:text-white">
        <Fragezeichen />
      </button>
    )
  }

  return (
    <button
      {...gemeinsam}
      className="hidden md:flex fixed bottom-5 right-5 z-40 w-10 h-10 items-center justify-center
                 rounded-full bg-white border shadow text-gray-500 hover:text-blue-600 hover:border-blue-300"
    >
      <Fragezeichen />
    </button>
  )
}

function Fragezeichen() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M8.228 9c.549-1.165 1.875-2 3.272-2 1.933 0 3.5 1.343 3.5 3 0 1.4-.86 2.07-1.75 2.6-.9.54-1.25 1.06-1.25 1.9M12 17h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  )
}
