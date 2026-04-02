/**
 * API client — all backend calls go through here.
 * Base URL defaults to http://localhost:8000 (overridable via VITE_API_BASE_URL).
 */

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// ── Session ───────────────────────────────────────────────────────────────────

export async function createSession() {
  const { data } = await api.post('/session/create')
  return data
}

export async function endSession(sessionId) {
  const { data } = await api.delete(`/session/${sessionId}/end`)
  return data
}

// ── Upload ────────────────────────────────────────────────────────────────────

/**
 * Upload one or more .mpp File objects.
 * @param {string} sessionId
 * @param {File[]} files
 * @param {(pct: number) => void} [onProgress]
 */
export async function uploadFiles(sessionId, files, onProgress) {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))

  const { data } = await api.post(`/session/${sessionId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
      ? (e) => onProgress(Math.round((e.loaded * 100) / (e.total || 1)))
      : undefined,
  })
  return data
}

// ── Versions ──────────────────────────────────────────────────────────────────

export async function getVersions(sessionId) {
  const { data } = await api.get(`/session/${sessionId}/versions`)
  return data
}

// ── CPM Analysis ──────────────────────────────────────────────────────────────

export async function analyzeVersion(sessionId, versionIndex) {
  const { data } = await api.post(`/session/${sessionId}/analyze`, {
    version_index: versionIndex,
  })
  return data
}

// ── Diff ──────────────────────────────────────────────────────────────────────

export async function diffVersions(sessionId, baseIndex, compareIndex) {
  const { data } = await api.post(`/session/${sessionId}/diff`, {
    base_index: baseIndex,
    compare_index: compareIndex,
  })
  return data
}

// ── DCMA ──────────────────────────────────────────────────────────────────────

export async function getDcma(sessionId, versionIndex) {
  const { data } = await api.get(`/session/${sessionId}/dcma/${versionIndex}`)
  return data
}

// ── Forensics ─────────────────────────────────────────────────────────────────

export async function runForensics(sessionId, versionIndices) {
  const { data } = await api.post(`/session/${sessionId}/forensics`, {
    version_indices: versionIndices,
  })
  return data
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function chat(sessionId, query) {
  const { data } = await api.post(`/session/${sessionId}/chat`, { query })
  return data
}

export default api
