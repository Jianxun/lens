import type { FormEvent } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './App.css'
import { createSession, fetchSession, fetchSessions, streamChat } from './api'
import type { ChatMetadata, ChatRequestMessage, SessionDetail, SessionMessage, SessionSummary } from './types'

function formatDate(value: string) {
  try {
    const date = new Date(value)
    return date.toLocaleString()
  } catch {
    return value
  }
}

function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null)
  const [loadingSession, setLoadingSession] = useState(false)
  const [userInput, setUserInput] = useState('')
  const [optimisticMessages, setOptimisticMessages] = useState<SessionMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [streamingMetadata, setStreamingMetadata] = useState<ChatMetadata | null>(null)
  const [histogramOpen, setHistogramOpen] = useState(false)
  const lastMetadataRef = useRef<ChatMetadata | null>(null)

  const sortedMessages = useMemo(() => {
    if (!sessionDetail) return []
    return [...sessionDetail.messages].sort((a, b) => a.idx - b.idx)
  }, [sessionDetail])

  const displayMessages = useMemo(() => {
    const combined = [...sortedMessages, ...optimisticMessages]
    return combined.sort((a, b) => a.idx - b.idx)
  }, [optimisticMessages, sortedMessages])

  const loadSessions = async () => {
    try {
      const data = await fetchSessions()
      setSessions(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load sessions')
    }
  }

  useEffect(() => {
    void loadSessions()
  }, [])

  const openSession = async (id: string) => {
    setSelectedSessionId(id)
    setLoadingSession(true)
    setStreamingMetadata(null)
    setHistogramOpen(false)
    setOptimisticMessages([])
    try {
      const detail = await fetchSession(id)
      setSessionDetail(detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load session')
    } finally {
      setLoadingSession(false)
    }
  }

  const handleNewSession = async () => {
    setLoadingSession(true)
    setStreamingMetadata(null)
    setHistogramOpen(false)
    setOptimisticMessages([])
    try {
      const detail = await createSession()
      setSelectedSessionId(detail.id)
      setSessionDetail(detail)
      await loadSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create session')
    } finally {
      setLoadingSession(false)
    }
  }

  const handleSend = async (event?: FormEvent) => {
    event?.preventDefault()
    if (isStreaming) return

    const text = userInput.trim()
    if (!text) return

    const history: ChatRequestMessage[] = sortedMessages
      .filter((msg) => msg.role === 'user' || msg.role === 'assistant' || msg.role === 'system')
      .map((msg) => ({
        role: (msg.role as ChatRequestMessage['role']) ?? 'user',
        content: msg.content ?? '',
      }))

    const outgoing: ChatRequestMessage[] = [...history, { role: 'user', content: text }]

    const startIdx = (sortedMessages.at(-1)?.idx ?? -1) + 1
    const optimisticUser: SessionMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      create_time: new Date().toISOString(),
      idx: startIdx,
      conversation_id: sessionDetail?.conversation_id ?? 'pending',
    }
    const optimisticAssistant: SessionMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      create_time: new Date().toISOString(),
      idx: startIdx + 1,
      conversation_id: sessionDetail?.conversation_id ?? 'pending',
    }

    setOptimisticMessages([optimisticUser, optimisticAssistant])
    setIsStreaming(true)
    setError(null)
    setStreamingMetadata(null)
    lastMetadataRef.current = null

    try {
      await streamChat(
        {
          messages: outgoing,
          session_id: selectedSessionId ?? undefined,
        },
        {
          onToken: (token) => {
            setOptimisticMessages((msgs) =>
              msgs.map((msg) =>
                msg.role === 'assistant' ? { ...msg, content: `${msg.content ?? ''}${token}` } : msg,
              ),
            )
          },
          onMetadata: (metadata) => {
            lastMetadataRef.current = metadata
            setStreamingMetadata(metadata)
            setSelectedSessionId(metadata.session_id)
            setHistogramOpen(true)
          },
        },
      )

      const metadata = lastMetadataRef.current as ChatMetadata | null
      const targetSessionId = metadata?.session_id ?? selectedSessionId
      if (targetSessionId) {
        const detail = await fetchSession(targetSessionId)
        setSessionDetail(detail)
        await loadSessions()
      }

      setUserInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message')
    } finally {
      setIsStreaming(false)
      setOptimisticMessages([])
    }
  }

  const currentSessionTitle =
    sessionDetail?.title || sessions.find((s) => s.id === selectedSessionId)?.title || 'Untitled session'

  return (
    <div className="app-shell">
      <aside className="sessions-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Lens</p>
            <h2>Sessions</h2>
          </div>
          <div className="panel-actions">
            <button className="ghost" onClick={loadSessions} disabled={loadingSession}>
              Refresh
            </button>
            <button className="primary" onClick={handleNewSession} disabled={loadingSession || isStreaming}>
              New Session
            </button>
          </div>
        </div>

        <div className="session-list">
          {sessions.length === 0 && <p className="muted">No sessions yet. Create one to start chatting.</p>}
          {sessions.map((session) => {
            const isSelected = session.id === selectedSessionId
            return (
              <button
                key={session.id}
                className={`session-card ${isSelected ? 'selected' : ''}`}
                onClick={() => openSession(session.id)}
                disabled={loadingSession || isStreaming}
              >
                <div className="session-card__top">
                  <span className="session-title">{session.title || 'Untitled session'}</span>
                  {session.pinned && <span className="badge">Pinned</span>}
                  {session.archived && <span className="badge muted">Archived</span>}
                </div>
                <div className="session-card__meta">
                  <span>{session.message_count} messages</span>
                  <span>Updated {formatDate(session.updated_at)}</span>
                </div>
              </button>
            )
          })}
        </div>
      </aside>

      <main className="chat-panel">
        <header className="chat-header">
          <div>
            <p className="eyebrow">Chat</p>
            <h1>{currentSessionTitle}</h1>
            {sessionDetail && <p className="muted">Conversation ID: {sessionDetail.conversation_id}</p>}
          </div>
          <div className="metadata-actions">
            <button
              className="ghost"
              onClick={() => setHistogramOpen((prev) => !prev)}
              disabled={!streamingMetadata}
            >
              {histogramOpen ? 'Hide histogram' : 'Show histogram'}
            </button>
          </div>
        </header>

        <section className="messages" aria-live="polite">
          {loadingSession && <p className="muted">Loading session…</p>}
          {!loadingSession && displayMessages.length === 0 && (
            <p className="muted">No messages yet. Say hello to start.</p>
          )}
          {displayMessages.map((msg) => (
            <article key={msg.id} className={`message ${msg.role === 'user' ? 'user' : 'assistant'}`}>
              <div className="message-meta">
                <span className="bubble-role">{msg.role}</span>
                {msg.create_time && <span className="muted">{formatDate(msg.create_time)}</span>}
              </div>
              {msg.role === 'assistant' ? (
                <div className="message-body assistant">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ''}</ReactMarkdown>
                </div>
              ) : (
                <div className="message-body user">{msg.content || ''}</div>
              )}
            </article>
          ))}
        </section>

        {error && <div className="error">{error}</div>}

        {streamingMetadata && (
          <section className={`histogram ${histogramOpen ? 'open' : 'collapsed'}`}>
            <div className="histogram-header">
              <div>
                <p className="eyebrow">Context</p>
                <h3>Histogram & cited turns</h3>
                <p className="muted">
                  Total matches: {streamingMetadata.histogram.total} | Bin: {streamingMetadata.histogram.bin_days} day
                  {streamingMetadata.histogram.bin_days > 1 ? 's' : ''}
                </p>
              </div>
              <button className="ghost" onClick={() => setHistogramOpen((prev) => !prev)}>
                {histogramOpen ? 'Collapse' : 'Expand'}
              </button>
            </div>
            {histogramOpen && (
              <div className="histogram-body">
                <div className="buckets">
                  {streamingMetadata.histogram.buckets.length === 0 && (
                    <p className="muted">No histogram buckets returned.</p>
                  )}
                  {streamingMetadata.histogram.buckets.map((bucket) => (
                    <div key={`${bucket.start}-${bucket.end}`} className="bucket-row">
                      <div>
                        <div className="bucket-range">
                          {formatDate(bucket.start)} → {formatDate(bucket.end)}
                        </div>
                      </div>
                      <div className="bucket-count">{bucket.count}</div>
                    </div>
                  ))}
                </div>
                <div className="cited">
                  <p className="eyebrow">Cited turn IDs</p>
                  {streamingMetadata.cited_turn_ids.length === 0 && <p className="muted">None cited.</p>}
                  {streamingMetadata.cited_turn_ids.length > 0 && (
                    <ul>
                      {streamingMetadata.cited_turn_ids.map((id) => (
                        <li key={id} className="mono">
                          {id}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </section>
        )}

        <form className="composer" onSubmit={handleSend}>
          <textarea
            placeholder="Ask something..."
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            disabled={isStreaming || loadingSession}
            rows={3}
          />
          <div className="composer-actions">
            <button type="submit" className="primary" disabled={isStreaming || loadingSession}>
              {isStreaming ? 'Streaming…' : loadingSession ? 'Loading…' : 'Send'}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}

export default App
