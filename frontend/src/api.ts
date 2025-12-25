import type { ChatMetadata, ChatRequest, SessionDetail, SessionSummary, StreamHandlers } from './types'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function parseError(res: Response): Promise<Error> {
  try {
    const data = await res.json()
    const detail = data?.detail || data?.message || JSON.stringify(data)
    return new Error(`Request failed (${res.status}): ${detail}`)
  } catch {
    const fallback = await res.text()
    return new Error(`Request failed (${res.status}): ${fallback || res.statusText}`)
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    throw await parseError(res)
  }
  return (await res.json()) as T
}

export function fetchSessions(): Promise<SessionSummary[]> {
  return getJson<SessionSummary[]>('/sessions')
}

export function fetchSession(id: string): Promise<SessionDetail> {
  return getJson<SessionDetail>(`/sessions/${id}`)
}

export function createSession(title?: string): Promise<SessionDetail> {
  return getJson<SessionDetail>('/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: title ?? null }),
  })
}

export async function streamChat(request: ChatRequest, handlers: StreamHandlers = {}): Promise<void> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })

  if (!res.ok) {
    throw await parseError(res)
  }
  if (!res.body) {
    throw new Error('No response body received from chat endpoint')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const processBuffer = () => {
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary).trim()
      buffer = buffer.slice(boundary + 2)

      if (!raw.startsWith('data:')) {
        boundary = buffer.indexOf('\n\n')
        continue
      }

      const payload = raw.replace(/^data:\s*/, '')
      if (payload === '[DONE]') {
        handlers.onDone?.()
        boundary = buffer.indexOf('\n\n')
        continue
      }

      let parsed: any
      try {
        parsed = JSON.parse(payload)
      } catch {
        boundary = buffer.indexOf('\n\n')
        continue
      }

      const choice = parsed?.choices?.[0]
      const delta = choice?.delta ?? {}

      if (delta.content) {
        handlers.onToken?.(delta.content as string)
      }

      if (delta.metadata || choice?.finish_reason === 'metadata') {
        handlers.onMetadata?.((delta.metadata ?? {}) as ChatMetadata)
      }

      boundary = buffer.indexOf('\n\n')
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (value) {
      buffer += decoder.decode(value, { stream: !done })
      processBuffer()
    }
    if (done) {
      buffer += decoder.decode()
      processBuffer()
      break
    }
  }
}

