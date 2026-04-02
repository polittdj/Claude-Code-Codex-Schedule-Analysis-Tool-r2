import React, { useState } from 'react'
import { useSession } from '../App.jsx'
import { runForensics } from '../api/client.js'

const SEVERITY_COLOR = {
  HIGH: '#fc8181',
  MEDIUM: '#d69e2e',
  LOW: '#63b3ed',
}

export default function FindingsPanel() {
  const { sessionId, versions } = useSession() || {}
  const [findings, setFindings] = useState(null)
  const [riskScore, setRiskScore] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState({})

  const analyze = async () => {
    if (!sessionId || !versions?.length) return
    setLoading(true)
    setError(null)
    try {
      const indices = versions.map((v) => v.version_index)
      const data = await runForensics(sessionId, indices)
      setFindings(data.findings || [])
      setRiskScore(data.manipulation_risk_score ?? null)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!versions || versions.length === 0) {
    return <div style={styles.empty}>Upload schedule files to run forensic analysis.</div>
  }

  const toggleExpand = (i) => setExpanded((prev) => ({ ...prev, [i]: !prev[i] }))

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <button style={styles.btn} onClick={analyze} disabled={loading}>
          {loading ? 'Analysing…' : 'Run Forensic Analysis'}
        </button>
        {riskScore != null && (
          <div style={styles.scoreRow}>
            <span style={styles.scoreLabel}>Manipulation Risk Score:</span>
            <span style={{ ...styles.score, color: riskScore > 0.5 ? '#fc8181' : riskScore > 0.2 ? '#d69e2e' : '#68d391' }}>
              {(riskScore * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      {error && <p style={styles.error}>{error}</p>}

      {findings !== null && findings.length === 0 && (
        <p style={styles.clean}>No manipulation patterns detected.</p>
      )}

      {findings && findings.length > 0 && (
        <div style={styles.list}>
          {findings
            .sort((a, b) => {
              const sev = { HIGH: 0, MEDIUM: 1, LOW: 2 }
              return (sev[a.severity] ?? 3) - (sev[b.severity] ?? 3)
            })
            .map((f, i) => (
              <div key={i} style={{ ...styles.card, borderLeftColor: SEVERITY_COLOR[f.severity] || '#718096' }}>
                <div style={styles.cardHeader} onClick={() => toggleExpand(i)}>
                  <span style={{ ...styles.severity, color: SEVERITY_COLOR[f.severity] || '#718096' }}>
                    {f.severity}
                  </span>
                  <span style={styles.pattern}>{f.pattern}</span>
                  <span style={styles.confidence}>
                    {(f.confidence * 100).toFixed(0)}% confidence
                  </span>
                  <span style={styles.expandIcon}>{expanded[i] ? '▾' : '▸'}</span>
                </div>

                {expanded[i] && (
                  <div style={styles.cardBody}>
                    {f.affected_task_ids?.length > 0 && (
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Tasks:</span>
                        <span>{f.affected_task_ids.join(', ')}</span>
                      </div>
                    )}
                    {f.affected_link_pairs?.length > 0 && (
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Links:</span>
                        <span>{f.affected_link_pairs.map(([p, s]) => `${p}→${s}`).join(', ')}</span>
                      </div>
                    )}
                    <div style={styles.evidence}>{f.evidence}</div>
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', gap: '16px' },
  toolbar: { display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' },
  btn: { padding: '8px 16px', background: '#2b6cb0', border: 'none', borderRadius: '4px', color: '#fff', fontSize: '0.85rem', cursor: 'pointer' },
  scoreRow: { display: 'flex', alignItems: 'center', gap: '8px' },
  scoreLabel: { fontSize: '0.85rem', color: '#a0aec0' },
  score: { fontSize: '1.1rem', fontWeight: 700 },
  error: { color: '#fc8181', fontSize: '0.85rem' },
  clean: { color: '#68d391', fontSize: '0.85rem' },
  list: { display: 'flex', flexDirection: 'column', gap: '8px' },
  card: {
    background: '#1a1f2e',
    border: '1px solid #2d3748',
    borderLeft: '4px solid',
    borderRadius: '4px',
    overflow: 'hidden',
  },
  cardHeader: {
    display: 'flex', alignItems: 'center', gap: '10px',
    padding: '10px 14px', cursor: 'pointer',
  },
  severity: { fontSize: '0.75rem', fontWeight: 700, width: '52px', flexShrink: 0 },
  pattern: { flex: 1, fontSize: '0.875rem', color: '#e2e8f0', fontWeight: 500 },
  confidence: { fontSize: '0.75rem', color: '#718096' },
  expandIcon: { color: '#718096', fontSize: '0.85rem' },
  cardBody: { padding: '0 14px 12px', display: 'flex', flexDirection: 'column', gap: '6px' },
  detailRow: { display: 'flex', gap: '8px', fontSize: '0.8rem', color: '#a0aec0' },
  detailLabel: { color: '#718096', flexShrink: 0 },
  evidence: {
    fontSize: '0.8rem', color: '#a0aec0',
    background: '#0f1117', borderRadius: '4px',
    padding: '8px 10px', lineHeight: 1.5,
  },
  empty: { color: '#718096', padding: '40px', textAlign: 'center' },
}
