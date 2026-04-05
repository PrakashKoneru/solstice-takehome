'use client'

import { createContext, useContext, useState } from 'react'

export type Session = {
  id: number
  title: string
}

type SessionContextType = {
  sessions: Session[]
  activeSessionId: number | null
  setSessions: React.Dispatch<React.SetStateAction<Session[]>>
  setActiveSessionId: React.Dispatch<React.SetStateAction<number | null>>
}

const SessionContext = createContext<SessionContextType | null>(null)

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)

  return (
    <SessionContext.Provider value={{ sessions, activeSessionId, setSessions, setActiveSessionId }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}
