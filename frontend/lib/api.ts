const BASE = 'http://localhost:5001'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) throw new Error(`API error ${res.status}`)
  return res.json()
}

export type Session = {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export const api = {
  sessions: {
    list: ()                          => request<Session[]>('/api/sessions/'),
    create: (title: string)           => request<Session>('/api/sessions/', { method: 'POST', body: JSON.stringify({ title }) }),
    update: (id: number, title: string) => request<Session>(`/api/sessions/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
    delete: (id: number)              => request<{ deleted: number }>(`/api/sessions/${id}`, { method: 'DELETE' }),
  },
}
