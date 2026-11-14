import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Buchungen from './pages/Buchungen'
import Konten from './pages/Konten'
import Kategorien from './pages/Kategorien'
import Projekte from './pages/Projekte'
import Gebaeude from './pages/Gebaeude'
import Benutzer from './pages/Benutzer'
import Statistik from './pages/Statistik'
import Liquiditaet from './pages/Liquiditaet'
import Wiederkehrend from './pages/Wiederkehrend'
import Haushaltsbuch from './pages/Haushaltsbuch'
import Geschaefte from './pages/Geschaefte'
import Empfaenger from './pages/Empfaenger'
import Import from './pages/Import'
import Einstellungen from './pages/Einstellungen'
import Hilfe from './pages/Hilfe'

function RequireAuth({ children }) {
  const { user } = useAuth()
  if (user === undefined) return <div className="flex items-center justify-center h-screen text-gray-400">Lade…</div>
  if (user === null) return <Navigate to="/login" replace />
  return children
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={<RequireAuth><Layout /></RequireAuth>}
      >
        <Route index element={<Dashboard />} />
        <Route path="buchungen" element={<Buchungen />} />
        <Route path="haushaltsbuch" element={<Haushaltsbuch />} />
        <Route path="geschaefte" element={<Geschaefte />} />
        <Route path="wiederkehrend" element={<Wiederkehrend />} />
        <Route path="statistik" element={<Statistik />} />
        <Route path="liquiditaet" element={<Liquiditaet />} />
        <Route path="konten" element={<Konten />} />
        <Route path="kategorien" element={<Kategorien />} />
        <Route path="projekte" element={<Projekte />} />
        <Route path="gebaeude" element={<Gebaeude />} />
        <Route path="benutzer" element={<Benutzer />} />
        <Route path="empfaenger" element={<Empfaenger />} />
        <Route path="import" element={<Import />} />
        <Route path="einstellungen" element={<Einstellungen />} />
        <Route path="hilfe" element={<Hilfe />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
