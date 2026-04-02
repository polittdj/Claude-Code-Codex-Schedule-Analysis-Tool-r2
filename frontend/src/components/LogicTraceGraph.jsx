import React, { useEffect, useRef, useState } from 'react'
import { useSession } from '../App.jsx'
import { analyzeVersion } from '../api/client.js'

/**
 * Logic trace graph using Cytoscape.js with dagre layout.
 * Focal task in blue; driving predecessors in red; others in grey.
 */
export default function LogicTraceGraph() {
  const { sessionId, versions, cpmResults, setCpmResults, focalTaskId } = useSession() || {}
  const [selectedVersion, setSelectedVersion] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const containerRef = useRef(null)
  const cyRef = useRef(null)

  const version = versions?.find((v) => v.version_index === selectedVersion)
  const cpm = cpmResults?.[selectedVersion]

  useEffect(() => {
    if (!sessionId || !version || cpm) return
    setLoading(true)
    analyzeVersion(sessionId, selectedVersion)
      .then((data) => setCpmResults((prev) => ({ ...prev, [selectedVersion]: data })))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [sessionId, version, cpm, selectedVersion, setCpmResults])

  useEffect(() => {
    if (!containerRef.current || !version || !cpm) return

    Promise.all([
      import('cytoscape'),
      import('cytoscape-dagre'),
    ]).then(([cytoscapeModule, dagreModule]) => {
      const cytoscape = cytoscapeModule.default
      const dagre = dagreModule.default

      if (!cytoscape.prototype._registered_dagre) {
        cytoscape.use(dagre)
        cytoscape.prototype._registered_dagre = true
      }

      const taskMap = {}
      ;(version.tasks || []).forEach((t) => { taskMap[t.unique_id] = t })

      const criticalSet = new Set(cpm.critical_path || [])

      // Build neighbour subgraph around focal task (2 hops)
      const links = version.links || []
      const predMap = {}
      const succMap = {}
      links.forEach((lnk) => {
        if (!predMap[lnk.succ_unique_id]) predMap[lnk.succ_unique_id] = []
        predMap[lnk.succ_unique_id].push(lnk)
        if (!succMap[lnk.pred_unique_id]) succMap[lnk.pred_unique_id] = []
        succMap[lnk.pred_unique_id].push(lnk)
      })

      const focal = focalTaskId || cpm.critical_path?.[0]
      const included = new Set()
      const bfs = (id, depth) => {
        if (!id || depth < 0 || included.has(id)) return
        included.add(id)
        ;(predMap[id] || []).forEach((l) => bfs(l.pred_unique_id, depth - 1))
        ;(succMap[id] || []).forEach((l) => bfs(l.succ_unique_id, depth - 1))
      }
      if (focal) bfs(focal, 2)
      else Object.keys(taskMap).slice(0, 40).forEach((id) => included.add(id))

      const nodes = [...included].map((id) => {
        const t = taskMap[id]
        if (!t) return null
        const isFocal = id === focal
        const isCrit = criticalSet.has(id)
        return {
          data: {
            id,
            label: (t.name || id).slice(0, 30),
            color: isFocal ? '#63b3ed' : isCrit ? '#e53e3e' : '#718096',
          },
        }
      }).filter(Boolean)

      const edges = links
        .filter((l) => included.has(l.pred_unique_id) && included.has(l.succ_unique_id))
        .map((l) => ({
          data: {
            id: `${l.pred_unique_id}_${l.succ_unique_id}`,
            source: l.pred_unique_id,
            target: l.succ_unique_id,
            label: l.lag_days !== 0 ? `${l.relationship_type} ${l.lag_days > 0 ? '+' : ''}${l.lag_days}d` : l.relationship_type,
          },
        }))

      if (cyRef.current) cyRef.current.destroy()

      cyRef.current = cytoscape({
        container: containerRef.current,
        elements: [...nodes, ...edges],
        style: [
          {
            selector: 'node',
            style: {
              label: 'data(label)',
              'background-color': 'data(color)',
              color: '#e2e8f0',
              'font-size': '9px',
              'text-valign': 'center',
              'text-halign': 'center',
              width: '80px',
              height: '30px',
              shape: 'roundrectangle',
              'text-wrap': 'wrap',
              'text-max-width': '75px',
            },
          },
          {
            selector: 'edge',
            style: {
              'curve-style': 'bezier',
              'target-arrow-shape': 'triangle',
              'line-color': '#4a5568',
              'target-arrow-color': '#4a5568',
              'font-size': '8px',
              label: 'data(label)',
              color: '#718096',
              width: 1.5,
            },
          },
        ],
        layout: { name: 'dagre', rankDir: 'LR', nodeSep: 20, rankSep: 60 },
        userZoomingEnabled: true,
        userPanningEnabled: true,
        boxSelectionEnabled: false,
      })
    })
  }, [version, cpm, focalTaskId, selectedVersion])

  if (!versions || versions.length === 0) {
    return <div style={styles.empty}>Upload schedule files to see the logic graph.</div>
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
        <span style={styles.hint}>
          {focalTaskId ? `Focal: ${focalTaskId}` : 'Select a focal task to filter'}
        </span>
      </div>
      {loading && <p style={styles.info}>Running CPM…</p>}
      {error && <p style={styles.error}>{error}</p>}
      <div ref={containerRef} style={styles.graph} />
    </div>
  )
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', gap: '12px' },
  toolbar: { display: 'flex', alignItems: 'center', gap: '16px' },
  label: { fontSize: '0.8rem', color: '#a0aec0', display: 'flex', alignItems: 'center', gap: '6px' },
  select: { background: '#2d3748', border: '1px solid #4a5568', color: '#e2e8f0', borderRadius: '4px', padding: '4px 8px', fontSize: '0.8rem' },
  hint: { fontSize: '0.75rem', color: '#718096' },
  graph: { width: '100%', height: '500px', background: '#0f1117', borderRadius: '4px', border: '1px solid #2d3748' },
  info: { color: '#63b3ed', fontSize: '0.85rem' },
  error: { color: '#fc8181', fontSize: '0.85rem' },
  empty: { color: '#718096', padding: '40px', textAlign: 'center' },
}
