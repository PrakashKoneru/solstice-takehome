'use client'

import { useState } from 'react'
import Link from 'next/link'

type Session = {
  id: number
  title: string
  created_at: string
}

type Message = {
  role: 'user' | 'assistant'
  content: string
}

type ViewMode = 'preview' | 'edit'

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
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSession, setActiveSession] = useState<Session | null>(null)

  // Chat state
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [currentHtml, setCurrentHtml] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('preview')
  const [editContent, setEditContent] = useState('')

  function handleNewSession() {
    const newSession: Session = {
      id: Date.now(),
      title: 'New Session',
      created_at: new Date().toISOString().split('T')[0],
    }
    setSessions((prev) => [newSession, ...prev])
    setActiveSession(newSession)
    setMessages([])
    setCurrentHtml('')
    setEditContent('')
  }

  function handleSelectSession(session: Session) {
    setActiveSession(session)
    setMessages([])
    setCurrentHtml('')
    setEditContent('')
  }

  async function handleSend() {
    if (!input.trim() || sending) return
    const userMessage = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])
    setSending(true)

    // TODO: call API
    await new Promise((r) => setTimeout(r, 1500))

    setCurrentHtml('')
    setEditContent('')

    // Update session title from first message
    if (messages.length === 0 && activeSession) {
      const newTitle = userMessage.slice(0, 40)
      setActiveSession((s) => s ? { ...s, title: newTitle } : s)
      setSessions((prev) => prev.map((s) => s.id === activeSession.id ? { ...s, title: newTitle } : s))
    }

    setMessages((prev) => [...prev, {
      role: 'assistant',
      content: 'I\'ve generated a slide using your selected knowledge base documents. You can ask me to adjust the layout, emphasis, or tone — or switch to Edit mode for direct changes.',
    }])
    setSending(false)
  }

  return (
    <div className="flex flex-1 overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>

      {/* Left sidebar */}
      <aside className="flex flex-col border-r border-slate-200 bg-white w-64 flex-shrink-0">
        {/* Pinned nav items */}
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
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New session
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {sessions.length === 0 ? (
            <p className="px-4 py-3 text-xs text-slate-400">No sessions yet.</p>
          ) : (
            <ul className="space-y-0.5 px-2">
              {sessions.map((session) => (
                <li key={session.id}>
                  <button
                    onClick={() => handleSelectSession(session)}
                    className={`w-full text-left rounded-lg px-3 py-2 text-sm transition-colors truncate ${
                      activeSession?.id === session.id
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

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">


        {/* Empty state */}
        {!activeSession && (
          <div className="flex flex-1 flex-col items-center justify-center text-center px-8">
            <h2 className="text-2xl font-semibold text-slate-800 mb-2">What are we creating today?</h2>
            <p className="text-slate-400 text-sm mb-6 max-w-sm">Start a new session to generate compliant pharma content from your approved knowledge base.</p>
            <button
              onClick={handleNewSession}
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New session
            </button>
          </div>
        )}

        {/* Active session: chat + preview */}
        {activeSession && (
          <div className="flex flex-1 overflow-hidden">

            {/* Chat panel */}
            <div className="flex flex-col w-full lg:w-2/5 border-r border-slate-200 bg-white overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200">
                <p className="text-sm font-semibold text-slate-900 truncate">{activeSession.title}</p>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                {messages.length === 0 && (
                  <div className="flex flex-col items-center justify-center h-full text-center text-slate-400">
                    <svg className="h-9 w-9 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    <p className="text-sm">Describe what you want to generate.</p>
                    <p className="text-xs mt-1 max-w-xs">e.g. "Create a one-page efficacy slide for oncologists"</p>
                  </div>
                )}
                {messages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-br-sm'
                        : 'bg-slate-100 text-slate-800 rounded-bl-sm'
                    }`}>
                      {msg.content}
                    </div>
                  </div>
                ))}
                {sending && (
                  <div className="flex justify-start">
                    <div className="bg-slate-100 rounded-2xl rounded-bl-sm px-4 py-3">
                      <div className="flex gap-1 items-center">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Input */}
              <div className="px-4 py-3 border-t border-slate-200">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                    placeholder="Ask anything..."
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    disabled={sending}
                  />
                  <button
                    onClick={handleSend}
                    disabled={!input.trim() || sending}
                    className="rounded-lg bg-indigo-600 px-3 py-2 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            {/* Preview / Edit panel */}
            <div className="hidden lg:flex flex-col flex-1 bg-slate-50 overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-700">Output</p>
                <div className="flex items-center gap-2">
                  <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                    <button
                      onClick={() => setViewMode('preview')}
                      className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                        viewMode === 'preview' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      Preview
                    </button>
                    <button
                      onClick={() => { setEditContent(currentHtml); setViewMode('edit') }}
                      className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                        viewMode === 'edit' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      Edit
                    </button>
                  </div>
                  {viewMode === 'edit' && (
                    <button
                      onClick={() => { setCurrentHtml(editContent); setViewMode('preview') }}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors"
                    >
                      Save
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-hidden">
                {!currentHtml ? (
                  <div className="flex flex-col items-center justify-center h-full text-center text-slate-400 px-8">
                    <svg className="h-12 w-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p className="text-sm">Generated content will appear here.</p>
                  </div>
                ) : viewMode === 'preview' ? (
                  <div className="h-full overflow-y-auto p-6">
                    <div
                      className="bg-white rounded-xl shadow-sm min-h-full"
                      dangerouslySetInnerHTML={{ __html: currentHtml }}
                    />
                  </div>
                ) : (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full h-full resize-none p-4 text-xs font-mono text-slate-700 bg-white focus:outline-none"
                  />
                )}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  )
}
