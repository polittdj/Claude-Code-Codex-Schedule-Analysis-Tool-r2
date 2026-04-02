import React, { useState } from 'react'
import { useSession } from '../App.jsx'
import { diffVersions } from '../api/client.js'

export default function DiffView() {
  const { sessionId, versions } = useSession() || {}
  const [baseIdx, setBaseIdx] = useState(0)
  const [compareIdx, setCompareIdx] = useState(1)
  const [diff, setDiff] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runDiff = async () => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      const data = await diffVersions(sessionId, baseIdx, compareIdx)
      setDiff(data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!versions || versions.length < 2) {
    return <div style={styles.empty}>Load at least 2 versions to compare.</div>
  }

  const versionOptions = versions.map((v) => (
    <option key={v.version_index} value={v.version_index}>
      v{v.version_index} — {v.filename}
    </option>
  ))

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <label style={styles.label}>
          Base:
          <select style={styles.select} value={baseIdx} onChange={(e) => setBaseIdx(Number(e.target.value))}>
            {versionOptions}
          </select>
        </label>
        <span style={styles.arrow}>→</span>
        <label style={styles.label}>
          Compare:
          <select style={styles.select} value={compareIdx} onChange={(e) => setCompareIdx(Number(e.target.value))}>
            {versionOptions}
          </select>
        </label>
        <button style={styles.btn} onClick={runDiff} disabled={loading || baseIdx === compareIdx}>
          {loading ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {error && <p style={styles.error}>{error}</p>}

      {diff && (
        <div style={styles.results}>
          <div style={styles.summary}>
            <span>
              {diff.task_changes?.filter((c) => c.change_type === 'added').length ?? 0} added
            </span>
            <span style={styles.removed}>
              {diff.task_changes?.filter((c) => c.change_type === 'removed').length ?? 0} removed
            </span>
            <span style={styles.modified}>
              {diff.task_changes?.filter((c) => c.change_type === 'modified').length ?? 0} modified
            </span>
            {diff.project_finish_delta_days != null && (
              <span style={diff.project_finish_delta_days > 0 ? styles.removed : styles.added}>
                Finish: {diff.project_finish_delta_days > 0 ? '+' : ''}
                {diff.project_finish_delta_days.toFixed(0)}d
              </span>
            )}
          </div>

          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Task ID</th>
                <th style={styles.th}>Change</th>
                <th style={styles.th}>Fields Changed</th>
              </tr>
            </thead>
            <tbody>
              {(diff.task_changes || []).map((c, i) => {
                const rowStyle =
                  c.change_type === 'added'
                    ? styles.rowAdded
                    : c.change_type === 'removed'
                    ? styles.rowRemoved
                    : styles.rowModified
                return (
                  <tr key={i} style={rowStyle}>
                    <td style={styles.td}>{c.unique_id}</td>
                    <td style={styles.td}>{c.change_type}</td>
                    <td style={styles.td}>
                      {Object.entries(c.field_changes || {})
                        .slice(0, 5)
                        .map(([field, [before, after]]) => (
                          <div key={field} style={styles.fieldChange}>
                            <span style={styles.fieldName}>{field}</span>
                            {': '}
                            <span style={styles.valueBefore}>{String(before ?? '—')}</span>
                            {' → '}
                            <span style={styles.valueAfter}>{String(after ?? '—')}</span>
                          </div>
                        ))}
                    </td>
                  </tr>
                )
              })}
              {(diff.task_changes || []).length === 0 && (
                <tr>
                  <td colSpan={3} style={{ ...styles.td, color: '#718096', textAlign: 'center' }}>
                    No task changes
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', gap: '16px' },
  toolbar: { display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' },
  label: { fontSize: '0.8rem', color: '#a0aec0', display: 'flex', alignItems: 'center', gap: '6px' },
  select: { background: '#2d3748', border: '1px solid #4a5568', color: '#e2e8f0', borderRadius: '4px', padding: '4px 8px', fontSize: '0.8rem' },
  arrow: { color: '#63b3ed', fontSize: '1.2rem' },
  btn: { padding: '6px 14px', background: '#2b6cb0', border: 'none', borderRadius: '4px', color: '#fff', fontSize: '0.85rem', cursor: 'pointer' },
  error: { color: '#fc8181', fontSize: '0.85rem' },
  results: { display: 'flex', flexDirection: 'column', gap: '12px' },
  summary: { display: 'flex', gap: '16px', fontSize: '0.85rem', color: '#68d391' },
  added: { color: '#68d391' },
  removed: { color: '#fc8181' },
  modified: { color: '#d69e2e' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' },
  th: { background: '#1a1f2e', color: '#a0aec0', padding: '6px 10px', textAlign: 'left', borderBottom: '1px solid #2d3748' },
  td: { padding: '5px 10px', borderBottom: '1px solid #2d3748', color: '#e2e8f0', verticalAlign: 'top' },
  rowAdded: { background: 'rgba(104, 211, 145, 0.06)' },
  rowRemoved: { background: 'rgba(252, 129, 129, 0.06)' },
  rowModified: { background: 'rgba(214, 158, 46, 0.06)' },
  fieldChange: { fontSize: '0.75rem', marginBottom: '2px' },
  fieldName: { color: '#a0aec0' },
  valueBefore: { color: '#fc8181' },
  valueAfter: { color: '#68d391' },
  empty: { color: '#718096', padding: '40px', textAlign: 'center' },
}
