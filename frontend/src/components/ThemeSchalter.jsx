import { useEffect, useState } from 'react'
import { beobachteSystem, gespeichertesTheme, setzeTheme, systemIstDunkel } from '../theme'

const REIHENFOLGE = ['system', 'hell', 'dunkel']
const TITEL = { system: 'Systemvorgabe', hell: 'Heller Modus', dunkel: 'Dunkler Modus' }

// Kleiner Umschalter in der Navigation: ein Klick geht zur naechsten Stufe.
// Die ausfuehrliche Auswahl steht in den Einstellungen.
export default function ThemeSchalter() {
  const [theme, setTheme] = useState(gespeichertesTheme)

  useEffect(() => beobachteSystem(), [])

  const weiter = () => {
    const naechstes = REIHENFOLGE[(REIHENFOLGE.indexOf(theme) + 1) % REIHENFOLGE.length]
    setTheme(naechstes)
    setzeTheme(naechstes)
  }

  const symbol = theme === 'system' ? (systemIstDunkel() ? '◑' : '◐') : theme === 'dunkel' ? '●' : '○'

  return (
    <button
      onClick={weiter}
      title={`${TITEL[theme]} – klicken zum Wechseln`}
      aria-label={TITEL[theme]}
      className="text-sm text-gray-400 hover:text-white transition-colors leading-none"
    >
      {symbol}
    </button>
  )
}
