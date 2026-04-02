import React, { useCallback, useRef, useState } from 'react'
import { uploadFiles } from '../api/client.js'
import { useSession } from '../App.jsx'

const MAX_FILES = 10

/**
 * Drag-and-drop upload panel. Creates a session on first drop then uploads files.
 *
 * @param {{ onSessionReady: () => Promise<void> }} props
 */
export default function UploadPanel({ onSessionReady }) {
  const { sessionId, setVersions } = useSession() || {}
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  const processFiles = useCallback(
    async (files) => {
      const mppFiles = Array.from(files).filter((f) =>
        f.name.toLowerCase().endsWith('.mpp')
      )
      if (mppFiles.length === 0) {
        setError('Please select .mpp files.')
        return
      }
      if (mppFiles.length > MAX_FILES) {
        setError(`Maximum ${MAX_FILES} files per session.`)
        return
      }

      setError(null)
      setUploading(true)
      setProgress(0)

      try {
        // Ensure session exists
        if (!sessionId && onSessionReady) {
          await onSessionReady()
        }

        const sid = sessionId
        if (!sid) {
          setError('Could not create session.')
          return
        }

        const data = await uploadFiles(sid, mppFiles, setProgress)
        setResults(data.uploaded || [])

        // Refresh version list
        const { getVersions } = await import('../api/client.js')
        const versionsData = await getVersions(sid)
        if (setVersions) setVersions(versionsData.versions || [])
      } catch (err) {
        setError('Upload failed: ' + (err.response?.data?.detail || err.message))
      } finally {
        setUploading(false)
      }
    },
    [sessionId, onSessionReady, setVersions]
  )

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      setDragging(false)
      processFiles(e.dataTransfer.files)
    },
    [processFiles]
  )

  const onDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const onDragLeave = () => setDragging(false)
  const onInputChange = (e) => processFiles(e.target.files)

  return (
    <div style={styles.wrapper}>
      <div
        style={{ ...styles.dropZone, ...(dragging ? styles.dropZoneDragging : {}) }}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        aria-label="Upload .mpp files"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".mpp"
          multiple
          style={{ display: 'none' }}
          onChange={onInputChange}
        />
        {uploading ? (
          <div>
            <p style={styles.dropText}>Uploading… {progress}%</p>
            <div style={styles.progressBar}>
              <div style={{ ...styles.progressFill, width: `${progress}%` }} />
            </div>
          </div>
        ) : (
          <>
            <p style={styles.dropIcon}>📂</p>
            <p style={styles.dropText}>
              Drag &amp; drop .mpp files here, or click to browse
            </p>
            <p style={styles.dropHint}>Up to {MAX_FILES} files · All processing is local-only</p>
          </>
        )}
      </div>

      {error && <p style={styles.error}>{error}</p>}

      {results.length > 0 && (
        <ul style={styles.resultList}>
          {results.map((r, i) => (
            <li key={i} style={styles.resultItem}>
              <span style={r.status === 'ok' ? styles.ok : styles.err}>
                {r.status === 'ok' ? '✓' : '✗'}
              </span>{' '}
              <strong>{r.filename}</strong>
              {r.status === 'ok'
                ? ` — v${r.version_index}, ${r.task_count} tasks`
                : ` — ${r.reason}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const styles = {
  wrapper: { width: '100%', maxWidth: '640px', margin: '40px auto' },
  dropZone: {
    border: '2px dashed #4a5568',
    borderRadius: '8px',
    padding: '48px 24px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'border-color 0.2s',
    background: '#1a1f2e',
  },
  dropZoneDragging: { borderColor: '#63b3ed', background: '#1e2d45' },
  dropIcon: { fontSize: '2.5rem', margin: '0 0 8px' },
  dropText: { color: '#e2e8f0', fontSize: '1rem', margin: '0 0 6px' },
  dropHint: { color: '#718096', fontSize: '0.8rem', margin: 0 },
  progressBar: { height: '6px', background: '#2d3748', borderRadius: '3px', margin: '8px 0 0' },
  progressFill: { height: '100%', background: '#63b3ed', borderRadius: '3px', transition: 'width 0.2s' },
  error: { color: '#fc8181', fontSize: '0.875rem', marginTop: '8px' },
  resultList: { listStyle: 'none', padding: 0, marginTop: '16px' },
  resultItem: { fontSize: '0.875rem', padding: '4px 0', color: '#e2e8f0' },
  ok: { color: '#68d391' },
  err: { color: '#fc8181' },
}
