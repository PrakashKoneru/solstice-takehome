'use client'

import { useState } from 'react'
import Sidebar from '@/components/Sidebar'

type DesignSystem = {
  id: number
  name: string
  pdf_filename: string
  tokens: {
    colors?: { name: string; hex: string }[]
    fonts?: { name: string; usage: string }[]
    button_styles?: string
    headline_styles?: string
  }
  created_at: string
}

export default function DesignSystemPage() {
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [systems, setSystems] = useState<DesignSystem[]>([])
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
  }

  return (
    <div className="flex overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>
      <Sidebar sessions={[]} />
      <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Design System</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload a brand style guide PDF. The AI will extract design tokens and apply them to all generated content.
        </p>
      </div>

      {/* Upload form */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">Upload Style Guide</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Product Brand 2024"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">PDF File</label>
            <div
              onDrop={handleDrop}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onClick={() => document.getElementById('ds-file-input')?.click()}
              className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors ${
                dragOver
                  ? 'border-indigo-400 bg-indigo-50'
                  : file
                  ? 'border-green-400 bg-green-50'
                  : 'border-slate-300 hover:border-slate-400 bg-slate-50'
              }`}
            >
              <input
                id="ds-file-input"
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
            {loading ? 'Extracting tokens...' : 'Upload & Extract'}
          </button>
        </form>
      </div>

      {/* Existing design systems */}
      {systems.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-700">Uploaded Design Systems</h2>
          </div>
          <ul className="divide-y divide-slate-200">
            {systems.map((ds) => (
              <li key={ds.id} className="px-6 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{ds.name}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{ds.pdf_filename}</p>
                  </div>
                  {ds.tokens.colors && (
                    <div className="flex gap-1 flex-shrink-0">
                      {ds.tokens.colors.slice(0, 5).map((c) => (
                        <div
                          key={c.hex}
                          title={c.name}
                          className="h-5 w-5 rounded-full border border-slate-200"
                          style={{ backgroundColor: c.hex }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {systems.length === 0 && (
        <p className="text-center text-sm text-slate-400 py-8">No design systems uploaded yet.</p>
      )}
      </div>
      </div>
    </div>
  )
}
