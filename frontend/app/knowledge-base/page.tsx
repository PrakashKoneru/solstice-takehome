'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '@/components/Sidebar'
import { api, KnowledgeItem, Claim, type Session } from '@/lib/api'

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

const CLAIM_TYPE_LABELS: Record<string, string> = {
  efficacy: 'Efficacy', safety: 'Safety', dosing: 'Dosing', moa: 'MOA',
  isi: 'ISI', boilerplate: 'Boilerplate', stat: 'Stat',
  study_design: 'Study Design', indication: 'Indication', nccn: 'NCCN',
}

const CLAIM_TYPE_COLORS: Record<string, string> = {
  efficacy: 'bg-green-50 text-green-700',
  safety: 'bg-red-50 text-red-700',
  dosing: 'bg-blue-50 text-blue-700',
  moa: 'bg-purple-50 text-purple-700',
  isi: 'bg-orange-50 text-orange-700',
  boilerplate: 'bg-slate-100 text-slate-600',
  stat: 'bg-teal-50 text-teal-700',
  study_design: 'bg-indigo-50 text-indigo-700',
  indication: 'bg-amber-50 text-amber-700',
  nccn: 'bg-sky-50 text-sky-700',
}

export default function KnowledgeBasePage() {
  const [files, setFiles] = useState<File[]>([])
  const [name, setName] = useState('')
  const [docType, setDocType] = useState('general')
  const [loading, setLoading] = useState(false)
  const [docs, setDocs] = useState<KnowledgeItem[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [sessions, setSessions] = useState<Session[]>([])

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDocType, setEditDocType] = useState('general')
  const [editFile, setEditFile] = useState<File | null>(null)
  const [editLoading, setEditLoading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  // Claims panel state
  const [claimsDocId, setClaimsDocId] = useState<number | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [claimsLoading, setClaimsLoading] = useState(false)
  const [claimsTypeFilter, setClaimsTypeFilter] = useState<string>('')
  const [extractionProgress, setExtractionProgress] = useState<{ claims_so_far: number; total_pages: number } | null>(null)

  useEffect(() => {
    api.knowledge.list().then(setDocs).catch(console.error)
    api.sessions.list().then(setSessions).catch(console.error)
  }, [])

  const loadClaims = useCallback(async (docId: number) => {
    setClaimsLoading(true)
    try {
      const data = await api.knowledge.listClaims(docId)
      setClaims(data)
    } finally {
      setClaimsLoading(false)
    }
  }, [])

  const startExtractionStream = useCallback((docId: number) => {
    const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001'
    const es = new EventSource(`${BASE}/api/knowledge/${docId}/extraction-stream`)
    setClaimsDocId(docId)
    setClaims([])
    setExtractionProgress({ claims_so_far: 0, total_pages: 0 })

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      setExtractionProgress({ claims_so_far: data.claims_so_far, total_pages: data.total_pages })
    })

    es.addEventListener('claims', (e) => {
      const newClaims: Claim[] = JSON.parse(e.data)
      setClaims((prev) => {
        const existingIds = new Set(prev.map((c) => c.id))
        const unique = newClaims.filter((c) => !existingIds.has(c.id))
        return [...prev, ...unique]
      })
    })

    es.addEventListener('done', (e) => {
      const data = JSON.parse(e.data)
      es.close()
      setExtractionProgress(null)
      setDocs((prev) => prev.map((d) => d.id === docId
        ? { ...d, extraction_status: data.status as KnowledgeItem['extraction_status'], claim_count: data.total_claims }
        : d
      ))
    })

    es.addEventListener('error', () => {
      es.close()
      setExtractionProgress(null)
    })

    return es
  }, [])

  async function toggleApproval(docId: number, claim: Claim) {
    const updated = await api.knowledge.updateClaim(docId, claim.id, { is_approved: !claim.is_approved })
    setClaims((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
    // Update claim_count on the doc
    setDocs((prev) => prev.map((d) => {
      if (d.id !== docId) return d
      const delta = updated.is_approved ? 1 : -1
      return { ...d, claim_count: Math.max(0, (d.claim_count ?? 0) + delta) }
    }))
  }

  async function handleDeleteClaim(docId: number, claimId: string) {
    await api.knowledge.deleteClaim(docId, claimId)
    setClaims((prev) => prev.filter((c) => c.id !== claimId))
    setDocs((prev) => prev.map((d) => d.id === docId ? { ...d, claim_count: Math.max(0, (d.claim_count ?? 1) - 1) } : d))
  }

  const isMulti = files.length > 1

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const dropped = Array.from(e.dataTransfer.files).filter((f) => f.type === 'application/pdf')
    if (dropped.length) setFiles(dropped)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!files.length || (!isMulti && !name)) return
    setLoading(true)
    setUploadError(null)
    try {
      const uploaded: KnowledgeItem[] = []
      for (const f of files) {
        const title = isMulti ? f.name.replace(/\.pdf$/i, '') : name
        const item = await api.knowledge.upload(f, title, docType)
        uploaded.push(item)
      }
      setDocs((prev) => [...uploaded.reverse(), ...prev])
      setFiles([])
      setName('')
      setDocType('general')
      // Auto-open SSE stream for the first uploaded doc that is extracting
      const extracting = uploaded.find((d) => d.extraction_status === 'extracting')
      if (extracting) {
        startExtractionStream(extracting.id)
      }
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(id: number) {
    await api.knowledge.delete(id)
    setDocs((prev) => prev.filter((d) => d.id !== id))
  }

  function startEdit(doc: KnowledgeItem) {
    setEditingId(doc.id)
    setEditTitle(doc.title)
    setEditDocType(doc.doc_type)
    setEditFile(null)
  }

  async function handleUpdate(id: number) {
    setEditLoading(true)
    try {
      const updated = await api.knowledge.update(id, editTitle, editDocType, editFile)
      setDocs((prev) => prev.map((d) => (d.id === id ? updated : d)))
      setEditingId(null)
    } finally {
      setEditLoading(false)
    }
  }

  return (
    <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
      <Sidebar sessions={sessions} />
      <div className="flex-1 overflow-y-auto">
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
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Document Name {isMulti && <span className="text-slate-400 font-normal">(using filenames)</span>}
              </label>
              <input
                type="text"
                value={isMulti ? '' : name}
                onChange={(e) => setName(e.target.value)}
                placeholder={isMulti ? 'Auto — using each file name' : 'e.g. Product Visual Aid 2024'}
                disabled={isMulti}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-50 disabled:text-slate-400"
                required={!isMulti}
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
                  : files.length
                  ? 'border-green-400 bg-green-50'
                  : 'border-slate-300 hover:border-slate-400 bg-slate-50'
              }`}
            >
              <input
                id="kb-file-input"
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
              {files.length ? (
                <>
                  <svg className="h-8 w-8 text-green-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {files.length === 1 ? (
                    <>
                      <p className="text-sm font-medium text-slate-700">{files[0].name}</p>
                      <p className="text-xs text-slate-400 mt-1">{(files[0].size / 1024).toFixed(0)} KB</p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-slate-700">{files.length} PDFs selected</p>
                      <ul className="mt-2 space-y-0.5 text-center">
                        {files.map((f, i) => (
                          <li key={i} className="text-xs text-slate-500 truncate max-w-xs">{f.name}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </>
              ) : (
                <>
                  <svg className="h-8 w-8 text-slate-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-sm text-slate-500">Drag & drop PDFs or <span className="text-indigo-600 font-medium">browse</span></p>
                  <p className="text-xs text-slate-400 mt-1">Select one or multiple PDFs, up to 50MB each</p>
                </>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={!files.length || (!isMulti && !name) || loading}
            className="w-full sm:w-auto rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Uploading...' : 'Upload Document'}
          </button>
          {uploadError && (
            <p className="text-sm text-red-600">{uploadError}</p>
          )}
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
              <li key={doc.id}>
                {editingId === doc.id ? (
                  <div className="flex items-center gap-3 px-6 py-4 flex-wrap">
                    <input
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 min-w-0 flex-1"
                    />
                    <select
                      value={editDocType}
                      onChange={(e) => setEditDocType(e.target.value)}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      {DOC_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                    <label className="cursor-pointer rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 transition-colors">
                      {editFile ? editFile.name : 'Replace PDF'}
                      <input type="file" accept=".pdf" className="hidden" onChange={(e) => setEditFile(e.target.files?.[0] ?? null)} />
                    </label>
                    <button
                      onClick={() => handleUpdate(doc.id)}
                      disabled={editLoading}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      {editLoading ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-sm text-slate-400 hover:text-slate-600 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-4 px-6 py-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <svg className="h-5 w-5 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 truncate">{doc.title}</p>
                        <p className="text-xs text-slate-400 truncate">{doc.filename}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${docTypeBadge(doc.doc_type)}`}>
                        {DOC_TYPES.find((t) => t.value === doc.doc_type)?.label ?? doc.doc_type}
                      </span>
                      {doc.extraction_status === 'extracting' && (
                        <button
                          onClick={() => {
                            if (claimsDocId === doc.id) {
                              setClaimsDocId(null)
                              setExtractionProgress(null)
                            } else {
                              startExtractionStream(doc.id)
                            }
                          }}
                          className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-amber-50 text-amber-700 animate-pulse"
                        >
                          Extracting…
                        </button>
                      )}
                      {doc.extraction_status === 'failed' && (
                        <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-red-50 text-red-700">
                          Failed
                        </span>
                      )}
                      {(doc.extraction_status === 'complete' || doc.extraction_status === 'pending' || !doc.extraction_status) && doc.claim_count !== undefined && (
                        <button
                          onClick={() => {
                            if (claimsDocId === doc.id) {
                              setClaimsDocId(null)
                            } else {
                              setClaimsDocId(doc.id)
                              loadClaims(doc.id)
                            }
                          }}
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
                            claimsDocId === doc.id
                              ? 'bg-indigo-600 text-white'
                              : doc.extraction_status === 'complete'
                              ? 'bg-green-50 text-green-700 hover:bg-green-100'
                              : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100'
                          }`}
                        >
                          {doc.claim_count} claim{doc.claim_count !== 1 ? 's' : ''}
                        </button>
                      )}
                      <button
                        onClick={() => startEdit(doc)}
                        className="text-slate-400 hover:text-indigo-500 transition-colors"
                        aria-label="Edit document"
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 012.828 2.828L11.828 15.828a2 2 0 01-1.414.586H7v-3a2 2 0 01.586-1.414z" />
                        </svg>
                      </button>
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
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Claims panel */}
      {claimsDocId !== null && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-slate-700">
                Claims — {docs.find((d) => d.id === claimsDocId)?.title}
              </h2>
              <span className="text-xs text-slate-400">{claims.length} total</span>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={claimsTypeFilter}
                onChange={(e) => setClaimsTypeFilter(e.target.value)}
                className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 focus:border-indigo-500 focus:outline-none"
              >
                <option value="">All types</option>
                {Object.entries(CLAIM_TYPE_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
              <button
                onClick={() => setClaimsDocId(null)}
                className="text-slate-400 hover:text-slate-600 transition-colors text-xs"
              >
                Close
              </button>
            </div>
          </div>

          {extractionProgress && claimsDocId !== null && (
            <div className="px-6 py-3 bg-amber-50 border-b border-amber-100">
              <div className="flex items-center justify-between text-xs text-amber-700 mb-1.5">
                <span>Extracting claims…</span>
                <span>{extractionProgress.claims_so_far} claims found</span>
              </div>
              <div className="w-full bg-amber-200 rounded-full h-1.5">
                <div className="bg-amber-500 h-1.5 rounded-full transition-all duration-500 animate-pulse" style={{ width: '100%' }} />
              </div>
            </div>
          )}

          {claimsLoading ? (
            <div className="py-12 text-center text-sm text-slate-400">Loading claims…</div>
          ) : claims.length === 0 && !extractionProgress ? (
            <div className="py-12 text-center text-sm text-slate-400">No claims extracted for this document.</div>
          ) : (
            <ul className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
              {claims
                .filter((c) => !claimsTypeFilter || c.claim_type === claimsTypeFilter)
                .map((claim) => (
                  <li key={claim.id} className={`flex items-start gap-3 px-6 py-3 ${claim.is_approved ? '' : 'opacity-50'}`}>
                    <button
                      onClick={() => toggleApproval(claimsDocId, claim)}
                      className={`mt-0.5 flex-shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
                        claim.is_approved
                          ? 'border-green-500 bg-green-500 text-white'
                          : 'border-slate-300 bg-white'
                      }`}
                      title={claim.is_approved ? 'Approved — click to reject' : 'Rejected — click to approve'}
                    >
                      {claim.is_approved && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-800 leading-relaxed">{claim.text}</p>
                      {claim.source_citation && (
                        <p className="text-xs text-slate-400 mt-0.5">{claim.source_citation}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${CLAIM_TYPE_COLORS[claim.claim_type] ?? 'bg-slate-100 text-slate-600'}`}>
                        {CLAIM_TYPE_LABELS[claim.claim_type] ?? claim.claim_type}
                      </span>
                      <button
                        onClick={() => handleDeleteClaim(claimsDocId, claim.id)}
                        className="text-slate-300 hover:text-red-400 transition-colors"
                        title="Delete claim"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}

      </div>
      </div>
    </div>
  )
}
