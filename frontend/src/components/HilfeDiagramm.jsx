import { Fragment } from 'react'

/** Kästchen im Erklär-Diagramm einer Hilfe-Erklärung. */
export function HilfeKasten({ titel, wert, ton = 'grau' }) {
  const toene = {
    grau: 'border-gray-300 bg-white text-gray-700',
    blau: 'border-blue-300 bg-blue-100 text-blue-900',
    gruen: 'border-green-300 bg-green-100 text-green-900',
    gelb: 'border-yellow-300 bg-yellow-50 text-yellow-900',
  }
  return (
    <div className={`rounded border px-2 py-1 leading-tight ${toene[ton]}`}>
      <div className="text-[9px] uppercase tracking-wide opacity-60">{titel}</div>
      <div className="font-medium whitespace-nowrap">{wert}</div>
    </div>
  )
}

/** Pfeil mit optionaler Beschriftung im Erklär-Diagramm. */
export function HilfePfeil({ label }) {
  return (
    <div className="flex flex-col items-center px-0.5 shrink-0">
      {label && <span className="text-[9px] text-blue-600 leading-none mb-0.5">{label}</span>}
      <span className="text-gray-400 leading-none">→</span>
    </div>
  )
}

/**
 * Ein Schritt samt eingehendem Pfeil, als eine untrennbare Einheit.
 * In einer umbrechenden HilfeFlow-Zeile verhindert das, dass ein Pfeil am
 * Zeilenende hängen bleibt, während sein Kästchen in die nächste Zeile rutscht.
 */
export function HilfeSchritt({ label, titel, wert, ton }) {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <HilfePfeil label={label} />
      <HilfeKasten titel={titel} wert={wert} ton={ton} />
    </div>
  )
}

/** Horizontale Ablauf-Zeile aus Kästchen/Schritten/Verzweigungen, umbricht auf Mobil. */
export function HilfeFlow({ children }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap overflow-x-auto py-1">
      {children}
    </div>
  )
}

/**
 * Verzweigung: ein Eingang teilt sich in mehrere mögliche Wege auf.
 * `label`: Beschriftung des eingehenden Pfeils (optional, macht die Verzweigung
 * inklusive Pfeil zu einer untrennbaren Einheit, siehe HilfeSchritt).
 * `optionen`: [{ label?, schritte: [{titel, wert, ton}, ...] }]
 */
export function HilfeVerzweigung({ label, optionen }) {
  const zeilenHoehe = 40
  const hoehe = optionen.length * zeilenHoehe
  const mitte = hoehe / 2

  return (
    <div className="flex items-center gap-1.5 shrink-0">
      {label !== undefined && <HilfePfeil label={label} />}
      <div className="flex items-stretch">
        <svg width="18" height={hoehe} viewBox={`0 0 18 ${hoehe}`} className="text-gray-300 shrink-0">
          {optionen.map((_, i) => (
            <path
              key={i}
              d={`M0 ${mitte} L9 ${mitte} L9 ${i * zeilenHoehe + zeilenHoehe / 2} L18 ${i * zeilenHoehe + zeilenHoehe / 2}`}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            />
          ))}
        </svg>
        <div className="flex flex-col gap-2 justify-center">
          {optionen.map((opt, i) => (
            <div key={i} className="flex items-center gap-1.5">
              {opt.label && <span className="text-[9px] text-blue-600 shrink-0 w-max">{opt.label}</span>}
              <div className="flex items-center gap-1.5">
                {opt.schritte.map((s, j) => (
                  <Fragment key={j}>
                    {j > 0 && <HilfePfeil />}
                    <HilfeKasten {...s} />
                  </Fragment>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
