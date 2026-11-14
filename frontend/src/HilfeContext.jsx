import { createContext, useCallback, useContext, useState } from 'react'

const HilfeContext = createContext(null)

export function HilfeProvider({ children }) {
  const [aktiverAnker, setAktiverAnker] = useState(null)

  const openHilfe = useCallback((anker) => setAktiverAnker(anker), [])
  const closeHilfe = useCallback(() => setAktiverAnker(null), [])

  return (
    <HilfeContext.Provider value={{ aktiverAnker, openHilfe, closeHilfe }}>
      {children}
    </HilfeContext.Provider>
  )
}

export function useHilfe() {
  const ctx = useContext(HilfeContext)
  if (!ctx) throw new Error('useHilfe muss innerhalb von HilfeProvider verwendet werden')
  return ctx
}
