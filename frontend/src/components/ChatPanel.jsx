import React, { useRef, useState } from 'react'
import { useSession } from '../App.jsx'
import { chat } from '../api/client.js'

export default function ChatPanel() {
  const { sessionId } = useSession() || {}
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Ask me about the schedule. Try:\n• "What is driving [task ID]?"\n• "Show critical path for version 0"\n• "What changed between version 0 and 1?"\n• "What is the DCMA score for version 0?"\n• "Top float risks"\n• "Missing logic"\n• "Valid critical path"',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  const send = async () => {
    const query = input.trim()
    if (!query || !sessionId || loading) return

    setMessages((prev) => [...prev, { role: 'user', text: query }])
    setInput('')
    setLoading(true)

    try {
      const data = await chat(sessionId, query)
      setMessages((prev) => [...prev, { role: 'assistant', text: data.response_text || 'No response.' }])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: `Error: ${err.response?.data?.detail || err.message}` },
      ])
    } finally {
      setLoading(false)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.messages}>
        {messages.map((m, i) => (
          <div key={i} style={{ ...styles.bubble, ...(m.role === 'user' ? styles.userBubble : styles.aiBubble) }}>
            <pre style={styles.text}>{m.text}</pre>
          </div>
        ))}
        {loading && (
          <div style={{ ...styles.bubble, ...styles.aiBubble }}>
            <span style={styles.typing}>Thinking…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={styles.inputRow}>
        <textarea
          style={styles.textarea}
          rows={2}
          placeholder="Ask a question about the schedule…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={loading}
        />
        <button style={styles.sendBtn} onClick={send} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', minHeight: '400px', gap: '12px' },
  messages: { flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', padding: '4px' },
  bubble: { maxWidth: '85%', padding: '10px 14px', borderRadius: '8px' },
  userBubble: { alignSelf: 'flex-end', background: '#2b6cb0' },
  aiBubble: { alignSelf: 'flex-start', background: '#1a1f2e', border: '1px solid #2d3748' },
  text: { margin: 0, fontFamily: 'inherit', fontSize: '0.85rem', color: '#e2e8f0', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  typing: { color: '#718096', fontSize: '0.85rem', fontStyle: 'italic' },
  inputRow: { display: 'flex', gap: '8px', alignItems: 'flex-end' },
  textarea: {
    flex: 1, resize: 'none', padding: '8px 10px',
    background: '#1a1f2e', border: '1px solid #4a5568', borderRadius: '6px',
    color: '#e2e8f0', fontSize: '0.85rem',
  },
  sendBtn: {
    padding: '8px 16px', background: '#2b6cb0', border: 'none', borderRadius: '6px',
    color: '#fff', fontSize: '0.85rem', cursor: 'pointer', alignSelf: 'flex-end',
  },
}
