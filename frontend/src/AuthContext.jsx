import { createContext, useContext, useEffect, useState } from 'react'
import { authApi } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined) // undefined = noch nicht geprüft

  useEffect(() => {
    authApi.me()
      .then((r) => setUser(r.data))
      .catch(() => setUser(null))
  }, [])

  const login = async (name, passwort, code) => {
    const r = await authApi.login(name, passwort, code)
    setUser(r.data)
    return r.data
  }

  const logout = async () => {
    await authApi.logout()
    setUser(null)
    sessionStorage.removeItem('buchungen_filter')
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
