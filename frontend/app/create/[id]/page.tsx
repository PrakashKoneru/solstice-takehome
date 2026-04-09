'use client'

import React, { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { api, type Session, type DesignSystem, type KnowledgeItem, type Message as ApiMessage, type ReviewReport } from '@/lib/api'
import jsPDF from 'jspdf'
import { PresenceProvider, usePresence, type PresenceUser, type CursorPosition } from '@/contexts/PresenceContext'

type ChatMessage = { role: 'user' | 'assistant'; content: string }
type Version = { html: string; prompt: string; review: ReviewReport | null }
type ViewMode = 'preview' | 'edit' | 'source'

function sanitizeHtml(html: string): string {
  if (typeof window === 'undefined') return html
  const div = document.createElement('div')
  div.innerHTML = html
  div.querySelectorAll('script').forEach((s) => s.remove())
  div.querySelectorAll('*').forEach((el) => {
    Array.from(el.attributes).forEach((attr) => {
      if (attr.name.startsWith('on')) el.removeAttribute(attr.name)
    })
  })
  return div.innerHTML
}

function parseSlides(html: string): string[] {
  if (typeof window === 'undefined') return [html]
  const div = document.createElement('div')
  div.innerHTML = html
  const slides = Array.from(div.querySelectorAll('[data-slide]'))
  if (slides.length > 0) return slides.map((s) => (s as HTMLElement).outerHTML)
  return [html]
}

const CLAIM_LOCKED_STYLE = `
  .claim-locked, [data-claim-id][contenteditable="false"] {
    background: rgba(59, 130, 246, 0.08);
    cursor: not-allowed;
    border-radius: 2px;
    padding: 0 1px;
    user-select: none;
  }
`

const PRESENCE_COLORS = [
  '#f59e0b', '#10b981', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#f97316', '#14b8a6',
]

function PresenceDots({ users, myUserId }: { users: PresenceUser[]; myUserId: string }) {
  const remoteUsers = users.filter((u) => u.user_id !== myUserId)
  if (remoteUsers.length === 0) return null
  const label =
    remoteUsers.length === 1
      ? '1 other viewing'
      : `${remoteUsers.length - 1} others viewing`
  const tooltip = remoteUsers.map((u) => u.display_name).join(', ')
  return (
    <div
      className="flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-1"
      title={tooltip}
    >
      <div className="flex items-center -space-x-1">
        {remoteUsers.slice(0, 3).map((u, i) => (
          <div
            key={u.user_id}
            className="h-2 w-2 rounded-full ring-1 ring-white"
            style={{ backgroundColor: PRESENCE_COLORS[i % PRESENCE_COLORS.length] }}
          />
        ))}
      </div>
      <span className="text-[11px] text-slate-500 font-medium">{label}</span>
    </div>
  )
}

function RemoteEditingBadge({ editor }: { editor: PresenceUser }) {
  return (
    <div className="absolute top-0 left-0 right-0 z-10 flex items-center gap-1.5 bg-amber-50 border-b border-amber-300 px-3 py-1">
      <div className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
      <span className="text-xs text-amber-700 font-medium">{editor.display_name} is editing...</span>
    </div>
  )
}

function EditableSlide({ html, onSave, paneH, slideIndex, onFocusSlide, onBlurSlide, remoteEditor }: { html: string; onSave: (updated: string) => void; paneH: number; slideIndex?: number; onFocusSlide?: (i: number) => void; onBlurSlide?: () => void; remoteEditor?: PresenceUser | null }) {
  const innerRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [scaledH, setScaledH] = React.useState(paneH)

  useEffect(() => {
    const wrap = wrapRef.current
    const inner = innerRef.current
    if (!wrap || !inner) return
    const apply = () => {
      const scale = Math.min(wrap.clientWidth / 1024, paneH / 576) * 0.92
      inner.style.transform = `scale(${scale})`
      setScaledH(Math.round(576 * scale) + 24)
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [html, paneH])

  // Inject claim-locked styles into the slide HTML
  const styledHtml = React.useMemo(() => {
    const s = sanitizeHtml(html)
    if (s.includes('data-claim-id') && !s.includes('claim-locked-injected')) {
      return `<style class="claim-locked-injected">${CLAIM_LOCKED_STYLE}</style>${s}`
    }
    return s
  }, [html])

  const isRemoteEditing = !!remoteEditor

  return (
    <div
      ref={wrapRef}
      className="relative"
      style={{ width: '100%', height: scaledH, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: isRemoteEditing ? '2px solid #f59e0b' : undefined, borderRadius: isRemoteEditing ? 4 : undefined }}
    >
      {remoteEditor && <RemoteEditingBadge editor={remoteEditor} />}
      <div
        ref={innerRef}
        contentEditable={!isRemoteEditing}
        suppressContentEditableWarning
        style={{ width: 1024, height: 576, transformOrigin: 'center center', flexShrink: 0, overflow: 'hidden', outline: 'none', opacity: isRemoteEditing ? 0.7 : 1 }}
        dangerouslySetInnerHTML={{ __html: styledHtml }}
        onFocus={() => { if (slideIndex !== undefined) onFocusSlide?.(slideIndex) }}
        onBlur={(e) => {
          onSave(e.currentTarget.outerHTML)
          onBlurSlide?.()
        }}
      />
    </div>
  )
}

function SlidePreview({ html, paneH }: { html: string; paneH: number }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  const [scaledH, setScaledH] = React.useState(paneH)

  useEffect(() => {
    const wrap = wrapRef.current
    const inner = innerRef.current
    if (!wrap || !inner) return
    const apply = () => {
      const scale = Math.min(wrap.clientWidth / 1024, paneH / 576) * 0.92
      inner.style.transform = `scale(${scale})`
      setScaledH(Math.round(576 * scale) + 24)
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [html, paneH])

  return (
    <div
      ref={wrapRef}
      style={{ width: '100%', height: scaledH, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
    >
      <div
        ref={innerRef}
        style={{ width: 1024, height: 576, transformOrigin: 'center center', flexShrink: 0, overflow: 'hidden' }}
        dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }}
      />
    </div>
  )
}

const CURSOR_COLORS = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899']

function RemoteCursor({ name, x, y, color }: { name: string; x: number; y: number; color: string }) {
  return (
    <div
      className="pointer-events-none absolute z-50 transition-all duration-100 ease-out"
      style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
    >
      <svg width="16" height="20" viewBox="0 0 16 20" fill="none" style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.3))' }}>
        <path d="M0 0L16 12L6.4 12L0 20V0Z" fill={color} />
      </svg>
      <span
        className="absolute left-4 top-3 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium text-white"
        style={{ backgroundColor: color }}
      >
        {name}
      </span>
    </div>
  )
}

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

function VerdictBadge({ verdict }: { verdict: ReviewReport['verdict'] }) {
  const styles = {
    approved: 'bg-green-50 text-green-700 border-green-200',
    flagged:  'bg-yellow-50 text-yellow-700 border-yellow-200',
    blocked:  'bg-red-50 text-red-700 border-red-200',
  }
  const icons = {
    approved: (
      <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    flagged: (
      <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
    ),
    blocked: (
      <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${styles[verdict]}`}>
      {icons[verdict]}
      {verdict}
    </span>
  )
}

function StatusChip({ status }: { status: 'verified' | 'unsupported' | 'inferred' }) {
  const styles = {
    verified:    'bg-green-100 text-green-700',
    unsupported: 'bg-red-100 text-red-700',
    inferred:    'bg-yellow-100 text-yellow-700',
  }
  return (
    <span className={`flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${styles[status]}`}>
      {status}
    </span>
  )
}

export default function SessionPage() {
  const { id } = useParams<{ id: string }>()
  return (
    <PresenceProvider sessionId={Number(id)}>
      <SessionPageInner />
    </PresenceProvider>
  )
}

function SessionPageInner() {
  const router = useRouter()
  const { id } = useParams<{ id: string }>()

  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSession, setActiveSession] = useState<Session | null>(null)
  const [creating, setCreating] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streamStatus, setStreamStatus] = useState<string>('')
  const htmlChunksRef = useRef<string>('')
  const [currentHtml, setCurrentHtml] = useState('')
  const [currentReview, setCurrentReview] = useState<ReviewReport | null>(null)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('preview')
  const [editContent, setEditContent] = useState('')
  const [versions, setVersions] = useState<Version[]>([])
  const [activeVersionIdx, setActiveVersionIdx] = useState<number | null>(null)
  const [selectedVersionIdx, setSelectedVersionIdx] = useState<number | null>(null)
  const [restoringIdx, setRestoringIdx] = useState<number | null>(null)
  const [ghostY, setGhostY] = useState<number | null>(null)
  const ghostRef = useRef<HTMLDivElement>(null)
  const dotRefs = useRef<Map<number, HTMLButtonElement>>(new Map())
  const innerScrollRef = useRef<HTMLDivElement>(null)

  const [designSystems, setDesignSystems] = useState<DesignSystem[]>([])
  const [selectedDsId, setSelectedDsId] = useState<number | ''>('')
  const [targetAudience, setTargetAudience] = useState<string>('')
  const [kbDocs, setKbDocs] = useState<KnowledgeItem[]>([])
  const [selectedDocIds, setSelectedDocIds] = useState<Set<number>>(new Set())
  const contextRestoredRef = useRef(false)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [attachUploading, setAttachUploading] = useState(false)
  const docPickerRef = useRef<HTMLDivElement>(null)
  const versionTrailRef = useRef<HTMLDivElement>(null)
  const attachInputRef = useRef<HTMLInputElement>(null)
  const contentEditableRef = useRef<HTMLDivElement>(null)
  const outputPaneRef = useRef<HTMLDivElement>(null)
  const [paneH, setPaneH] = useState(500)

  useEffect(() => {
    const el = outputPaneRef.current
    if (!el) return
    setPaneH(el.clientHeight)
    const ro = new ResizeObserver(() => setPaneH(el.clientHeight))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const [exporting, setExporting] = useState(false)

  const [reviewStale, setReviewStale] = useState(false)

  // Presence
  const presence = usePresence()
  const lastCursorBroadcast = useRef(0)
  const throttledBroadcastCursor = (x: number, y: number, slideIndex: number | null) => {
    const now = Date.now()
    if (now - lastCursorBroadcast.current < 50) return
    lastCursorBroadcast.current = now
    presence.broadcastCursor(x, y, slideIndex)
  }

  // Register remote update handlers
  useEffect(() => {
    presence.onRemoteSlideUpdate.current = (slideIndex: number, html: string, _userId: string) => {
      setCurrentHtml((prev) => {
        const slides = parseSlides(prev)
        if (slideIndex >= 0 && slideIndex < slides.length) {
          slides[slideIndex] = html
          return slides.join('')
        }
        return prev
      })
    }
    presence.onRemoteContentUpdate.current = (html: string, _message: string) => {
      setCurrentHtml(html)
      setEditContent(html)
    }
    return () => {
      presence.onRemoteSlideUpdate.current = null
      presence.onRemoteContentUpdate.current = null
    }
  }, [presence])

  const exportPdf = async () => {
    if (!currentHtml) return
    setExporting(true)
    try {
      const html2canvas = (await import('html2canvas')).default
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'px', format: [1024, 576] })

      // Parse slides from raw HTML — avoids any scale transforms in the preview
      const parser = new DOMParser()
      const doc = parser.parseFromString(currentHtml, 'text/html')
      const slideEls = Array.from(doc.querySelectorAll('[data-slide]'))
      if (!slideEls.length) return

      // Off-screen container at exact slide dimensions, no transforms
      const container = document.createElement('div')
      container.style.cssText = 'position:fixed;left:-9999px;top:0;width:1024px;height:576px;overflow:hidden;'
      document.body.appendChild(container)

      for (let i = 0; i < slideEls.length; i++) {
        container.innerHTML = slideEls[i].outerHTML
        // Wait for images to load
        await Promise.all(
          Array.from(container.querySelectorAll('img')).map(
            img => img.complete ? Promise.resolve() : new Promise(r => { img.onload = r; img.onerror = r })
          )
        )
        const canvas = await html2canvas(container.firstElementChild as HTMLElement, {
          scale: 2,
          useCORS: true,
          allowTaint: true,
          backgroundColor: '#ffffff',
          width: 1024,
          height: 576,
        })
        if (i > 0) pdf.addPage([1024, 576], 'landscape')
        pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, 1024, 576)
      }

      document.body.removeChild(container)
      pdf.save('slides.pdf')
    } finally {
      setExporting(false)
    }
  }

  const selectedDs = designSystems.find((d) => d.id === selectedDsId)
  const audienceOptions = selectedDs?.brand_guidelines?.supportedAudiences ?? []

  // Auto-default audience when DS changes and has supported_audiences
  useEffect(() => {
    if (selectedDs?.brand_guidelines?.supportedAudiences?.length) {
      const options = selectedDs.brand_guidelines.supportedAudiences
      if (!options.includes(targetAudience)) {
        const first = options[0]
        setTargetAudience(first)
        if (typeof window !== 'undefined') localStorage.setItem(`audience-${id}`, first)
      }
    }
  }, [selectedDsId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.sessions.list().then(setSessions).catch(console.error)
    api.designSystem.list().then((dses) => {
      setDesignSystems(dses)
      const def = dses.find((d) => d.is_default)
      if (def) setSelectedDsId(def.id)
    }).catch(console.error)
    api.knowledge.list().then(setKbDocs).catch(console.error)
  }, [])

  // Load the active session + restore messages + restore context when id changes
  useEffect(() => {
    const numId = Number(id)
    if (!numId) return
    contextRestoredRef.current = false
    api.sessions.list().then((all) => {
      const match = all.find((s) => s.id === numId)
      if (match) {
        setActiveSession(match)
        // Restore persisted context (only if something was saved)
        if (match.selected_ds_id !== null) {
          setSelectedDsId(match.selected_ds_id)
        }
        if (match.selected_doc_ids?.length) {
          setSelectedDocIds(new Set(match.selected_doc_ids))
        }
      }
      contextRestoredRef.current = true
    })
    setMessages([])
    setCurrentHtml('')
    setEditContent('')
    setCurrentReview(null)
    setViewMode('preview')
    setVersions([])
    setActiveVersionIdx(null)
    setSelectedVersionIdx(null)
    const savedAudience = typeof window !== 'undefined' ? (localStorage.getItem(`audience-${id}`) ?? '') : ''
    setTargetAudience(savedAudience)
    api.chat.list(numId).then((msgs: ApiMessage[]) => {
      setMessages(msgs.map((m) => ({ role: m.role, content: m.content })))
      const versionList: Version[] = []
      for (let i = 0; i < msgs.length; i++) {
        const m = msgs[i]
        if (m.role === 'assistant' && m.html_content) {
          const userMsg = msgs.slice(0, i).reverse().find((x) => x.role === 'user')
          versionList.push({ html: m.html_content, prompt: userMsg?.content ?? 'Generated', review: m.review_report ?? null })
        }
      }
      setVersions(versionList)
      if (versionList.length > 0) {
        const lastIdx = versionList.length - 1
        setCurrentHtml(versionList[lastIdx].html)
        setEditContent(versionList[lastIdx].html)
        setCurrentReview(versionList[lastIdx].review)
        setActiveVersionIdx(lastIdx)
      }
    }).catch(console.error)
  }, [id])

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (docPickerRef.current && !docPickerRef.current.contains(e.target as Node)) {
        setShowDocPicker(false)
      }
      if (versionTrailRef.current && !versionTrailRef.current.contains(e.target as Node)) {
        setSelectedVersionIdx(null)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  // Persist context selection whenever it changes (after initial restore)
  useEffect(() => {
    const numId = Number(id)
    if (!numId || !contextRestoredRef.current) return
    api.sessions.update(numId, {
      selected_ds_id: selectedDsId || null,
      selected_doc_ids: Array.from(selectedDocIds),
    }).catch(console.error)
  }, [selectedDsId, selectedDocIds]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleNewSession() {
    setCreating(true)
    try {
      const session = await api.sessions.create('New Session')
      setSessions((prev) => [session, ...prev])
      router.push(`/create/${session.id}`)
    } finally {
      setCreating(false)
    }
  }

  async function handleDeleteSession(sessionId: number, e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    await api.sessions.delete(sessionId)
    setSessions((prev) => prev.filter((s) => s.id !== sessionId))
    if (Number(id) === sessionId) router.push('/create')
  }

  function toggleDoc(docId: number) {
    setSelectedDocIds((prev) => {
      const next = new Set(prev)
      next.has(docId) ? next.delete(docId) : next.add(docId)
      return next
    })
  }

  async function handleAttachPdf(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setAttachUploading(true)
    try {
      const title = f.name.replace(/\.pdf$/i, '')
      const item = await api.knowledge.upload(f, title, 'general')
      setKbDocs((prev) => [item, ...prev])
      setSelectedDocIds((prev) => new Set(prev).add(item.id))
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setAttachUploading(false)
      e.target.value = ''
    }
  }

  async function handleSend() {
    if (!input.trim() || sending) return
    if (selectedDocIds.size === 0) {
      setMessages((prev) => [...prev, { role: 'user', content: input.trim() }, { role: 'assistant', content: 'Please select a Knowledge Base document before sending a message.' }])
      setInput('')
      return
    }
    const userMessage = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])
    setSending(true)
    setStreamStatus('Thinking...')
    htmlChunksRef.current = ''

    const isFirstMessage = messages.length === 0
    let receivedHtml = ''
    let receivedReview: ReviewReport | null = null
    let chatText = ''
    let debounceTimer: ReturnType<typeof setTimeout> | null = null

    try {
      const { promise } = api.chat.sendStream(
        Number(id),
        userMessage,
        {
          onStatus: (step) => {
            setStreamStatus(step)
          },
          onSlideReady: (index, layout, title) => {
            setStreamStatus(`Built slide ${index + 1}: ${title || layout}`)
          },
          onHtmlChunk: (chunk) => {
            htmlChunksRef.current += chunk
            // Debounce preview updates to avoid excessive re-renders.
            // IMPORTANT: only touch currentHtml (the preview). Do NOT overwrite
            // editContent or flip viewMode — partial HTML would corrupt the
            // editor and yanking the user out of edit mode is jarring.
            if (debounceTimer) clearTimeout(debounceTimer)
            debounceTimer = setTimeout(() => {
              setCurrentHtml(htmlChunksRef.current)
            }, 500)
          },
          onHtmlComplete: (html) => {
            if (debounceTimer) clearTimeout(debounceTimer)
            receivedHtml = html
            setCurrentHtml(html)
            setEditContent(html)
          },
          onReview: (report) => {
            receivedReview = report
            setCurrentReview(report)
            setReviewStale(false)
            setReviewOpen(false)
          },
          onChat: (text) => {
            chatText = text
          },
          onDone: () => {
            // Final state updates handled below after promise resolves
          },
        },
        selectedDsId,
        Array.from(selectedDocIds),
        currentHtml || null,
        targetAudience || undefined,
      )
      await promise

      setMessages((prev) => [...prev, { role: 'assistant', content: chatText || 'Slides generated — check the output panel.' }])
      if (receivedHtml) {
        const htmlChanged = receivedHtml !== currentHtml
        setViewMode('preview')
        if (htmlChanged) {
          appendVersion(receivedHtml, userMessage, receivedReview)
        }
      }
      if (isFirstMessage && activeSession) {
        const newTitle = userMessage.slice(0, 40)
        api.sessions.update(activeSession.id, { title: newTitle }).then((updated) => {
          setActiveSession(updated)
          setSessions((prev) => prev.map((s) => s.id === updated.id ? updated : s))
        })
      }
    } catch (err) {
      console.error(err)
      const msg = err instanceof Error ? err.message : 'Something went wrong. Please try again.'
      setMessages((prev) => [...prev, { role: 'assistant', content: msg }])
    } finally {
      setSending(false)
      setStreamStatus('')
    }
  }

  function appendVersion(html: string, prompt: string, review: ReviewReport | null) {
    setVersions((prev) => {
      const next = [...prev, { html, prompt, review }]
      setActiveVersionIdx(next.length - 1)
      return next
    })
  }

  const selectedDocs = kbDocs.filter((d) => selectedDocIds.has(d.id))

  return (
    <div className="flex flex-col md:flex-row md:overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>

      {/* Sidebar */}
      <aside className={`hidden md:flex flex-col border-r border-slate-200 bg-white flex-shrink-0 transition-all duration-200 overflow-hidden ${sidebarOpen ? 'w-64' : 'w-10'}`}>
        {sidebarOpen ? (
          <>
            <div className="flex items-center justify-end px-3 pt-2 pb-1">
              <button
                onClick={() => setSidebarOpen(false)}
                className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                aria-label="Collapse sidebar"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
            </div>

            <div className="p-3 pt-1 space-y-0.5">
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
                        className={`block w-full rounded-lg px-3 py-2 pr-8 text-sm transition-colors truncate ${
                          session.id === Number(id)
                            ? 'bg-slate-100 text-slate-900 font-medium'
                            : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                        }`}
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
          </>
        ) : (
          <div className="flex flex-col items-center pt-3 gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              aria-label="Expand sidebar"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}
      </aside>

      {/* Chat panel */}
      <div className="flex flex-col shrink-0 md:flex-none md:w-[30%] border-b md:border-b-0 md:border-r border-slate-200 bg-white overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>
        <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-slate-900 truncate">{activeSession?.title ?? '…'}</p>

          {/* Context controls */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Design system selector */}
            <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs">
              <svg className="h-3.5 w-3.5 text-indigo-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
              </svg>
              <select
                value={selectedDsId}
                onChange={(e) => setSelectedDsId(e.target.value === '' ? '' : Number(e.target.value))}
                className="bg-transparent text-slate-700 font-medium focus:outline-none cursor-pointer max-w-[110px] truncate"
              >
                <option value="">No design system</option>
                {designSystems.map((ds) => (
                  <option key={ds.id} value={ds.id}>{ds.name}{ds.is_default ? ' ★' : ''}</option>
                ))}
              </select>
            </div>

            {/* Audience selector — only shown when DS has identified audiences */}
            {audienceOptions.length > 0 && (
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs">
                <svg className="h-3.5 w-3.5 text-indigo-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                <select
                  value={targetAudience}
                  onChange={(e) => {
                    setTargetAudience(e.target.value)
                    if (typeof window !== 'undefined') localStorage.setItem(`audience-${id}`, e.target.value)
                  }}
                  className="bg-transparent text-slate-700 font-medium focus:outline-none cursor-pointer max-w-[120px] truncate"
                >
                  {audienceOptions.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Knowledge docs picker */}
            <div className="relative" ref={docPickerRef}>
              <button
                onClick={() => setShowDocPicker((v) => !v)}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
                  selectedDocIds.size > 0
                    ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300'
                }`}
              >
                <svg className="h-3.5 w-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                {selectedDocIds.size === 0 ? 'Docs' : `${selectedDocIds.size} doc${selectedDocIds.size !== 1 ? 's' : ''}`}
                <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {showDocPicker && (
                <div className="absolute top-full mt-1.5 right-0 w-64 rounded-xl border border-slate-200 bg-white shadow-lg z-10 overflow-hidden">
                  <div className="px-3 py-2 border-b border-slate-100 flex items-center justify-between">
                    <p className="text-xs font-semibold text-slate-700">Knowledge Base</p>
                    <div className="flex items-center gap-2">
                      {selectedDocIds.size > 0 && (
                        <button onClick={() => setSelectedDocIds(new Set())} className="text-xs text-slate-400 hover:text-slate-600">
                          Clear
                        </button>
                      )}
                      <label title="Upload PDF to knowledge base" className="cursor-pointer text-slate-400 hover:text-indigo-600 transition-colors">
                        {attachUploading ? (
                          <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                        ) : (
                          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                          </svg>
                        )}
                        <input type="file" accept=".pdf" className="hidden" onChange={handleAttachPdf} />
                      </label>
                    </div>
                  </div>
                  {kbDocs.length === 0 ? (
                    <p className="px-3 py-3 text-xs text-slate-400">No documents in knowledge base.</p>
                  ) : (
                    <ul className="max-h-48 overflow-y-auto py-1">
                      {kbDocs.map((doc) => (
                        <li key={doc.id}>
                          <label className="flex items-center gap-2.5 px-3 py-2 hover:bg-slate-50 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedDocIds.has(doc.id)}
                              onChange={() => toggleDoc(doc.id)}
                              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-slate-800 truncate">{doc.title}</p>
                              <p className="text-[10px] text-slate-400 capitalize">{doc.doc_type}</p>
                            </div>
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Context bar */}
        <div className="px-3 py-2 border-b border-l border-r border-dashed border-blue-200 bg-blue-50/60 flex flex-wrap gap-1.5 items-center min-h-[80px]">
          {/* Design system chip */}
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium border ${
            selectedDsId
              ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
              : 'bg-white text-slate-400 border-slate-200'
          }`}>
            <svg className="h-3 w-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
            </svg>
            {selectedDsId
              ? (designSystems.find((d) => d.id === selectedDsId)?.name ?? 'Design System')
              : 'No design system'}
          </span>

          {/* KB doc chips */}
          {kbDocs.filter((d) => selectedDocIds.has(d.id)).map((doc) => (
            <span key={doc.id} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium bg-white border border-slate-200 text-slate-600">
              <svg className="h-3 w-3 flex-shrink-0 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span className="max-w-[100px] truncate">{doc.title}</span>
              <button
                onClick={() => toggleDoc(doc.id)}
                className="ml-0.5 text-slate-400 hover:text-slate-600 transition-colors leading-none"
                aria-label={`Remove ${doc.title}`}
              >
                ×
              </button>
            </span>
          ))}
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
                {msg.role === 'assistant' ? (
                  <ReactMarkdown
                    components={{
                      p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
                      strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                      ul: ({ children }) => <ul className="list-disc pl-4 mb-1">{children}</ul>,
                      ol: ({ children }) => <ol className="list-decimal pl-4 mb-1">{children}</ol>,
                      li: ({ children }) => <li className="mb-0.5">{children}</li>,
                      hr: () => <hr className="my-2 border-slate-300" />,
                      table: ({ children }) => <table className="text-xs border-collapse w-full my-1">{children}</table>,
                      th: ({ children }) => <th className="border border-slate-300 px-2 py-1 bg-slate-200 font-semibold">{children}</th>,
                      td: ({ children }) => <td className="border border-slate-300 px-2 py-1">{children}</td>,
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                ) : msg.content}
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
                  {streamStatus && (
                    <span className="ml-2 text-xs text-slate-500">{streamStatus}</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-slate-200">
          {/* Input row */}
          <div className="px-3 py-3 flex gap-2">
            <input ref={attachInputRef} type="file" accept=".pdf" className="hidden" onChange={handleAttachPdf} />
            <button
              onClick={() => attachInputRef.current?.click()}
              disabled={attachUploading}
              title="Upload PDF to knowledge base"
              className="flex-shrink-0 rounded-lg border border-slate-300 p-2 text-slate-500 hover:border-indigo-400 hover:text-indigo-600 disabled:opacity-40 transition-colors"
            >
              {attachUploading ? (
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              )}
            </button>

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
      <div className="flex flex-col shrink-0 md:flex-1 bg-slate-50 overflow-hidden" style={{ height: 'calc(100vh - 64px)' }}>
        <div className="px-4 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-slate-700">Output</p>
            {currentReview && !reviewStale && (
              <VerdictBadge verdict={currentReview.verdict} />
            )}
            {currentReview && reviewStale && (
              <span className="inline-flex items-center gap-1 rounded-full border border-yellow-200 bg-yellow-50 px-2 py-0.5 text-xs font-medium text-yellow-700">
                <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
                Edited — review out of date
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <PresenceDots users={presence.users} myUserId={presence.myIdentity.userId} />
            <div className="flex rounded-lg border border-slate-200 overflow-hidden">
              <button
                onClick={() => setViewMode('edit')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${viewMode === 'edit' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'}`}
              >
                Edit
              </button>
              <button
                onClick={() => setViewMode('preview')}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${viewMode === 'preview' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-700'}`}
              >
                Preview
              </button>
            </div>
            {currentHtml && (
              <button
                onClick={exportPdf}
                disabled={exporting}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50"
              >
                {exporting ? 'Exporting…' : 'Export PDF'}
              </button>
            )}
            {viewMode === 'edit' && (
              <button
                onClick={() => setViewMode('preview')}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors"
              >
                Done
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          {!currentHtml ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-slate-400 px-8">
              <svg className="h-12 w-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-sm">Generated content will appear here.</p>
            </div>
          ) : (
            <>
              <div className="flex-1 overflow-hidden flex flex-row">
                <div className="flex-1 overflow-hidden" ref={outputPaneRef}>
                  {viewMode === 'preview' && (
                    <div
                      className="w-full h-full overflow-y-auto bg-slate-200 relative"
                      onMouseMove={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect()
                        const x = (e.clientX - rect.left) / rect.width
                        const y = (e.clientY - rect.top + e.currentTarget.scrollTop) / e.currentTarget.scrollHeight
                        throttledBroadcastCursor(x, y, null)
                      }}
                      onMouseLeave={() => presence.broadcastCursor(-1, -1, null)}
                    >
                      {parseSlides(currentHtml).map((slideHtml, i) => (
                        <SlidePreview key={`${i}-${slideHtml.length}-${slideHtml.slice(0, 80)}`} html={slideHtml} paneH={paneH} />
                      ))}
                      {Array.from(presence.cursors.entries()).map(([userId, cursor], idx) => {
                        if (cursor.x < 0 || cursor.y < 0) return null
                        return (
                          <RemoteCursor
                            key={userId}
                            name={cursor.display_name}
                            x={cursor.x}
                            y={cursor.y}
                            color={CURSOR_COLORS[idx % CURSOR_COLORS.length]}
                          />
                        )
                      })}
                    </div>
                  )}
                  {viewMode === 'edit' && (
                    <div className="w-full h-full overflow-y-auto bg-slate-200">
                      {parseSlides(currentHtml).map((slideHtml, i) => {
                        const remoteEditor = presence.users.find(
                          (u) => u.user_id !== presence.myIdentity.userId && u.editing_slide === i
                        ) ?? null
                        return (
                          <EditableSlide
                            key={`${i}-${slideHtml.length}-${slideHtml.slice(0, 80)}`}
                            html={slideHtml}
                            paneH={paneH}
                            slideIndex={i}
                            remoteEditor={remoteEditor}
                            onFocusSlide={(idx) => presence.startEditing(idx)}
                            onBlurSlide={() => presence.stopEditing()}
                            onSave={(updated) => {
                              const all = parseSlides(currentHtml)
                              const before = all.join('')
                              all[i] = updated
                              const after = all.join('')
                              setCurrentHtml(after)
                              if (after !== before) {
                                if (currentReview) setReviewStale(true)
                                presence.broadcastSlideSave(i, updated)
                              }
                            }}
                          />
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Version trail */}
                {versions.length > 0 && (
                  <div ref={versionTrailRef} className="flex-shrink-0 w-8 flex flex-col items-center justify-center border-l border-slate-100 bg-white relative">
                    {/* Ghost dot that animates up the trail on restore */}
                    {ghostY !== null && (
                      <div
                        ref={ghostRef}
                        style={{
                          position: 'absolute',
                          top: ghostY,
                          left: '50%',
                          transform: 'translateX(-50%)',
                          width: '10px',
                          height: '10px',
                          borderRadius: '50%',
                          backgroundColor: '#4f46e5',
                          transition: 'top 420ms cubic-bezier(0.4, 0, 0.2, 1)',
                          zIndex: 30,
                          pointerEvents: 'none',
                        }}
                      />
                    )}
                    {/* Popover — rendered outside scroll container to avoid clipping */}
                    {selectedVersionIdx !== null && versions[selectedVersionIdx] && (
                      <div className="absolute right-full top-1/2 -translate-y-1/2 mr-2 w-52 rounded-xl border border-slate-200 bg-white shadow-xl p-3 z-20 space-y-2">
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">v{selectedVersionIdx + 1}</p>
                        <p className="text-xs text-slate-700 line-clamp-3 leading-relaxed">{versions[selectedVersionIdx].prompt}</p>
                        {selectedVersionIdx === activeVersionIdx ? (
                          <p className="text-[10px] font-semibold text-indigo-600">Current version</p>
                        ) : (
                          <button
                            onClick={async () => {
                              const idx = selectedVersionIdx
                              const v = versions[idx]
                              setCurrentHtml(v.html)
                              setEditContent(v.html)
                              setCurrentReview(v.review)
                              setSelectedVersionIdx(null)
                              setRestoringIdx(idx)

                              // Persist restore to DB so it survives refresh
                              api.chat.restore(Number(id), v.html, v.review, v.prompt).then((saved) => {
                                setMessages((prev) => [...prev, { role: 'assistant', content: saved.content }])
                              }).catch(console.error)

                              // Measure start Y of the restoring dot relative to trail container
                              const btn = dotRefs.current.get(idx)
                              const trail = versionTrailRef.current
                              const scroll = innerScrollRef.current
                              if (btn && trail && scroll) {
                                const btnRect = btn.getBoundingClientRect()
                                const trailRect = trail.getBoundingClientRect()
                                const scrollRect = scroll.getBoundingClientRect()
                                const startY = btnRect.top - trailRect.top + btn.offsetHeight / 2 - 5
                                const targetY = scrollRect.top - trailRect.top + 16
                                setGhostY(startY)
                                setTimeout(() => {
                                  if (ghostRef.current) ghostRef.current.style.top = targetY + 'px'
                                }, 20)
                              }

                              setTimeout(() => {
                                setVersions((prev) => {
                                  const next = [...prev.filter((_, i) => i !== idx), { ...prev[idx], prompt: 'Restored version' }]
                                  setActiveVersionIdx(next.length - 1)
                                  return next
                                })
                                setRestoringIdx(null)
                                setGhostY(null)
                              }, 480)
                            }}
                            className="w-full rounded-lg bg-indigo-600 px-2 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors"
                          >
                            Restore
                          </button>
                        )}
                      </div>
                    )}
                    {/* Scrollable dots */}
                    <div
                      ref={innerScrollRef}
                      className="flex flex-col items-center gap-4 py-4 overflow-y-auto"
                      style={{ maxHeight: '160px', scrollbarWidth: 'none' }}
                    >
                      {[...versions].map((v, i) => ({ v, i })).reverse().map(({ v, i }) => (
                        <button
                          key={i}
                          ref={(el) => { if (el) dotRefs.current.set(i, el); else dotRefs.current.delete(i) }}
                          onClick={() => setSelectedVersionIdx(selectedVersionIdx === i ? null : i)}
                          title={`v${i + 1}`}
                          className={`flex-shrink-0 rounded-full transition-all duration-300 ${
                            i === restoringIdx
                              ? 'h-2.5 w-2.5 opacity-0'
                              : i === activeVersionIdx
                              ? 'h-3 w-3 bg-indigo-600 border-2 border-blue-400'
                              : 'h-2.5 w-2.5 bg-slate-300 hover:bg-slate-400'
                          }`}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {currentReview && (
                <div className="border-t border-slate-200 bg-white flex-shrink-0">
                  <button
                    onClick={() => setReviewOpen((v) => !v)}
                    className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                      </svg>
                      Compliance Review
                    </span>
                    <svg className={`h-3.5 w-3.5 transition-transform ${reviewOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {reviewOpen && (
                    <div className="px-4 pb-4 space-y-4 max-h-96 overflow-y-auto">
                      {/* Summary */}
                      <p className="text-xs text-slate-500">{currentReview.summary}</p>

                      {/* Review Agent Findings (soft checks) */}
                      {(currentReview.soft_checks?.flags?.length ?? 0) > 0 && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Review Agent Findings</p>
                          <ul className="space-y-2">
                            {currentReview.soft_checks!.flags.map((flag, i) => (
                              <li key={i} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs space-y-1">
                                <div className="flex items-start justify-between gap-2">
                                  <p className="text-slate-700 font-medium flex-1">{flag.claim}</p>
                                  <StatusChip status={flag.status} />
                                </div>
                                <p className="text-slate-400">{flag.note}</p>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Claim Traceability */}
                      {(currentReview.trace?.length ?? 0) > 0 && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Claim Traceability</p>
                          <ul className="space-y-2">
                            {currentReview.trace!.map((entry, i) => (
                              <li key={i} className="rounded-lg border border-slate-100 bg-blue-50/50 px-3 py-2 text-xs space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="inline-flex items-center rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                                    Slide {entry.slide}
                                  </span>
                                  <span className="text-slate-400 text-[10px]">{entry.element}</span>
                                </div>
                                <p className="text-slate-700">{entry.claim_text}</p>
                                {entry.source && (
                                  <p className="text-slate-400 italic">Source: {entry.source}</p>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Legacy top-level flags fallback */}
                      {currentReview.flags.length > 0 && !(currentReview.soft_checks?.flags?.length) && (
                        <ul className="space-y-2">
                          {currentReview.flags.map((flag, i) => (
                            <li key={i} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs space-y-1">
                              <div className="flex items-start justify-between gap-2">
                                <p className="text-slate-700 font-medium flex-1">{flag.claim}</p>
                                <StatusChip status={flag.status} />
                              </div>
                              <p className="text-slate-400">{flag.note}</p>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

    </div>
  )
}
