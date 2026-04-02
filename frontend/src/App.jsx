import React, { createContext, useContext, useState, useCallback } from 'react'
import { createSession, endSession as apiEndSession } from './api/client.js'
import UploadPanel from './components/UploadPanel.jsx'
import VersionTimeline from './components/VersionTimeline.jsx'
import FocalTaskSelector from './components/FocalTaskSelector.jsx'
import SessionEndButton from './components/SessionEndButton.jsx'
import GanttChart from './components/GanttChart.jsx'
import LogicTraceGraph from './components/LogicTraceGraph.jsx'
import DiffView from './components/DiffView.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import FindingsPanel from './components/FindingsPanel.jsx'

// ── Session Context ───────────────────────────────────────────────────────────

export const SessionContext = createContext(null)

export function useSession() {
  return useContext(SessionContext)
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [sessionId, setSessionId] = useState(null)
  const [versions, setVersions] = useState([])
  const [cpmResults, setCpmResults] = useState({})
  const [focalTaskId, setFocalTaskId] = useState(null)
  const [activeTab, setActiveTab] = useState('gantt')
  const [error, setError] = useState(null)

  const initSession = useCallback(async () => {
    try {
      const session = await createSession()
      setSessionId(session.session_id)
      setVersions([])
      setCpmResults({})
      setFocalTaskId(null)
      setError(null)
    } catch (err) {
      setError('Failed to create session: ' + (err.message || String(err)))
    }
  }, [])

  const endSession = useCallback(async () => {
    if (!sessionId) return
    try {
      await apiEndSession(sessionId)
    } catch (_) {
      // Ignore errors on end — wipe state regardless
    }
    setSessionId(null)
    setVersions([])
    setCpmResults({})
    setFocalTaskId(null)
    setError(null)
  }, [sessionId])

  const ctx = {
    sessionId,
    versions,
    setVersions,
    cpmResults,
    setCpmResults,
    focalTaskId,
    setFocalTaskId,
    endSession,
  }

  // Before session is created — show upload panel
  if (!sessionId) {
    return (
      <SessionContext.Provider value={ctx}>
        <div style={styles.root}>
          <header style={styles.header}>
            <h1 style={styles.title}>Schedule Forensics Tool</h1>
            <p style={styles.subtitle}>Local-only · Zero data leaves your machine</p>
          </header>
          {error && <div style={styles.error}>{error}</div>}
          <UploadPanel onSessionReady={initSession} />
        </div>
      </SessionContext.Provider>
    )
  }

  const tabs = [
    { id: 'gantt', label: 'Gantt' },
    { id: 'logic', label: 'Logic Graph' },
    { id: 'diff', label: 'Diff' },
    { id: 'chat', label: 'Ask the Schedule' },
    { id: 'findings', label: 'Findings' },
  ]

  return (
    <SessionContext.Provider value={ctx}>
      <div style={styles.root}>
        <header style={styles.header}>
          <h1 style={styles.title}>Schedule Forensics Tool</h1>
          <SessionEndButton />
        </header>

        <div style={styles.sidebar}>
          <VersionTimeline />
          <FocalTaskSelector />
        </div>

        <main style={styles.main}>
          <nav style={styles.tabBar}>
            {tabs.map((t) => (
              <button
                key={t.id}
                style={{ ...styles.tab, ...(activeTab === t.id ? styles.tabActive : {}) }}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div style={styles.tabContent}>
            {activeTab === 'gantt' && <GanttChart />}
            {activeTab === 'logic' && <LogicTraceGraph />}
            {activeTab === 'diff' && <DiffView />}
            {activeTab === 'chat' && <ChatPanel />}
            {activeTab === 'findings' && <FindingsPanel />}
          </div>
        </main>
      </div>
    </SessionContext.Provider>
  )
}

// ── Inline styles (no CSS file dependency) ────────────────────────────────────

const styles = {
  root: {
    fontFamily: 'system-ui, sans-serif',
    minHeight: '100vh',
    background: '#0f1117',
    color: '#e2e8f0',
    display: 'grid',
    gridTemplateAreas: '"header header" "sidebar main"',
    gridTemplateColumns: '280px 1fr',
    gridTemplateRows: 'auto 1fr',
  },
  header: {
    gridArea: 'header',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 24px',
    background: '#1a1f2e',
    borderBottom: '1px solid #2d3748',
  },
  title: {
    margin: 0,
    fontSize: '1.2rem',
    fontWeight: 600,
    color: '#63b3ed',
  },
  subtitle: {
    margin: '4px 0 0',
    fontSize: '0.75rem',
    color: '#718096',
  },
  error: {
    gridColumn: '1/-1',
    background: '#742a2a',
    color: '#fed7d7',
    padding: '10px 24px',
    fontSize: '0.875rem',
  },
  sidebar: {
    gridArea: 'sidebar',
    background: '#1a1f2e',
    borderRight: '1px solid #2d3748',
    padding: '16px',
    overflowY: 'auto',
  },
  main: {
    gridArea: 'main',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  tabBar: {
    display: 'flex',
    gap: '4px',
    padding: '8px 16px',
    background: '#1a1f2e',
    borderBottom: '1px solid #2d3748',
  },
  tab: {
    padding: '6px 14px',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '0.85rem',
    background: 'transparent',
    color: '#a0aec0',
  },
  tabActive: {
    background: '#2b6cb0',
    color: '#fff',
  },
  tabContent: {
    flex: 1,
    overflow: 'auto',
    padding: '16px',
  },
}
