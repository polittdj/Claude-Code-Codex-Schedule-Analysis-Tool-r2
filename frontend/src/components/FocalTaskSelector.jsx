import React, { useState, useMemo } from 'react'
import { useSession } from '../App.jsx'

export default function FocalTaskSelector() {
  const { versions, focalTaskId, setFocalTaskId } = useSession() || {}
  const [query, setQuery] = useState('')

  const allTasks = useMemo(() => {
    if (!versions || versions.length === 0) return []
    const latest = versions[versions.length - 1]
    return (latest.tasks || []).filter((t) => !t.is_summary && !t.is_loe)
  }, [versions])

  const filtered = useMemo(() => {
    if (!query.trim()) return allTasks.slice(0, 50)
    const q = query.toLowerCase()
    return allTasks
      .filter(
        (t) =>
          t.unique_id.toLowerCase().includes(q) ||
          (t.name || '').toLowerCase().includes(q) ||
          (t.wbs || '').toLowerCase().includes(q)
      )
      .slice(0, 50)
  }, [query, allTasks])

  if (!versions || versions.length === 0) return null

  return (
    <div style={styles.container}>
      <h3 style={styles.heading}>Focal Task</h3>
      <input
        style={styles.input}
        placeholder="Search by ID, name, or WBS…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {filtered.length > 0 && (
        <ul style={styles.list}>
          {filtered.map((t) => (
            <li
              key={t.unique_id}
              style={{
                ...styles.item,
                ...(focalTaskId === t.unique_id ? styles.itemSelected : {}),
              }}
              onClick={() =>
                setFocalTaskId(t.unique_id === focalTaskId ? null : t.unique_id)
              }
            >
              <span style={styles.uid}>{t.unique_id}</span>
              <span style={styles.name}>{t.name}</span>
              {t.is_milestone && <span style={styles.milestoneBadge}>M</span>}
            </li>
          ))}
        </ul>
      )}
      {focalTaskId && (
        <button style={styles.clearBtn} onClick={() => setFocalTaskId(null)}>
          Clear focal task
        </button>
      )}
    </div>
  )
}

const styles = {
  container: { marginTop: '8px' },
  heading: {
    fontSize: '0.8rem',
    textTransform: 'uppercase',
    color: '#718096',
    margin: '0 0 8px',
    letterSpacing: '0.05em',
  },
  input: {
    width: '100%',
    padding: '6px 8px',
    boxSizing: 'border-box',
    background: '#2d3748',
    border: '1px solid #4a5568',
    borderRadius: '4px',
    color: '#e2e8f0',
    fontSize: '0.8rem',
  },
  list: {
    listStyle: 'none',
    padding: 0,
    margin: '6px 0 0',
    maxHeight: '200px',
    overflowY: 'auto',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 6px',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '0.75rem',
  },
  itemSelected: { background: '#2b6cb0' },
  uid: { color: '#63b3ed', flexShrink: 0, minWidth: '28px' },
  name: {
    flex: 1,
    color: '#e2e8f0',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  milestoneBadge: {
    flexShrink: 0,
    fontSize: '0.6rem',
    padding: '1px 4px',
    background: '#d69e2e',
    color: '#1a1f2e',
    borderRadius: '3px',
    fontWeight: 700,
  },
  clearBtn: {
    marginTop: '8px',
    width: '100%',
    padding: '5px',
    background: '#4a5568',
    border: 'none',
    borderRadius: '4px',
    color: '#e2e8f0',
    fontSize: '0.75rem',
    cursor: 'pointer',
  },
}
