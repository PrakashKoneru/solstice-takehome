'use client'

import { useState } from 'react'

type KBDocument = {
  id: number
  name: string
  doc_type: string
}

type Message = {
  role: 'user' | 'assistant'
  content: string
}

// Mock KB docs for UI development — will come from API
const MOCK_KB_DOCS: KBDocument[] = [
  { id: 1, name: 'FRUZAQLA Visual Aid 2024', doc_type: 'claims' },
  { id: 2, name: 'FRESCO-2 Study Results', doc_type: 'research' },
  { id: 3, name: 'FRUZAQLA Prescribing Information', doc_type: 'prescribing_info' },
]

type Step = 'setup' | 'chat'
type ViewMode = 'preview' | 'edit'

export default function CreatePage() {
  const [step, setStep] = useState<Step>('setup')

  // Setup state
  const [title, setTitle] = useState('')
  const [selectedKBIds, setSelectedKBIds] = useState<number[]>([])
  const [artifactFile, setArtifactFile] = useState<File | null>(null)
  const [starting, setStarting] = useState(false)

  // Chat state
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [currentHtml, setCurrentHtml] = useState<string>('')
  const [viewMode, setViewMode] = useState<ViewMode>('preview')
  const [editContent, setEditContent] = useState('')

  function toggleKBDoc(id: number) {
    setSelectedKBIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  async function handleStart(e: React.FormEvent) {
    e.preventDefault()
    if (!title) return
    setStarting(true)
    // TODO: create session via API
    await new Promise((r) => setTimeout(r, 500))
    setStarting(false)
    setStep('chat')
  }

  async function handleSend() {
    if (!input.trim() || sending) return
    const userMessage = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])
    setSending(true)

    // TODO: call API — mock response for now
    await new Promise((r) => setTimeout(r, 1500))
    const mockHtml = `<div style="font-family: Arial, sans-serif; padding: 2rem; max-width: 800px; margin: 0 auto;">
  <h1 style="color: #002855; font-size: 2rem; margin-bottom: 1rem;">FRUZAQLA®</h1>
  <h2 style="color: #8C4799; font-size: 1.25rem; margin-bottom: 1.5rem;">fruquintinib</h2>
  <p style="color: #333; line-height: 1.8; margin-bottom: 1rem;">
    FRUZAQLA demonstrated a statistically significant improvement in overall survival compared to placebo plus best supportive care.
  </p>
  <div style="background: #f8f4fc; border-left: 4px solid #8C4799; padding: 1rem; margin: 1.5rem 0; border-radius: 0 8px 8px 0;">
    <strong style="color: #8C4799;">Key Efficacy Data</strong>
    <p style="margin: 0.5rem 0 0; color: #333;">Median OS: 7.4 vs 4.8 months (HR=0.66; P&lt;0.001)</p>
  </div>
  <p style="font-size: 0.75rem; color: #666; border-top: 1px solid #eee; padding-top: 1rem; margin-top: 2rem;">
    <strong>INDICATION:</strong> FRUZAQLA is indicated for the treatment of adult patients with metastatic colorectal cancer (mCRC) who have been previously treated with fluoropyrimidine-, oxaliplatin-, and irinotecan-based chemotherapy.
  </p>
</div>`
    setCurrentHtml(mockHtml)
    setEditContent(mockHtml)
    setMessages((prev) => [...prev, { role: 'assistant', content: 'I\'ve generated a slide based on your selected knowledge base documents. You can continue refining it or switch to Edit mode to make direct changes.' }])
    setSending(false)
  }

  function handleSaveEdit() {
    setCurrentHtml(editContent)
    setViewMode('preview')
  }

  if (step === 'setup') {
    return (
      <div className="max-w-2xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Create Content</h1>
          <p className="mt-1 text-sm text-slate-500">
            Set up your session context, then chat with the AI to generate compliant content.
          </p>
        </div>

        <form onSubmit={handleStart} className="space-y-6">
          {/* Session title */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-semibold text-slate-700">Session Details</h2>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. FRUZAQLA HCP Email — Q3 Campaign"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>
          </div>

          {/* KB doc selection */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-700">Knowledge Base Sources</h2>
              <p className="text-xs text-slate-400 mt-0.5">Select which approved documents the AI can draw from.</p>
            </div>
            {MOCK_KB_DOCS.length === 0 ? (
              <p className="text-sm text-slate-400">No documents in your knowledge base yet. <a href="/knowledge-base" className="text-indigo-600 underline">Upload some first.</a></p>
            ) : (
              <ul className="space-y-2">
                {MOCK_KB_DOCS.map((doc) => (
                  <li key={doc.id}>
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={selectedKBIds.includes(doc.id)}
                        onChange={() => toggleKBDoc(doc.id)}
                        className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-slate-700 group-hover:text-slate-900">{doc.name}</span>
                      <span className="ml-auto text-xs text-slate-400">{doc.doc_type}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Optional artifact upload */}
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-700">Upload Additional Artifact <span className="font-normal text-slate-400">(optional)</span></h2>
              <p className="text-xs text-slate-400 mt-0.5">Upload a session-specific document not in the knowledge base.</p>
            </div>
            <div
              onClick={() => document.getElementById('artifact-input')?.click()}
              className={`flex items-center gap-3 rounded-lg border-2 border-dashed px-4 py-3 cursor-pointer transition-colors ${
                artifactFile ? 'border-green-400 bg-green-50' : 'border-slate-300 hover:border-slate-400 bg-slate-50'
              }`}
            >
              <input
                id="artifact-input"
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => setArtifactFile(e.target.files?.[0] ?? null)}
              />
              <svg className={`h-5 w-5 flex-shrink-0 ${artifactFile ? 'text-green-500' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
              </svg>
              <span className="text-sm text-slate-500 truncate">
                {artifactFile ? artifactFile.name : 'Click to attach a PDF'}
              </span>
            </div>
          </div>

          <button
            type="submit"
            disabled={!title || starting}
            className="w-full rounded-lg bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {starting ? 'Starting session...' : 'Start Session →'}
          </button>
        </form>
      </div>
    )
  }

  // Chat step
  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-8rem)]">
      {/* Left: Chat panel */}
      <div className="flex flex-col w-full lg:w-2/5 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-900">{title}</p>
            <p className="text-xs text-slate-400">{selectedKBIds.length} source{selectedKBIds.length !== 1 ? 's' : ''} selected</p>
          </div>
          <button
            onClick={() => setStep('setup')}
            className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
          >
            ← Back
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center text-slate-400">
              <svg className="h-10 w-10 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="text-sm">Describe the content you want to create.</p>
              <p className="text-xs mt-1">e.g. "Create a one-page slide highlighting FRUZAQLA efficacy data for oncologists"</p>
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
              <div className="bg-slate-100 rounded-2xl rounded-bl-sm px-4 py-2.5">
                <div className="flex gap-1 items-center h-5">
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
              placeholder="Describe what you want to create..."
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              disabled={sending}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || sending}
              className="rounded-lg bg-indigo-600 px-3 py-2 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Right: Preview / Edit panel */}
      <div className="flex flex-col w-full lg:w-3/5 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
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
                onClick={handleSaveEdit}
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
              <p className="text-xs mt-1">Start chatting on the left to generate your first slide.</p>
            </div>
          ) : viewMode === 'preview' ? (
            <div className="h-full overflow-y-auto bg-slate-100 p-4">
              <div
                className="bg-white rounded-lg shadow-sm min-h-full"
                dangerouslySetInnerHTML={{ __html: currentHtml }}
              />
            </div>
          ) : (
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-full resize-none p-4 text-xs font-mono text-slate-700 focus:outline-none"
              placeholder="HTML content will appear here for editing..."
            />
          )}
        </div>
      </div>
    </div>
  )
}
