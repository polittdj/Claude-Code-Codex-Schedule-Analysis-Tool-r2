import React, { useEffect, useRef, useState } from 'react'
import { useSession } from '../App.jsx'
import { analyzeVersion } from '../api/client.js'

/**
 * Gantt chart using Plotly.js horizontal bar chart.
 * Critical path tasks → red, near-critical → orange, focal task → blue border.
 */
export default function GanttChart() {
  const { sessionId, versions, cpmResults, setCpmResults, focalTaskId } = useSession() || {}
  const [selectedVersion, setSelectedVersion] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const chartRef = useRef(null)
  const plotRef = useRef(null)

  const version = versions?.find((v) => v.version_index === selectedVersion)
  const cpm = cpmResults?.[selectedVersion]

  // Run CPM if not yet cached
  useEffect(() => {
    if (!sessionId || !version || cpm) return
    setLoading(true)
    setError(null)
    analyzeVersion(sessionId, selectedVersion)
      .then((data) => {
        setCpmResults((prev) => ({ ...prev, [selectedVersion]: data }))
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [sessionId, version, cpm, selectedVersion, setCpmResults])

  // Render Plotly chart
  useEffect(() => {
    if (!chartRef.current || !version || !cpm) return

    import('plotly.js').then((Plotly) => {
      const tasks = (version.tasks || []).filter((t) => !t.is_summary && !t.is_loe)
      const projectStart = version.project_start ? new Date(version.project_start) : new Date()

      const toDate = (days) => {
        const d = new Date(projectStart)
        d.setDate(d.getDate() + Math.round(days))
        return d.toISOString().split('T')[0]
      }

      const criticalSet = new Set(cpm.critical_path || [])
      const nearCriticalSet = new Set(cpm.near_critical || [])
      const floatMap = cpm.task_floats || {}

      const bars = tasks.map((t) => {
        const tf = floatMap[t.unique_id]
        const es = tf ? (t.duration_days || 0) - (tf.total_float || 0) : 0
        const dur = t.duration_days || 0
        const start = toDate(es - dur)
        const finish = toDate(es)
        const isCritical = criticalSet.has(t.unique_id)
        const isNear = nearCriticalSet.has(t.unique_id)
        const isFocal = t.unique_id === focalTaskId

        const color = isCritical ? '#e53e3e' : isNear ? '#d69e2e' : '#3182ce'
        const border = isFocal ? '#fff' : color

        return {
          type: 'bar',
          orientation: 'h',
          x: [dur === 0 ? 0.3 : dur],
          y: [t.name.length > 40 ? t.name.slice(0, 40) + '…' : t.name],
          base: [start],
          marker: { color, line: { color: border, width: isFocal ? 2 : 0 } },
          hovertemplate: `<b>${t.name}</b><br>Start: ${start}<br>End: ${finish}<br>TF: ${tf ? tf.total_float.toFixed(1) : '?'}d<extra></extra>`,
          showlegend: false,
        }
      })

      const layout = {
        paper_bgcolor: '#1a1f2e',
        plot_bgcolor: '#0f1117',
        font: { color: '#e2e8f0', size: 11 },
        margin: { l: 220, r: 20, t: 30, b: 40 },
        xaxis: { type: 'date', title: '', gridcolor: '#2d3748' },
        yaxis: { autorange: 'reversed', tickfont: { size: 10 } },
        barmode: 'overlay',
        height: Math.max(300, tasks.length * 22 + 80),
      }

      Plotly.default.react(chartRef.current, bars, layout, {
        responsive: true,
        displayModeBar: false,
      })
      plotRef.current = true
    })
  }, [version, cpm, focalTaskId])

  if (!versions || versions.length === 0) {
    return <EmptyState>Upload schedule files to see the Gantt chart.</EmptyState>
  }

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <label style={styles.label}>
          Version:
          <select
            style={styles.select}
            value={selectedVersion}
            onChange={(e) => setSelectedVersion(Number(e.target.value))}
          >
            {versions.map((v) => (
              <option key={v.version_index} value={v.version_index}>
                v{v.version_index} — {v.filename}
              </option>
            ))}
          </select>
        </label>
        <Legend />
      </div>
      {loading && <p style={styles.info}>Running CPM analysis…</p>}
      {error && <p style={styles.error}>{error}</p>}
      <div ref={chartRef} style={styles.chart} />
    </div>
  )
}

function Legend() {
  return (
    <div style={styles.legend}>
      {[['#e53e3e', 'Critical'], ['#d69e2e', 'Near-Critical'], ['#3182ce', 'Other']].map(([color, label]) => (
        <span key={label} style={styles.legendItem}>
          <span style={{ ...styles.legendDot, background: color }} />
          {label}
        </span>
      ))}
    </div>
  )
}

function EmptyState({ children }) {
  return <div style={styles.empty}>{children}</div>
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', gap: '12px' },
  toolbar: { display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' },
  label: { fontSize: '0.8rem', color: '#a0aec0', display: 'flex', alignItems: 'center', gap: '6px' },
  select: { background: '#2d3748', border: '1px solid #4a5568', color: '#e2e8f0', borderRadius: '4px', padding: '4px 8px', fontSize: '0.8rem' },
  legend: { display: 'flex', gap: '12px' },
  legendItem: { display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: '#a0aec0' },
  legendDot: { width: '10px', height: '10px', borderRadius: '50%' },
  chart: { width: '100%', overflowX: 'auto' },
  info: { color: '#63b3ed', fontSize: '0.85rem' },
  error: { color: '#fc8181', fontSize: '0.85rem' },
  empty: { color: '#718096', padding: '40px', textAlign: 'center' },
}
