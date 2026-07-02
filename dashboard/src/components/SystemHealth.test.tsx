import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SystemHealth } from './SystemHealth'

const mockHealthData = {
  timestamp: '2026-07-02T02:30:00Z',
  services: {
    sapBridge: { status: 'healthy', connected: true, uptimeSeconds: 3600 },
    mqtt: { status: 'healthy', connected: true, uptimeSeconds: 7200 },
    redis: { status: 'healthy', connected: true, uptimeSeconds: 1800 },
    database: { status: 'healthy', connected: true, uptimeSeconds: 9000 },
    watchdog: { status: 'healthy', connected: true, uptimeSeconds: 5400 },
  },
  resources: {
    cpuPercent: 45,
    memoryPercent: 62,
    errorRatePercent: 1.2,
    safeMode: false,
    throttleActive: false,
  },
  fleet: {
    total: 12, online: 10, error: 1, moving: 4, idle: 5, charging: 2,
  },
  version: '3.4.0',
}

const mockHealthDataWithWarnings = {
  ...mockHealthData,
  resources: {
    cpuPercent: 85, memoryPercent: 92, errorRatePercent: 8.5,
    safeMode: true, throttleActive: true,
  },
  services: { ...mockHealthData.services, mqtt: { status: 'disconnected', connected: false } },
  fleet: { total: 12, online: 8, error: 3, moving: 2, idle: 4, charging: 1 },
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('SystemHealth — 监控面板', () => {
  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<SystemHealth />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders service status grid on successful fetch', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockHealthData,
    } as Response)

    render(<SystemHealth />)

    await waitFor(() => {
      expect(screen.getByText('SAP Bridge')).toBeInTheDocument()
    })
    expect(screen.getByText('MQTT Broker')).toBeInTheDocument()
    expect(screen.getByText('Redis')).toBeInTheDocument()
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.getByText('Watchdog')).toBeInTheDocument()
  })

  it('renders CPU / Memory / Error Rate gauges', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockHealthData,
    } as Response)

    render(<SystemHealth />)

    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeInTheDocument()
    })
    expect(screen.getByText('Memory')).toBeInTheDocument()
    expect(screen.getByText('Error Rate')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByText('62%')).toBeInTheDocument()
  })

  it('renders fleet status summary', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockHealthData,
    } as Response)

    render(<SystemHealth />)

    await waitFor(() => {
      expect(screen.getByText('Fleet Status')).toBeInTheDocument()
    })
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getByText('Online')).toBeInTheDocument()
  })

  it('shows SAFE MODE and THROTTLE indicators when active', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockHealthDataWithWarnings,
    } as Response)

    render(<SystemHealth />)

    await waitFor(() => {
      expect(screen.getByText('SAFE MODE ACTIVE')).toBeInTheDocument()
    })
    expect(screen.getByText('THROTTLE ACTIVE')).toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network Error'))

    render(<SystemHealth />)

    await waitFor(() => {
      expect(screen.getByText(/Network Error/)).toBeInTheDocument()
    })
  })

  it('shows version in timestamp footer', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockHealthData,
    } as Response)

    render(<SystemHealth />)

    await waitFor(() => {
      expect(screen.getByText(/v3\.4\.0/)).toBeInTheDocument()
    })
  })

  it('polls every 10 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockHealthData,
    } as Response)

    render(<SystemHealth />)

    // Let initial useEffect + fetch settle
    await vi.advanceTimersByTimeAsync(100)
    expect(fetchSpy).toHaveBeenCalledTimes(1)

    // Advance 10s — should trigger next poll
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchSpy).toHaveBeenCalledTimes(2)

    // Another 10s
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchSpy).toHaveBeenCalledTimes(3)

    vi.useRealTimers()
  })
})
