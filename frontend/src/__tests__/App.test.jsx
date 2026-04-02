import { render, screen } from '@testing-library/react'
import App from '../App.jsx'

test('renders app placeholder', () => {
  render(<App />)
  expect(screen.getByText(/Schedule Forensics Tool/i)).toBeTruthy()
})
