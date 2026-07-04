import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { AlertPanel } from './AlertPanel'
import { SettingsProvider } from '../context/SettingsContext'

function renderWithProviders(ui: React.ReactElement) {
  return render(<SettingsProvider>{ui}</SettingsProvider>)
}

const normalHealth = {
  timestamp: '2026-07-02T02:30:00Z',
  services: {
    mqtt: { status: 'healthy', connected: true },
    redis: { status: 'healthy', connected: true },
    watchdog: { status: 'healthy', connected: true },
  },
  resources: {
    cpuPercent: 30, memoryPercent: 40, errorRatePercent: 0.5,
    safeMode: false, throttleActive: false,
  },
  fleet: { total: 5, online: 5, error: 0 },
  version: '3.4.0',
}

const criticalHealth = {
  ...normalHealth,
  resources: {
    cpuPercent: 92, memoryPercent: 97, errorRatePercent: 12,
    safeMode: true, throttleActive: true,
  },
  services: {
    mqtt: { status: 'disconnected', connected: false },
    redis: { status: 'healthy', connected: true },
    watchdog: { status: 'healthy', connected: true },
  },
  fleet: { total: 5, online: 2, error: 3 },
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AlertPanel — 错误追踪面板', () => {
  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    renderWithProviders(<AlertPanel />)
    expect(screen.getByText('Loading alerts…')).toBeInTheDocument()
  })

  it('shows "No active alerts" when system is healthy', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => normalHealth,
    } as Response)

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      expect(screen.getByText('No active alerts')).toBeInTheDocument()
    })
  })

  it('derives P0 alert when MQTT is disconnected', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => criticalHealth,
    } as Response)

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      const badges = screen.getAllByText('P0')
      expect(badges.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('derives alert for SAFE MODE active', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => criticalHealth,
    } as Response)

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      expect(screen.getByText(/SAFE MODE/)).toBeInTheDocument()
    })
  })

  it('shows error state when API fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Connection refused'))

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      expect(screen.getByText(/Connection refused/)).toBeInTheDocument()
    })
  })

  it('renders severity filter buttons', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => criticalHealth,
    } as Response)

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      // Filter buttons contain count: "P0 (3)", "P1 (2)", etc.
      const filterBtns = screen.getAllByRole('button')
      const filterTexts = filterBtns.map(b => b.textContent || '')
      expect(filterTexts.some(t => t.includes('P0'))).toBe(true)
      expect(filterTexts.some(t => t.includes('P1'))).toBe(true)
      expect(filterTexts.some(t => t.includes('P2'))).toBe(true)
    })
  })

  it('Acknowledge button marks alert as acked', async () => {
    const healthWithOneAlert = {
      ...normalHealth,
      resources: { ...normalHealth.resources, safeMode: true },
    }
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => healthWithOneAlert,
    } as Response)

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      expect(screen.getByText(/SAFE MODE/)).toBeInTheDocument()
    })

    const ackBtn = screen.getByText('Ack')
    fireEvent.click(ackBtn)

    await waitFor(() => {
      expect(screen.getByText('✓ Acked')).toBeInTheDocument()
    })
  })

  it('shows unacknowledged count', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => criticalHealth,
    } as Response)

    renderWithProviders(<AlertPanel />)

    await waitFor(() => {
      expect(screen.getByText(/unacknowledged/)).toBeInTheDocument()
    })
  })
})
