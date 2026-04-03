import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { createSession as apiCreateSession, endSession as apiEndSession } from './api/client.js'
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
  const [sessionError, setSessionError] = useState(null)
  const [sessionLoading, setSessionLoading] = useState(true)

  // Create session automatically on mount
  useEffect(() => {
    apiCreateSession()
      .then((data) => {
        setSessionId(data.session_id)
        setSessionLoading(false)
      })
      .catch((err) => {
        setSessionError('Could not connect to server: ' + (err.message || String(err)))
        setSessionLoading(false)
      })
  }, [])

  const endSession = useCallback(async () => {
    if (!sessionId) return
    try {
      await apiEndSession(sessionId)
    } catch (_) {}
    // Create a fresh session immediately
    try {
      const data = await apiCreateSession()
      setSessionId(data.session_id)
      setVersions([])
      setCpmResults({})
      setFocalTaskId(null)
    } catch (err) {
      setSessionError('Could not create new session: ' + err.message)
    }
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

  if (sessionLoading) {
    return (
      <div style={styles.loading}>
        <p>Connecting to Schedule Forensics server...</p>
        <p style={styles.hint}>Make sure start_windows.bat is running</p>
      </div>
    )
  }

  if (sessionError) {
    return (
      <div style={styles.loading}>
        <p style={{ color: '#fc8181' }}>{sessionError}</p>
        <p style={styles.hint}>Close this page, check the black terminal window, then refresh</p>
      </div>
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
          <div>
            <h1 style={styles.title}>Schedule Forensics Tool</h1>
            <p style={styles.subtitle}>Local-only · Zero data leaves your machine</p>
          </div>
          <SessionEndButton />
        </header>

        <div style={styles.sidebar}>
          {/* Upload always visible in sidebar */}
          <div style={styles.uploadSection}>
            <h3 style={styles.sectionHeading}>Upload .mpp Files</h3>
            <UploadPanel />
          </div>
          <VersionTimeline />
          <FocalTaskSelector />
        </div>

        <main style={styles.main}>
          {versions.length === 0 ? (
            <div style={styles.emptyMain}>
              <p style={styles.emptyText}>Upload a .mpp schedule file using the panel on the left to get started.</p>
            </div>
          ) : (
            <>
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
            </>
          )}
        </main>
      </div>
    </SessionContext.Provider>
  )
}

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
  title: { margin: 0, fontSize: '1.2rem', fontWeight: 600, color: '#63b3ed' },
  subtitle: { margin: '2px 0 0', fontSize: '0.7rem', color: '#718096' },
  sidebar: {
    gridArea: 'sidebar',
    background: '#1a1f2e',
    borderRight: '1px solid #2d3748',
    padding: '12px',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  uploadSection: {},
  sectionHeading: {
    fontSize: '0.75rem',
    textTransform: 'uppercase',
    color: '#718096',
    margin: '0 0 6px',
    letterSpacing: '0.05em',
  },
  main: {
    gridArea: 'main',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  emptyMain: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: { color: '#718096', fontSize: '1rem', textAlign: 'center' },
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
  tabActive: { background: '#2b6cb0', color: '#fff' },
  tabContent: { flex: 1, overflow: 'auto', padding: '16px' },
  loading: {
    minHeight: '100vh',
    background: '#0f1117',
    color: '#e2e8f0',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'system-ui, sans-serif',
    gap: '12px',
  },
  hint: { color: '#718096', fontSize: '0.85rem' },
}
