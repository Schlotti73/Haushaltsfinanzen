import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { useEffect, useState } from 'react'
import { HilfeProvider } from '../HilfeContext'
import HilfePanel from './HilfePanel'
import HilfeKnopf from './HilfeKnopf'
import ThemeSchalter from './ThemeSchalter'
import { systemApi, updateApi } from '../api'

export const navItems = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/buchungen', label: 'Buchungen' },
  { to: '/haushaltsbuch', label: 'Haushaltsbuch' },
  { to: '/geschaefte', label: 'Geschäfte' },
  { to: '/statistik', label: 'Statistik' },
  { to: '/liquiditaet', label: 'Liquidität' },
  { to: '/wiederkehrend', label: 'Wiederkehrend' },
  { to: '/import', label: 'Kontoauszug-Import' },
  { to: '/konten', label: 'Konten' },
  { to: '/kategorien', label: 'Kategorien' },
  { to: '/projekte', label: 'Projekte' },
  { to: '/gebaeude', label: 'Gebäude' },
  { to: '/empfaenger', label: 'Empfänger' },
  { to: '/hilfe', label: 'Hilfe' },
]

function ladeVersteckteModule() {
  try { return JSON.parse(localStorage.getItem('versteckte_module') || '[]') } catch { return [] }
}

const adminItems = [
  { to: '/benutzer', label: 'Benutzer' },
  { to: '/einstellungen', label: 'Einstellungen' },
]

const ALLE_NAV = [...navItems, ...adminItems]

function NavItem({ to, label, end, onClick }) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        `block px-3 py-2 rounded text-sm transition-colors ${
          isActive
            ? 'bg-blue-600 text-white'
            : 'text-gray-300 hover:bg-gray-700 hover:text-white'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [versteckt, setVersteckt] = useState(ladeVersteckteModule)
  const [version, setVersion] = useState('')
  const [neueVersion, setNeueVersion] = useState('')

  // Die Version kommt aus der VERSION-Datei des Pakets, nicht aus dem
  // Frontend-Build: nur so stimmt die Anzeige nach einem Update sofort.
  // Der Update-Hinweis daneben ist bewusst eine zweite, stillschweigend
  // scheiternde Abfrage - ohne hinterlegtes Token oder ohne Netz soll die
  // Versionsanzeige trotzdem stehen.
  useEffect(() => {
    let abgebrochen = false
    systemApi.version()
      .then(r => { if (!abgebrochen) setVersion(r.data?.version || '') })
      .catch(() => {})
    updateApi.status()
      .then(r => { if (!abgebrochen && r.data?.neuer) setNeueVersion(r.data.neuere_version) })
      .catch(() => {})
    return () => { abgebrochen = true }
  }, [])

  useEffect(() => {
    const handler = () => setVersteckt(ladeVersteckteModule())
    window.addEventListener('versteckte_module_geaendert', handler)
    return () => window.removeEventListener('versteckte_module_geaendert', handler)
  }, [])

  useEffect(() => {
    const item = ALLE_NAV.find(n =>
      n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)
    )
    document.title = item ? `${item.label} · Haushaltsfinanzen` : 'Haushaltsfinanzen'
  }, [location.pathname])

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const sidebarContent = (closeOnClick) => (
    <>
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <h1 className="font-bold text-white text-sm leading-tight">Haushalts-<br/>finanzen</h1>
        {closeOnClick && (
          <button
            onClick={() => setMenuOpen(false)}
            className="text-gray-400 hover:text-white p-1 -mr-1"
            aria-label="Menü schließen"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
      <nav className="flex-1 py-2 space-y-0.5 px-2 overflow-y-auto">
        {navItems.filter(item => !versteckt.includes(item.to)).map(item => (
          <NavItem key={item.to} {...item} onClick={closeOnClick ? () => setMenuOpen(false) : undefined} />
        ))}
        {user?.rolle === 'admin' && (
          <>
            <div className="pt-2 pb-1 px-1 text-xs text-gray-500 uppercase tracking-wider">Admin</div>
            {adminItems.map(item => (
              <NavItem key={item.to} {...item} onClick={closeOnClick ? () => setMenuOpen(false) : undefined} />
            ))}
          </>
        )}
      </nav>
      <div className="p-3 border-t border-gray-700 shrink-0">
        <div className="mb-1">
          <div className="text-xs text-gray-400 truncate">{user?.name} ({user?.rolle})</div>
          {version && (
            <div className="text-[11px] text-gray-500 truncate">Version {version}</div>
          )}
          {neueVersion && (
            user?.rolle === 'admin' ? (
              <NavLink
                to="/einstellungen"
                onClick={closeOnClick ? () => setMenuOpen(false) : undefined}
                className="block text-[11px] text-blue-400 hover:text-blue-300 truncate"
              >
                {neueVersion} verfügbar
              </NavLink>
            ) : (
              /* Herunterladen darf nur ein Administrator - fuer alle anderen
                 waere ein Link auf die Einstellungen eine Sackgasse. */
              <div className="text-[11px] text-blue-400 truncate">{neueVersion} verfügbar</div>
            )
          )}
        </div>
        <div className="flex items-center justify-between gap-2">
          <button onClick={handleLogout} className="text-xs text-gray-400 hover:text-white transition-colors">
            Abmelden
          </button>
          <ThemeSchalter />
        </div>
      </div>
    </>
  )

  return (
    <HilfeProvider>
    <div className="flex flex-col md:flex-row h-screen overflow-hidden">
      {/* Mobile Topbar */}
      <header className="navflaeche md:hidden flex items-center justify-between px-3 py-2.5 text-white shrink-0 border-b border-gray-700">
        <button
          onClick={() => setMenuOpen(true)}
          className="p-1.5 -ml-1.5 text-gray-200 hover:text-white"
          aria-label="Menü öffnen"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <span className="font-bold text-sm">Haushaltsfinanzen</span>
        <HilfeKnopf variante="topbar" />
      </header>

      {/* Desktop Sidebar */}
      <aside className="navflaeche hidden md:flex w-44 text-gray-200 flex-col shrink-0">
        {sidebarContent(false)}
      </aside>

      {/* Mobile Drawer */}
      {menuOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="navflaeche relative w-64 max-w-[80vw] text-gray-200 flex flex-col h-full shadow-xl">
            {sidebarContent(true)}
          </aside>
        </div>
      )}

      {/* Hauptbereich */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>

      <HilfeKnopf />
      <HilfePanel />
    </div>
    </HilfeProvider>
  )
}
