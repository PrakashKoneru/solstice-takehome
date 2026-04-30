const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (err) {
    // Convert low-level network errors (fetch TypeErrors) into a regular
    // Error so callers can handle them uniformly and the Next.js dev
    // overlay doesn't treat them as unhandled TypeErrors.
    throw new Error(`Network error: ${err instanceof Error ? err.message : 'unknown'} (${path})`)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error ?? `API error ${res.status}`)
  }
  return res.json()
}

async function upload<T>(path: string, formData: FormData, method = 'POST'): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { method, body: formData })
  } catch (err) {
    throw new Error(`Network error: ${err instanceof Error ? err.message : 'unknown'} (${path})`)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error ?? `API error ${res.status}`)
  }
  return res.json()
}

export type Session = {
  id: number
  title: string
  selected_ds_id: number | null
  selected_doc_ids: number[]
  created_at: string
  updated_at: string
}

export type DesignTokens = {
  colors?: {
    palette?: { primary?: string; secondary?: string }
    fill?: { default?: string; subtle?: string }
    border?: { default?: string; strong?: string }
    text?: { default?: string; muted?: string; inverse?: string }
    brand?: { primary?: string; secondary?: string }
    state?: { success?: string; error?: string; warning?: string; highlight?: string }
  }
  fonts?: Record<string, string>
  fontSizes?: Record<string, string>
  fontWeights?: Record<string, string>
  lineHeight?: Record<string, string>
  grid?: { columns?: number; gutter?: string; margin?: string }
  spacing?: Record<string, string>
  breakpoints?: Record<string, string>
  shadows?: Record<string, string>
  borderRadius?: Record<string, string>
  components?: { cta?: { background?: string; text?: string; borderRadius?: string; border?: string } }
}

export type BrandGuidelines = {
  personality?: string[]
  primaryFont?: string
  secondaryFont?: string
  fontUsageRule?: string
  colorHierarchy?: string
  layoutPrinciples?: string
  tone?: string
  requiredElements?: string[]
  prohibited?: string[]
  hallmark?: string
  supportedAudiences?: string[]
  audienceRules?: Record<string, { rules: string[] }>
  otherRelevantGuidelines?: Record<string, { rules: string[] }>
}

export type DesignSystem = {
  id: number
  name: string
  pdf_filename: string
  tokens: DesignTokens
  brand_guidelines: BrandGuidelines
  component_patterns: Record<string, any>
  extraction_status: string
  extraction_step: string | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export type DesignSystemAsset = {
  id: number
  design_system_id: number
  name: string
  asset_type: 'icon' | 'logo' | 'image'
  file_url: string
  filename: string
  source: string
  page_number: number | null
  created_at: string
}

export type KnowledgeItem = {
  id: number
  title: string
  filename: string
  doc_type: string
  extraction_status?: 'pending' | 'extracting' | 'complete' | 'failed'
  total_pages?: number | null
  claim_count?: number
  created_at: string
  updated_at: string
}

export type Claim = {
  id: string
  knowledge_id: number
  text: string
  claim_type: string
  source_citation: string | null
  page_number: number | null
  numeric_values: { value: string; unit?: string; label: string }[]
  tags: string[]
  section?: string
  section_hierarchy?: string[]
  is_approved: boolean
  created_at: string
}

export type ReviewFlag = {
  claim: string
  status: 'verified' | 'unsupported' | 'inferred'
  note: string
}

export type TraceEntry = {
  slide: number
  element: string
  claim_id: string
  claim_text: string
  source: string
}

export type ReviewReport = {
  verdict: 'approved' | 'flagged' | 'blocked'
  confidence: number
  flags: ReviewFlag[]
  summary: string
  trace?: TraceEntry[]
  soft_checks?: {
    flags: ReviewFlag[]
    summary?: string
  }
}

export type Message = {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  html_content: string | null
  review_report: ReviewReport | null
  created_at: string
}

export const api = {
  sessions: {
    list: ()                            => request<Session[]>('/api/sessions/'),
    create: (title: string)             => request<Session>('/api/sessions/', { method: 'POST', body: JSON.stringify({ title }) }),
    update: (id: number, patch: { title?: string; selected_ds_id?: number | null; selected_doc_ids?: number[] }) =>
      request<Session>(`/api/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
    delete: (id: number)                => request<{ deleted: number }>(`/api/sessions/${id}`, { method: 'DELETE' }),
  },
  knowledge: {
    list: ()                                                    => request<KnowledgeItem[]>('/api/knowledge/'),
    upload: (file: File, title: string, docType: string)       => {
      const fd = new FormData(); fd.append('file', file); fd.append('title', title); fd.append('doc_type', docType)
      return upload<KnowledgeItem>('/api/knowledge/upload', fd)
    },
    update: (id: number, title?: string, docType?: string, file?: File | null) => {
      const fd = new FormData()
      if (title)   fd.append('title', title)
      if (docType) fd.append('doc_type', docType)
      if (file)    fd.append('file', file)
      return upload<KnowledgeItem>(`/api/knowledge/${id}`, fd, 'PATCH')
    },
    delete: (id: number)                                        => request<{ deleted: number }>(`/api/knowledge/${id}`, { method: 'DELETE' }),
    listClaims: (id: number, params?: { claim_type?: string; is_approved?: boolean }) => {
      const qs = new URLSearchParams()
      if (params?.claim_type) qs.set('claim_type', params.claim_type)
      if (params?.is_approved !== undefined) qs.set('is_approved', String(params.is_approved))
      const q = qs.toString()
      return request<Claim[]>(`/api/knowledge/${id}/claims${q ? '?' + q : ''}`)
    },
    updateClaim: (itemId: number, claimId: string, patch: Partial<Pick<Claim, 'text' | 'is_approved' | 'claim_type' | 'tags'>>) =>
      request<Claim>(`/api/knowledge/${itemId}/claims/${claimId}`, { method: 'PATCH', body: JSON.stringify(patch) }),
    deleteClaim: (itemId: number, claimId: string) =>
      request<{ deleted: string }>(`/api/knowledge/${itemId}/claims/${claimId}`, { method: 'DELETE' }),
  },
  designSystem: {
    list: ()                  => request<DesignSystem[]>('/api/design-system/'),
    get: (id: number)         => request<DesignSystem>(`/api/design-system/${id}`),
    delete: (id: number)      => request<{ deleted: number }>(`/api/design-system/${id}`, { method: 'DELETE' }),
    setDefault: (id: number)  => request<DesignSystem>(`/api/design-system/${id}/set-default`, { method: 'PATCH' }),
    upload: (file: File, name: string) => {
      const fd = new FormData(); fd.append('file', file); fd.append('name', name)
      return upload<DesignSystem>('/api/design-system/upload', fd)
    },
    listAssets: (id: number)  => request<DesignSystemAsset[]>(`/api/design-system/${id}/assets`),
    deleteAsset: (dsId: number, assetId: number) =>
      request<{ deleted: number }>(`/api/design-system/${dsId}/assets/${assetId}`, { method: 'DELETE' }),
    uploadAsset: (dsId: number, file: File, name: string, assetType: string) => {
      const fd = new FormData(); fd.append('file', file); fd.append('name', name); fd.append('asset_type', assetType)
      return upload<DesignSystemAsset>(`/api/design-system/${dsId}/assets`, fd)
    },
  },
  chat: {
    list: (sessionId: number) =>
      request<Message[]>(`/api/sessions/${sessionId}/messages`),
    restore: (sessionId: number, htmlContent: string, reviewReport: ReviewReport | null, originalPrompt?: string) =>
      request<Message>(`/api/sessions/${sessionId}/restore`, {
        method: 'POST',
        body: JSON.stringify({ html_content: htmlContent, review_report: reviewReport, original_prompt: originalPrompt ?? '' }),
      }),
    rerunReview: (sessionId: number, html: string) =>
      request<ReviewReport>(`/api/sessions/${sessionId}/review`, {
        method: 'POST',
        body: JSON.stringify({ html }),
      }),
    export: (sessionId: number, msgId: number) =>
      request<{ html_content: string; review_report: ReviewReport | null; prompt: string; generated_at: string }>(
        `/api/sessions/${sessionId}/messages/${msgId}/export`
      ),
    send: (
      sessionId: number,
      prompt: string,
      dsId?: number | '',
      kbDocIds?: number[],
      mode: 'chat' | 'generate' | 'auto' = 'chat',
      currentDraft?: string | null,
      targetAudience?: string,
    ) =>
      request<Message>(`/api/sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          prompt,
          design_system_id: dsId || null,
          kb_doc_ids: kbDocIds ?? [],
          mode,
          current_draft: currentDraft ?? null,
          target_audience: targetAudience ?? null,
        }),
      }),

    sendStream: (
      sessionId: number,
      prompt: string,
      callbacks: {
        onStatus?: (step: string) => void
        onSlideReady?: (index: number, layout: string, title: string) => void
        onHtmlChunk?: (chunk: string) => void
        onHtmlComplete?: (html: string) => void
        onReview?: (report: ReviewReport) => void
        onChat?: (text: string) => void
        onDone?: (message: Message | null) => void
      },
      dsId?: number | '',
      kbDocIds?: number[],
      currentDraft?: string | null,
      targetAudience?: string,
    ) => {
      const controller = new AbortController()
      const promise = (async () => {
        const res = await fetch(`${BASE}/api/sessions/${sessionId}/messages/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt,
            design_system_id: dsId || null,
            kb_doc_ids: kbDocIds ?? [],
            current_draft: currentDraft ?? null,
            target_audience: targetAudience ?? null,
          }),
          signal: controller.signal,
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.error ?? `API error ${res.status}`)
        }
        const reader = res.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const parts = buffer.split('\n\n')
          buffer = parts.pop() || ''

          for (const part of parts) {
            const lines = part.split('\n')
            let event = ''
            let data = ''
            for (const line of lines) {
              if (line.startsWith('event: ')) event = line.slice(7)
              else if (line.startsWith('data: ')) data = line.slice(6)
            }
            if (!event || !data) continue
            const parsed = JSON.parse(data)

            switch (event) {
              case 'status':
                callbacks.onStatus?.(parsed.step)
                break
              case 'slide_ready':
                callbacks.onSlideReady?.(parsed.index, parsed.layout, parsed.title)
                break
              case 'html_chunk':
                callbacks.onHtmlChunk?.(parsed.chunk)
                break
              case 'html_complete':
                callbacks.onHtmlComplete?.(parsed.html)
                break
              case 'review':
                callbacks.onReview?.(parsed.review_report)
                break
              case 'chat':
                callbacks.onChat?.(parsed.text)
                break
              case 'done':
                // Only pass through the message if the server actually
                // committed one (generate/edit success paths). Error
                // paths emit a bare `done` event with no message key.
                callbacks.onDone?.(parsed.message ?? null)
                break
            }
          }
        }
      })()
      return { promise, abort: () => controller.abort() }
    },
  },
}
