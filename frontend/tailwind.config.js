/** @type {import('tailwindcss').Config} */

// Graustufen und Weiss laufen ueber CSS-Variablen, die in index.css fuer hell
// und dunkel unterschiedlich belegt sind. Dadurch kippt die gesamte App mit
// einer Klasse am <html>, ohne dass an hunderten Stellen dark:-Varianten
// stehen muessen - und neue Seiten sind automatisch dunkeltauglich.
const grau = Object.fromEntries(
  [50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((s) => [s, `var(--grau-${s})`]),
)

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        white: 'var(--flaeche)',
        gray: grau,
      },
    },
  },
  plugins: [],
}
