import React from 'react'
import { useSession } from '../App.jsx'

export default function VersionTimeline() {
  const { versions, cpmResults } = useSession() || {}

  if (!versions || versions.length === 0) {
    return (
      <div style={styles.empty}>
        <p>No versions loaded yet.</p>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <h3 style={styles.heading}>Versions ({versions.length})</h3>
      <ul style={styles.list}>
        {versions.map((v) => {
          const cpm = cpmResults?.[v.version_index]
          return (
            <li key={v.version_index} style={styles.item}>
              <div style={styles.badge}>v{v.version_index}</div>
              <div style={styles.info}>
                <div style={styles.filename} title={v.filename}>
                  {v.filename}
                </div>
                {v.status_date && (
                  <div style={styles.meta}>Status: {v.status_date}</div>
                )}
                <div style={styles.meta}>
                  {v.task_count} tasks · {v.link_count} links
                </div>
                {cpm && (
                  <div style={styles.meta}>
                    CP: {cpm.critical_path?.length ?? '—'} tasks ·{' '}
                    {cpm.project_duration_days?.toFixed(0) ?? '—'}d
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const styles = {
  container: { marginBottom: '24px' },
  heading: { fontSize: '0.8rem', textTransform: 'uppercase', color: '#718096', margin: '0 0 8px', letterSpacing: '0.05em' },
  list: { listStyle: 'none', padding: 0, margin: 0 },
  item: { display: 'flex', gap: '10px', padding: '8px 0', borderBottom: '1px solid #2d3748' },
  badge: {
    flexShrink: 0,
    width: '32px', height: '32px',
    borderRadius: '50%',
    background: '#2b6cb0',
    color: '#fff',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: '0.75rem', fontWeight: 700,
  },
  info: { flex: 1, overflow: 'hidden' },
  filename: { fontSize: '0.8rem', color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { fontSize: '0.7rem', color: '#718096', marginTop: '2px' },
  empty: { color: '#718096', fontSize: '0.8rem' },
}
