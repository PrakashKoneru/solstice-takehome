const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error ?? `API error ${res.status}`)
  }
  return res.json()
}

async function upload<T>(path: string, formData: FormData, method = 'POST'): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method, body: formData })
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

export type SlideTemplate = {
  name: string
  description: string
  layout: string
  bestFor: string
}

export type DesignSystem = {
  id: number
  name: string
  pdf_filename: string
  tokens: DesignTokens
  brand_guidelines: BrandGuidelines
  slide_templates: SlideTemplate[]
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
  source: 'raster' | 'page_render'
  created_at: string
}

export type KnowledgeItem = {
  id: number
  title: string
  filename: string
  doc_type: string
  created_at: string
  updated_at: string
}

export type ReviewFlag = {
  claim: string
  status: 'verified' | 'unsupported' | 'inferred'
  note: string
}

export type ReviewReport = {
  verdict: 'approved' | 'flagged' | 'blocked'
  confidence: number
  flags: ReviewFlag[]
  summary: string
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
    restore: (sessionId: number, htmlContent: string, reviewReport: ReviewReport | null) =>
      request<Message>(`/api/sessions/${sessionId}/restore`, {
        method: 'POST',
        body: JSON.stringify({ html_content: htmlContent, review_report: reviewReport }),
      }),
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
  },
}
