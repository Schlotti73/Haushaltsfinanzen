// Hell / dunkel / Systemvorgabe. Die Wahl haengt am Browser (localStorage),
// nicht am Benutzerkonto: Handy und Desktop duerfen sich unterscheiden, und es
// gibt kein Aufblitzen, waehrend ein Profil geladen wird.
export const THEME_KEY = 'theme'

export function gespeichertesTheme() {
  try {
    const t = localStorage.getItem(THEME_KEY)
    return t === 'hell' || t === 'dunkel' ? t : 'system'
  } catch {
    return 'system'
  }
}

export function systemIstDunkel() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function wendeThemeAn(theme) {
  const dunkel = theme === 'dunkel' || (theme === 'system' && systemIstDunkel())
  document.documentElement.classList.toggle('dark', dunkel)
  // Faerbt auf dem Handy die Leiste um die App herum mit, sonst bleibt dort
  // ein heller bzw. blauer Streifen stehen
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.content = dunkel ? '#11151d' : '#1d4ed8'
}

export function setzeTheme(theme) {
  try {
    if (theme === 'system') localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, theme)
  } catch { /* privater Modus: dann gilt die Wahl nur fuer diese Sitzung */ }
  wendeThemeAn(theme)
}

// Folgt der Systemvorgabe, solange der Benutzer nichts Festes gewaehlt hat
export function beobachteSystem() {
  const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
  if (!mq) return () => {}
  const handler = () => { if (gespeichertesTheme() === 'system') wendeThemeAn('system') }
  mq.addEventListener('change', handler)
  return () => mq.removeEventListener('change', handler)
}
