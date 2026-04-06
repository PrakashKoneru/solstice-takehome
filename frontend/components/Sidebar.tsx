'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState } from 'react'
import { api } from '@/lib/api'

const PINNED_LINKS = [
  {
    href: '/design-system',
    label: 'Design System',
    icon: (
      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
      </svg>
    ),
  },
  {
    href: '/knowledge-base',
    label: 'Knowledge Base',
    icon: (
      <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
]

type Session = {
  id: number
  title: string
}

export default function Sidebar({ sessions, activeSessionId, onNewSession, onSelectSession }: {
  sessions: Session[]
  activeSessionId?: number | null
  onNewSession?: () => void
  onSelectSession?: (id: number) => void
}) {
  const pathname = usePathname()
  const router = useRouter()
  const [creating, setCreating] = useState(false)

  async function handleNewSession() {
    if (onNewSession) { onNewSession(); return }
    setCreating(true)
    try {
      const session = await api.sessions.create('New Session')
      router.push(`/create/${session.id}`)
    } finally {
      setCreating(false)
    }
  }

  return (
    <aside className="hidden md:flex flex-col border-r border-slate-200 bg-white w-64 flex-shrink-0">
      {/* Pinned links */}
      <div className="p-3 space-y-0.5">
        {PINNED_LINKS.map((link) => {
          const active = pathname === link.href
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? 'bg-slate-100 text-slate-900 font-medium'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              {link.icon}
              {link.label}
            </Link>
          )
        })}
      </div>

      {/* New session button */}
      <div className="px-3 pb-2 border-b border-slate-200">
        <button
          onClick={handleNewSession}
          disabled={creating}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-50"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {creating ? 'Starting…' : 'New session'}
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2">
        {sessions.length === 0 ? (
          <p className="px-4 py-3 text-xs text-slate-400">No sessions yet.</p>
        ) : (
          <ul className="space-y-0.5 px-2">
            {sessions.map((session) => (
              <li key={session.id}>
                <button
                  onClick={() => onSelectSession ? onSelectSession(session.id) : router.push(`/create/${session.id}`)}
                  className={`w-full text-left rounded-lg px-3 py-2 text-sm transition-colors truncate ${
                    activeSessionId === session.id
                      ? 'bg-slate-100 text-slate-900 font-medium'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  {session.title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
