export interface SessionSummary {
  id: string
  title?: string | null
  updated_at: string
  pinned: boolean
  archived: boolean
  message_count: number
}

export interface SessionMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | string
  content: string | null
  create_time: string | null
  idx: number
  conversation_id: string
}

export interface SessionDetail extends SessionSummary {
  created_at: string
  conversation_id: string
  messages: SessionMessage[]
}

export interface HistogramBucket {
  start: string
  end: string
  count: number
}

export interface Histogram {
  bin_days: number
  buckets: HistogramBucket[]
  total: number
}

export interface ChatMetadata {
  cited_turn_ids: string[]
  histogram: Histogram
  session_id: string
  conversation_id: string
  user_message_id: string
  assistant_message_id: string
}

export type ChatRole = 'user' | 'assistant' | 'system'

export interface ChatRequestMessage {
  role: ChatRole
  content: string
}

export interface ChatRequest {
  messages: ChatRequestMessage[]
  session_id?: string
  model?: string | null
  max_tokens?: number | null
  max_completion_tokens?: number | null
}

export interface StreamHandlers {
  onToken?: (token: string) => void
  onMetadata?: (metadata: ChatMetadata) => void
  onDone?: () => void
}

