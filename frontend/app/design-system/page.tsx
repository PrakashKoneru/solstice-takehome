'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import { api, type DesignSystem, type DesignSystemAsset, type Session, type BrandGuidelines, type SlideTemplate } from '@/lib/api'

type Tab = 'tokens' | 'brand' | 'assets'

const COLOR_CATEGORIES = ['palette', 'fill', 'border', 'text', 'brand', 'state'] as const
const TYPO_ROLES = ['hero', 'h1', 'h2', 'body', 'caption'] as const

function ColorSwatch({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-6 w-6 rounded border border-slate-200 flex-shrink-0"
        style={{ backgroundColor: value }}
        title={value}
      />
      <div className="min-w-0">
        <p className="text-xs font-medium text-slate-700 capitalize">{label}</p>
        <p className="text-xs text-slate-400 font-mono">{value}</p>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">{title}</h3>
      {children}
    </div>
  )
}

function TokensTab({ tokens }: { tokens: DesignSystem['tokens'] }) {
  const hasColors = tokens.colors && Object.values(tokens.colors).some(
    (cat) => cat && Object.values(cat).some(Boolean)
  )
  const hasTypo = tokens.fonts && Object.values(tokens.fonts).some(Boolean)
  const hasSpacing = tokens.spacing && Object.values(tokens.spacing).some(Boolean)
  const hasBorderRadius = tokens.borderRadius && Object.values(tokens.borderRadius).some(Boolean)
  const hasShadows = tokens.shadows && Object.values(tokens.shadows).some(Boolean)
  const hasGrid = tokens.grid && (tokens.grid.gutter || tokens.grid.margin)
  const hasCta = tokens.components?.cta && Object.values(tokens.components.cta).some(Boolean)

  if (!hasColors && !hasTypo && !hasSpacing) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-slate-400 text-sm">
        No tokens extracted. Try re-uploading your style guide.
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {hasColors && (
        <Section title="Colors">
          <div className="space-y-5">
            {COLOR_CATEGORIES.map((cat) => {
              const group = tokens.colors?.[cat]
              if (!group || !Object.values(group).some(Boolean)) return null
              return (
                <div key={cat}>
                  <p className="text-xs font-medium text-slate-600 capitalize mb-2">{cat}</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {Object.entries(group).map(([k, v]) => (
                      v ? <ColorSwatch key={k} label={k} value={v} /> : null
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </Section>
      )}

      {hasTypo && (
        <Section title="Typography">
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50">
                <tr>
                  {['Role', 'Font', 'Size', 'Weight', 'Line Height'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-medium text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {TYPO_ROLES.map((role) => {
                  const font = tokens.fonts?.[role]
                  const size = tokens.fontSizes?.[role]
                  const weight = tokens.fontWeights?.[role]
                  const lh = tokens.lineHeight?.[role]
                  if (!font && !size && !weight && !lh) return null
                  return (
                    <tr key={role} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-medium text-slate-700 capitalize">{role}</td>
                      <td className="px-3 py-2 text-slate-600 font-mono text-xs">{font || '—'}</td>
                      <td className="px-3 py-2 text-slate-600 font-mono text-xs">{size || '—'}</td>
                      <td className="px-3 py-2 text-slate-600 font-mono text-xs">{weight || '—'}</td>
                      <td className="px-3 py-2 text-slate-600 font-mono text-xs">{lh || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {hasSpacing && (
        <Section title="Spacing">
          <div className="flex flex-wrap gap-2">
            {Object.entries(tokens.spacing ?? {}).map(([k, v]) => v ? (
              <div key={k} className="flex items-center gap-1.5 rounded-md border border-slate-200 px-2.5 py-1">
                <span className="text-xs font-medium text-slate-600">{k}</span>
                <span className="text-xs text-slate-400 font-mono">{v}</span>
              </div>
            ) : null)}
          </div>
        </Section>
      )}

      {(hasBorderRadius || hasShadows || hasGrid) && (
        <Section title="Other Tokens">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {hasBorderRadius && (
              <div>
                <p className="text-xs font-medium text-slate-600 mb-1">Border Radius</p>
                <div className="space-y-0.5">
                  {Object.entries(tokens.borderRadius ?? {}).map(([k, v]) => v ? (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-slate-500 capitalize">{k}</span>
                      <span className="font-mono text-slate-700">{v}</span>
                    </div>
                  ) : null)}
                </div>
              </div>
            )}
            {hasShadows && (
              <div>
                <p className="text-xs font-medium text-slate-600 mb-1">Shadows</p>
                <div className="space-y-0.5">
                  {Object.entries(tokens.shadows ?? {}).map(([k, v]) => v ? (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-slate-500 capitalize">{k}</span>
                      <span className="font-mono text-slate-700 truncate max-w-[160px]">{v}</span>
                    </div>
                  ) : null)}
                </div>
              </div>
            )}
            {hasGrid && (
              <div>
                <p className="text-xs font-medium text-slate-600 mb-1">Grid</p>
                <div className="space-y-0.5">
                  {Object.entries(tokens.grid ?? {}).map(([k, v]) => v ? (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-slate-500 capitalize">{k}</span>
                      <span className="font-mono text-slate-700">{String(v)}</span>
                    </div>
                  ) : null)}
                </div>
              </div>
            )}
          </div>
        </Section>
      )}

      {hasCta && (
        <Section title="Components — CTA">
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(tokens.components?.cta ?? {}).map(([k, v]) => v ? (
              <div key={k} className="flex justify-between text-xs rounded-md border border-slate-200 px-3 py-1.5">
                <span className="text-slate-500 capitalize">{k}</span>
                <span className="font-mono text-slate-700">{v}</span>
              </div>
            ) : null)}
          </div>
        </Section>
      )}
    </div>
  )
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700 font-medium">
      {children}
    </span>
  )
}

function FlagPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block rounded-full bg-red-50 border border-red-200 px-2.5 py-0.5 text-xs text-red-700 font-medium">
      {children}
    </span>
  )
}

function BrandTab({ guidelines, templates }: { guidelines: BrandGuidelines; templates: SlideTemplate[] }) {
  const hasGuidelines = guidelines && Object.values(guidelines).some((v) =>
    Array.isArray(v) ? v.length > 0 : Boolean(v)
  )
  const hasTemplates = templates && templates.length > 0

  if (!hasGuidelines && !hasTemplates) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-slate-400 text-sm">
        No brand guidelines extracted. Try re-uploading your style guide.
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {hasGuidelines && (
        <>
          {(guidelines.personality?.length ?? 0) > 0 && (
            <Section title="Personality">
              <div className="flex flex-wrap gap-2">
                {guidelines.personality!.map((p) => <Pill key={p}>{p}</Pill>)}
              </div>
            </Section>
          )}

          {(guidelines.tone) && (
            <Section title="Tone of Voice">
              <p className="text-sm text-slate-700">{guidelines.tone}</p>
            </Section>
          )}

          {(guidelines.primaryFont || guidelines.secondaryFont || guidelines.fontUsageRule) && (
            <Section title="Typography">
              <div className="space-y-2">
                {guidelines.primaryFont && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-slate-500 w-32 flex-shrink-0">Primary font</span>
                    <span className="font-mono text-slate-800">{guidelines.primaryFont}</span>
                  </div>
                )}
                {guidelines.secondaryFont && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-slate-500 w-32 flex-shrink-0">Secondary font</span>
                    <span className="font-mono text-slate-800">{guidelines.secondaryFont}</span>
                  </div>
                )}
                {guidelines.fontUsageRule && (
                  <p className="text-xs text-slate-500 mt-1">{guidelines.fontUsageRule}</p>
                )}
              </div>
            </Section>
          )}

          {guidelines.colorHierarchy && (
            <Section title="Color Hierarchy">
              <p className="text-sm text-slate-700">{guidelines.colorHierarchy}</p>
            </Section>
          )}

          {guidelines.layoutPrinciples && (
            <Section title="Layout Principles">
              <p className="text-sm text-slate-700">{guidelines.layoutPrinciples}</p>
            </Section>
          )}

          {guidelines.hallmark && (
            <Section title="Brand Hallmark">
              <p className="text-sm text-slate-700">{guidelines.hallmark}</p>
            </Section>
          )}

          {(guidelines.requiredElements?.length ?? 0) > 0 && (
            <Section title="Required Elements">
              <div className="flex flex-wrap gap-2">
                {guidelines.requiredElements!.map((el) => <Pill key={el}>{el}</Pill>)}
              </div>
            </Section>
          )}

          {(guidelines.prohibited?.length ?? 0) > 0 && (
            <Section title="Prohibited">
              <div className="flex flex-wrap gap-2">
                {guidelines.prohibited!.map((el) => <FlagPill key={el}>{el}</FlagPill>)}
              </div>
            </Section>
          )}
        </>
      )}

      {hasTemplates && (
        <Section title="Slide Templates">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {templates.map((tmpl, i) => (
              <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 space-y-1.5">
                <p className="text-sm font-semibold text-slate-800">{tmpl.name}</p>
                {tmpl.description && <p className="text-xs text-slate-500">{tmpl.description}</p>}
                {tmpl.layout && (
                  <div className="flex gap-1.5 items-center text-xs text-slate-500">
                    <span className="font-medium text-slate-600">Layout:</span>
                    <span>{tmpl.layout}</span>
                  </div>
                )}
                {tmpl.bestFor && (
                  <div className="flex gap-1.5 items-center text-xs text-slate-500">
                    <span className="font-medium text-slate-600">Best for:</span>
                    <span>{tmpl.bestFor}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}

function AssetsTab({ dsId }: { dsId: number }) {
  const [assets, setAssets] = useState<DesignSystemAsset[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [assetName, setAssetName] = useState('')
  const [assetType, setAssetType] = useState<'icon' | 'logo' | 'image'>('icon')
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    api.designSystem.listAssets(dsId).then(setAssets).catch(console.error)
  }, [dsId])

  async function handleUploadAsset(e: React.FormEvent) {
    e.preventDefault()
    if (!file || !assetName) return
    setUploading(true)
    try {
      const asset = await api.designSystem.uploadAsset(dsId, file, assetName, assetType)
      setAssets((prev) => [asset, ...prev])
      setFile(null)
      setAssetName('')
    } catch (err) {
      console.error(err)
    } finally {
      setUploading(false)
    }
  }

  async function handleDeleteAsset(assetId: number) {
    await api.designSystem.deleteAsset(dsId, assetId)
    setAssets((prev) => prev.filter((a) => a.id !== assetId))
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-700 mb-4">Upload Asset</h3>
        <form onSubmit={handleUploadAsset} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Name</label>
              <input
                type="text"
                value={assetName}
                onChange={(e) => setAssetName(e.target.value)}
                placeholder="e.g. Brand Logo"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Type</label>
              <select
                value={assetType}
                onChange={(e) => setAssetType(e.target.value as typeof assetType)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="icon">Icon</option>
                <option value="logo">Logo</option>
                <option value="image">Image</option>
              </select>
            </div>
          </div>
          <div
            onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) setFile(f) }}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onClick={() => document.getElementById('asset-file-input')?.click()}
            className={`flex items-center justify-center rounded-lg border-2 border-dashed p-5 cursor-pointer transition-colors ${
              dragOver ? 'border-indigo-400 bg-indigo-50' : file ? 'border-green-400 bg-green-50' : 'border-slate-300 hover:border-slate-400 bg-slate-50'
            }`}
          >
            <input id="asset-file-input" type="file" accept=".png,.jpg,.jpeg,.svg,.webp" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {file ? (
              <p className="text-sm font-medium text-slate-700">{file.name}</p>
            ) : (
              <p className="text-sm text-slate-500">PNG, JPG, SVG, WebP — drag or <span className="text-indigo-600 font-medium">browse</span></p>
            )}
          </div>
          <button
            type="submit"
            disabled={!file || !assetName || uploading}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </form>
      </div>

      {assets.length === 0 ? (
        <p className="text-center text-sm text-slate-400 py-6">No assets uploaded yet.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {assets.map((asset) => (
            <div key={asset.id} className="group relative rounded-xl border border-slate-200 bg-white p-3 flex flex-col items-center gap-2">
              <div className="h-16 w-16 rounded-lg bg-slate-100 flex items-center justify-center overflow-hidden">
                {asset.filename.endsWith('.svg') ? (
                  <img src={`http://localhost:5001/uploads/${asset.filename}`} alt={asset.name} className="h-12 w-12 object-contain" />
                ) : (
                  <img src={`http://localhost:5001/uploads/${asset.filename}`} alt={asset.name} className="h-full w-full object-cover rounded-lg" />
                )}
              </div>
              <p className="text-xs font-medium text-slate-700 text-center truncate w-full">{asset.name}</p>
              <span className="text-xs text-slate-400 capitalize">{asset.asset_type}</span>
              <button
                onClick={() => handleDeleteAsset(asset.id)}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-all"
                aria-label="Delete asset"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function DesignSystemPage() {
  const [systems, setSystems] = useState<DesignSystem[]>([])
  const [selected, setSelected] = useState<DesignSystem | null>(null)
  const [tab, setTab] = useState<Tab>('tokens')
  const [sessions, setSessions] = useState<Session[]>([])

  // Upload form state
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    api.designSystem.list().then(setSystems).catch(console.error)
    api.sessions.list().then(setSessions).catch(console.error)
  }, [])

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault()
    if (!file || !name) return
    setLoading(true)
    try {
      const ds = await api.designSystem.upload(file, name)
      setSystems((prev) => [ds, ...prev])
      setSelected(ds)
      setTab('tokens')
      setFile(null)
      setName('')
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(id: number) {
    await api.designSystem.delete(id)
    setSystems((prev) => prev.filter((s) => s.id !== id))
    if (selected?.id === id) setSelected(null)
  }

  async function handleSetDefault(id: number) {
    const updated = await api.designSystem.setDefault(id)
    setSystems((prev) => prev.map((s) => ({ ...s, is_default: s.id === id })))
    if (selected?.id === id) setSelected(updated)
  }

  return (
    <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
      <Sidebar sessions={sessions} />

      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">

        {/* Left panel: upload + list */}
        <div className="w-full md:w-80 md:flex-shrink-0 flex flex-col border-b md:border-b-0 md:border-r border-slate-200 bg-white md:overflow-hidden">
          <div className="px-4 py-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-800">Design Systems</h2>
          </div>

          {/* Upload form */}
          <div className="px-4 py-4 border-b border-slate-200">
            <form onSubmit={handleUpload} className="space-y-3">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name (e.g. Brand 2024)"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                required
              />
              <div
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f?.type === 'application/pdf') setFile(f) }}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onClick={() => document.getElementById('ds-file-input')?.click()}
                className={`flex items-center justify-center rounded-lg border-2 border-dashed p-4 cursor-pointer transition-colors text-sm ${
                  dragOver ? 'border-indigo-400 bg-indigo-50' : file ? 'border-green-400 bg-green-50' : 'border-slate-300 hover:border-slate-400 bg-slate-50'
                }`}
              >
                <input id="ds-file-input" type="file" accept=".pdf" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                {file ? (
                  <p className="text-sm text-slate-700 truncate">{file.name}</p>
                ) : (
                  <p className="text-slate-400">Drop PDF or <span className="text-indigo-600 font-medium">browse</span></p>
                )}
              </div>
              <button
                type="submit"
                disabled={!file || !name || loading}
                className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? 'Extracting tokens...' : 'Upload & Extract'}
              </button>
            </form>
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto py-2">
            {systems.length === 0 ? (
              <p className="px-4 py-3 text-xs text-slate-400">No design systems yet.</p>
            ) : (
              <ul className="space-y-0.5 px-2">
                {systems.map((ds) => (
                  <li key={ds.id} className="group relative">
                    <button
                      onClick={() => { setSelected(ds); setTab('tokens') }}
                      className={`w-full text-left rounded-lg px-3 py-2 pr-8 text-sm transition-colors ${
                        selected?.id === ds.id
                          ? 'bg-slate-100 text-slate-900 font-medium'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                      }`}
                    >
                      <div className="flex items-baseline gap-1.5 min-w-0">
                        <p className="truncate text-sm">{ds.name}</p>
                        {ds.is_default && (
                          <span className="flex-shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 leading-none">Default</span>
                        )}
                      </div>
                      <p className="text-xs text-slate-400 truncate mt-0.5">{ds.pdf_filename}</p>
                    </button>
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-all">
                      {!ds.is_default && (
                        <button
                          onClick={() => handleSetDefault(ds.id)}
                          className="text-slate-400 hover:text-indigo-500 transition-colors"
                          aria-label="Set as default"
                          title="Set as default"
                        >
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                          </svg>
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(ds.id)}
                        className="text-slate-400 hover:text-red-500 transition-colors"
                        aria-label="Delete design system"
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
        </div>

        {/* Right panel: detail */}
        <div className="flex flex-1 flex-col overflow-hidden bg-slate-50">
          {!selected ? (
            <div className="flex flex-1 flex-col items-center justify-center text-center text-slate-400 px-8">
              <svg className="h-12 w-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
              </svg>
              <p className="text-sm">Select or upload a design system to view tokens.</p>
            </div>
          ) : (
            <>
              <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold text-slate-900">{selected.name}</p>
                    {selected.is_default && (
                      <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">Default</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400">{selected.pdf_filename}</p>
                </div>
                <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                  {(['tokens', 'brand', 'assets'] as Tab[]).map((t) => (
                    <button
                      key={t}
                      onClick={() => setTab(t)}
                      className={`px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                        tab === t ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                {tab === 'tokens' ? (
                  <TokensTab tokens={selected.tokens} />
                ) : tab === 'brand' ? (
                  <BrandTab guidelines={selected.brand_guidelines ?? {}} templates={selected.slide_templates ?? []} />
                ) : (
                  <AssetsTab dsId={selected.id} />
                )}
              </div>
            </>
          )}
        </div>

      </div>
    </div>
  )
}
