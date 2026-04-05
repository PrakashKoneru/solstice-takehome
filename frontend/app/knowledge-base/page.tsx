'use client'

import { useState } from 'react'

type KBDocument = {
  id: number
  name: string
  filename: string
  doc_type: string
  created_at: string
}

const DOC_TYPES = [
  { value: 'claims', label: 'Approved Claims' },
  { value: 'research', label: 'Research Paper' },
  { value: 'prescribing_info', label: 'Prescribing Information' },
  { value: 'general', label: 'General' },
]

function docTypeBadge(type: string) {
  const map: Record<string, string> = {
    claims: 'bg-purple-50 text-purple-700',
    research: 'bg-blue-50 text-blue-700',
    prescribing_info: 'bg-amber-50 text-amber-700',
    general: 'bg-slate-100 text-slate-600',
  }
  return map[type] ?? map.general
}

export default function KnowledgeBasePage() {
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [docType, setDocType] = useState('general')
  const [loading, setLoading] = useState(false)
  const [docs, setDocs] = useState<KBDocument[]>([])
  const [dragOver, setDragOver] = useState(false)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped?.type === 'application/pdf') setFile(dropped)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file || !name) return
    setLoading(true)
    // TODO: wire to API
    await new Promise((r) => setTimeout(r, 1000))
    setLoading(false)
    setFile(null)
    setName('')
    setDocType('general')
  }

  function handleDelete(id: number) {
    setDocs((prev) => prev.filter((d) => d.id !== id))
    // TODO: wire to API
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Knowledge Base</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload approved source documents. These become the only source of truth the AI can draw from during content generation.
        </p>
      </div>

      {/* Upload form */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">Upload Document</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Document Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. FRUZAQLA Visual Aid 2024"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Document Type</label>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {DOC_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">PDF File</label>
            <div
              onDrop={handleDrop}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onClick={() => document.getElementById('kb-file-input')?.click()}
              className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors ${
                dragOver
                  ? 'border-indigo-400 bg-indigo-50'
                  : file
                  ? 'border-green-400 bg-green-50'
                  : 'border-slate-300 hover:border-slate-400 bg-slate-50'
              }`}
            >
              <input
                id="kb-file-input"
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <svg className="h-8 w-8 text-green-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <p className="text-sm font-medium text-slate-700">{file.name}</p>
                  <p className="text-xs text-slate-400 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
                </>
              ) : (
                <>
                  <svg className="h-8 w-8 text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-sm text-slate-500">Drag & drop a PDF or <span className="text-indigo-600 font-medium">browse</span></p>
                  <p className="text-xs text-slate-400 mt-1">PDF up to 50MB</p>
                </>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={!file || !name || loading}
            className="w-full sm:w-auto rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Uploading...' : 'Upload Document'}
          </button>
        </form>
      </div>

      {/* Document list */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">Documents</h2>
          <span className="text-xs text-slate-400">{docs.length} document{docs.length !== 1 ? 's' : ''}</span>
        </div>

        {docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center px-4">
            <svg className="h-10 w-10 text-slate-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm text-slate-400">No documents yet. Upload your first one above.</p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-200">
            {docs.map((doc) => (
              <li key={doc.id} className="flex items-center justify-between gap-4 px-6 py-4">
                <div className="flex items-center gap-3 min-w-0">
                  <svg className="h-5 w-5 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{doc.name}</p>
                    <p className="text-xs text-slate-400 truncate">{doc.filename}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${docTypeBadge(doc.doc_type)}`}>
                    {DOC_TYPES.find((t) => t.value === doc.doc_type)?.label ?? doc.doc_type}
                  </span>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="text-slate-400 hover:text-red-500 transition-colors"
                    aria-label="Delete document"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
