import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { HILFE_ABSCHNITTE, HILFE_BEREICHE } from '../data/hilfeInhalte'

// Zwei Gruppen: "Bereiche" folgt dem Menue (ein Abschnitt je Menuepunkt),
// "Uebergreifend" sammelt die Ketten, die mehrere Seiten verbinden. Die
// Anker-IDs bleiben dabei unveraendert, damit die "Hilfe dazu"-Links aus den
// Modulen weiter treffen.
const GRUPPEN = [
  { key: 'bereiche', titel: 'Bereiche' },
  { key: 'uebergreifend', titel: 'Übergreifend' },
]

function Abschnitt({ id, titel, offen, onToggle, children }) {
  return (
    <div id={id} className="card p-0 overflow-hidden scroll-mt-4">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        aria-expanded={offen}
        onClick={onToggle}
      >
        <h3 className="font-semibold">{titel}</h3>
        <span className="text-gray-400">{offen ? '−' : '+'}</span>
      </button>
      {offen && (
        <div className="px-4 pb-4 space-y-2.5 text-sm text-gray-600 border-t pt-3">
          {children}
        </div>
      )}
    </div>
  )
}

export default function Hilfe() {
  const location = useLocation()
  const [offen, setOffen] = useState(() =>
    Object.fromEntries(HILFE_ABSCHNITTE.filter(a => a.standardOffen).map(a => [a.id, true]))
  )

  useEffect(() => {
    const anker = location.hash.replace('#', '')
    if (!anker) return
    setOffen(o => ({ ...o, [anker]: true }))
    requestAnimationFrame(() => {
      document.getElementById(anker)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [location.hash])

  const toggle = (id) => setOffen(o => ({ ...o, [id]: !o[id] }))
  const oeffne = (id) => setOffen(o => ({ ...o, [id]: true }))

  // Inhaltsverzeichnis: "Bereiche" kommt aus der Menueliste (auch dort, wo zwei
  // Menuepunkte auf denselben Abschnitt zeigen), "Uebergreifend" aus den
  // Abschnitten selbst.
  const uebergreifend = HILFE_ABSCHNITTE.filter(a => a.gruppe === 'uebergreifend')
  const inhalt = {
    bereiche: HILFE_BEREICHE,
    uebergreifend: uebergreifend.map(a => ({ label: a.titel, anker: a.id })),
  }

  return (
    <div className="p-6 space-y-4 max-w-3xl">
      <h2 className="text-xl font-bold">Hilfe</h2>
      <p className="text-sm text-gray-500">
        Zu jedem Bereich der App ein Abschnitt, dazu die übergreifenden Ketten. Über die Links unten
        springst du direkt zum passenden Abschnitt – auf jeder Seite öffnet der Knopf „?" die Hilfe
        zum gerade geöffneten Bereich.
      </p>

      <nav className="card p-4 space-y-3">
        {GRUPPEN.map(g => (
          <div key={g.key}>
            <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">{g.titel}</div>
            <ul className="space-y-1 text-sm">
              {inhalt[g.key].map((e, i) => (
                <li key={`${e.anker}-${i}`}>
                  <a
                    href={`#${e.anker}`}
                    className="text-blue-600 hover:underline"
                    onClick={() => oeffne(e.anker)}
                  >
                    {e.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {GRUPPEN.map(g => (
        <div key={g.key} className="space-y-4">
          <h3 className="text-xs uppercase tracking-wide text-gray-400 pt-2">{g.titel}</h3>
          {HILFE_ABSCHNITTE.filter(a => a.gruppe === g.key).map(({ id, titel, Inhalt }) => (
            <Abschnitt key={id} id={id} titel={titel} offen={!!offen[id]} onToggle={() => toggle(id)}>
              <Inhalt />
            </Abschnitt>
          ))}
        </div>
      ))}
    </div>
  )
}
