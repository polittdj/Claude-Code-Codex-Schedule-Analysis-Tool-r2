import { render, screen } from '@testing-library/react'
import App from '../App.jsx'

// Mock axios / API client so it doesn't make real network calls
vi.mock('../api/client.js', () => ({
  createSession: vi.fn(),
  endSession: vi.fn(),
  uploadFiles: vi.fn(),
  getVersions: vi.fn(),
  analyzeVersion: vi.fn(),
  diffVersions: vi.fn(),
  getDcma: vi.fn(),
  runForensics: vi.fn(),
  chat: vi.fn(),
  default: {},
}))

test('renders app title', () => {
  render(<App />)
  expect(screen.getByText(/Schedule Forensics Tool/i)).toBeTruthy()
})

test('shows privacy subtitle before session is created', () => {
  render(<App />)
  expect(screen.getAllByText(/local-only/i).length).toBeGreaterThan(0)
})
