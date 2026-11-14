import { Chart as ChartJS } from 'chart.js'

// Chart.js zeichnet Achsenbeschriftung, Gitter und Legende in festen Farben,
// die fuer hellen Untergrund gedacht sind. Hier werden sie an dieselben
// CSS-Variablen gehaengt wie der Rest der App und bei jedem Moduswechsel neu
// gesetzt - vorhandene Diagramme werden dabei aktualisiert.
function cssWert(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function wendeChartThemeAn() {
  ChartJS.defaults.color = cssWert('--grau-500')
  ChartJS.defaults.borderColor = cssWert('--grau-200')
  for (const chart of Object.values(ChartJS.instances)) chart.update('none')
}

export function beobachteChartTheme() {
  wendeChartThemeAn()
  const beobachter = new MutationObserver(wendeChartThemeAn)
  beobachter.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => beobachter.disconnect()
}
