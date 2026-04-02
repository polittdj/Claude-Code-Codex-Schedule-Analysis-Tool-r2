import React, { useState } from 'react'
import { useSession } from '../App.jsx'

export default function SessionEndButton() {
  const { endSession } = useSession() || {}
  const [confirming, setConfirming] = useState(false)

  if (!endSession) return null

  if (confirming) {
    return (
      <div style={styles.confirmRow}>
        <span style={styles.confirmText}>Delete all session data?</span>
        <button
          style={{ ...styles.btn, ...styles.btnDanger }}
          onClick={async () => {
            setConfirming(false)
            await endSession()
          }}
        >
          Yes, end session
        </button>
        <button style={styles.btn} onClick={() => setConfirming(false)}>
          Cancel
        </button>
      </div>
    )
  }

  return (
    <button
      style={{ ...styles.btn, ...styles.btnDanger }}
      onClick={() => setConfirming(true)}
      title="Wipe all uploaded files and analysis data"
    >
      End Session
    </button>
  )
}

const styles = {
  confirmRow: { display: 'flex', alignItems: 'center', gap: '8px' },
  confirmText: { fontSize: '0.8rem', color: '#fc8181' },
  btn: {
    padding: '6px 12px',
    borderRadius: '4px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '0.8rem',
    background: '#4a5568',
    color: '#e2e8f0',
  },
  btnDanger: { background: '#9b2c2c', color: '#fff' },
}
