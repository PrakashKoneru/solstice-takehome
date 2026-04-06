'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, type Session } from '@/lib/api'

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

export default function CreatePage() {
  const router = useRouter()
  const [sessions, setSessions] = useState<Session[]>([])
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    api.sessions.list().then(setSessions).catch(console.error)
  }, [])

  async function handleNewSession() {
    setCreating(true)
    try {
      const session = await api.sessions.create('New Session')
      router.push(`/create/${session.id}`)
    } finally {
      setCreating(false)
    }
  }

  async function handleDeleteSession(id: number, e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    await api.sessions.delete(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }

  return (
    <div className="flex flex-col md:flex-row flex-1 overflow-hidden">

      {/* Sidebar */}
      <aside className="hidden md:flex flex-col border-r border-slate-200 bg-white w-64 flex-shrink-0">
        <div className="p-3 space-y-0.5">
          {PINNED_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
            >
              {link.icon}
              {link.label}
            </Link>
          ))}
        </div>

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

        <div className="flex-1 overflow-y-auto py-2">
          {sessions.length === 0 ? (
            <p className="px-4 py-3 text-xs text-slate-400">No sessions yet.</p>
          ) : (
            <ul className="space-y-0.5 px-2">
              {sessions.map((session) => (
                <li key={session.id} className="group relative">
                  <Link
                    href={`/create/${session.id}`}
                    className="block w-full rounded-lg px-3 py-2 pr-8 text-sm text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors truncate"
                  >
                    {session.title}
                  </Link>
                  <button
                    onClick={(e) => handleDeleteSession(session.id, e)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-all"
                    aria-label="Delete session"
                  >
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* Empty state */}
      <div className="flex flex-1 flex-col items-center justify-center text-center px-8">
        <h2 className="text-2xl font-semibold text-slate-800 mb-2">What are we creating today?</h2>
        <p className="text-slate-400 text-sm mb-6 max-w-sm">Start a new session to generate compliant pharma content from your approved knowledge base.</p>
        <button
          onClick={handleNewSession}
          disabled={creating}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {creating ? 'Starting…' : 'New session'}
        </button>
      </div>

    </div>
  )
}
