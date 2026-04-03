import React, { useCallback, useRef, useState } from 'react'
import { uploadFiles, getVersions } from '../api/client.js'
import { useSession } from '../App.jsx'

const MAX_FILES = 10

export default function UploadPanel() {
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
      if (!sessionId) {
        setError('No active session. Please refresh the page.')
        return
      }

      setError(null)
      setUploading(true)
      setProgress(0)

      try {
        const data = await uploadFiles(sessionId, mppFiles, setProgress)
        setResults(data.uploaded || [])

        // Refresh version list
        const versionsData = await getVersions(sessionId)
        if (setVersions) setVersions(versionsData.versions || [])
      } catch (err) {
        setError('Upload failed: ' + (err.response?.data?.detail || err.message))
      } finally {
        setUploading(false)
      }
    },
    [sessionId, setVersions]
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
    <div>
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
            <p style={styles.dropText}>Drop .mpp file here or click to browse</p>
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
              {r.filename}
              {r.status === 'ok'
                ? ` (${r.task_count} tasks)`
                : `: ${r.reason}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const styles = {
  dropZone: {
    border: '2px dashed #4a5568',
    borderRadius: '6px',
    padding: '20px 12px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'border-color 0.2s',
    background: '#0f1117',
  },
  dropZoneDragging: { borderColor: '#63b3ed', background: '#1e2d45' },
  dropIcon: { fontSize: '1.8rem', margin: '0 0 6px' },
  dropText: { color: '#a0aec0', fontSize: '0.78rem', margin: 0 },
  progressBar: { height: '4px', background: '#2d3748', borderRadius: '2px', margin: '8px 0 0' },
  progressFill: { height: '100%', background: '#63b3ed', borderRadius: '2px', transition: 'width 0.2s' },
  error: { color: '#fc8181', fontSize: '0.75rem', marginTop: '6px' },
  resultList: { listStyle: 'none', padding: 0, marginTop: '8px' },
  resultItem: { fontSize: '0.72rem', padding: '2px 0', color: '#e2e8f0' },
  ok: { color: '#68d391' },
  err: { color: '#fc8181' },
}
