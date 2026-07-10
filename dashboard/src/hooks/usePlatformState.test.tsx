import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { usePlatformState } from './usePlatformState'

/** Wrapper component to test the hook */
function HookTester({ expose }: { expose: (result: ReturnType<typeof usePlatformState>) => void }) {
  const result = usePlatformState()
  expose(result)
  return (
    <div data-testid="hook-output">
      <span data-testid="connected">{String(result.connected)}</span>
      <span data-testid="error">{result.error ?? 'null'}</span>
      <span data-testid="has-state">{String(result.state !== null)}</span>
      <span data-testid="has-health">{String(result.health !== null)}</span>
    </div>
  )
}

const mockHealth = {
  status: 'healthy',
  mode: 'active',
  version: '5.0.0',
  supported_versions: ['5.0'],
  checks: ['mqtt', 'redis'],
}

const mockState = {
  robots: {
    'mir-001': {
      mode: 'TASKING',
      pose: [1.0, 2.0] as [number, number],
      boot_id: 'boot-123',
      sensor_health: 0.95,
      battery_percent: 85,
      velocity: 1.2,
    },
  },
  locked_zones: ['X1'],
  pending_tasks: 3,
  active_assignments: 2,
  pending_commands: 0,
  metrics: { intersection_X1: 1 },
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePlatformState', () => {
  it('starts with disconnected state', () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))

    render(<HookTester expose={() => {}} />)

    expect(screen.getByTestId('connected').textContent).toBe('false')
    expect(screen.getByTestId('error').textContent).toBe('null')
    expect(screen.getByTestId('has-state').textContent).toBe('false')
    expect(screen.getByTestId('has-health').textContent).toBe('false')
  })

  it('fetches health and state on mount', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    // First call: health
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => mockHealth,
    } as Response)
    // Second call: state
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => mockState,
    } as Response)

    render(<HookTester expose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('connected').textContent).toBe('true')
    })
    expect(screen.getByTestId('has-health').textContent).toBe('true')
    expect(screen.getByTestId('has-state').textContent).toBe('true')
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/v1/v5/health'),
      expect.any(Object),
    )
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/v1/v5/state'),
      expect.any(Object),
    )
  })

  it('sets connected=true even if state fetch fails after health OK', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => mockHealth,
    } as Response)
    // state endpoint fails but health succeeded → connected remains true
    fetchSpy.mockResolvedValueOnce({
      ok: false, status: 500,
    } as Response)

    render(<HookTester expose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('connected').textContent).toBe('true')
    })
    expect(screen.getByTestId('has-health').textContent).toBe('true')
    // state failed so has-state remains false
    expect(screen.getByTestId('has-state').textContent).toBe('false')
  })

  it('sets error when health endpoint returns non-ok', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: false, status: 503,
    } as Response)

    render(<HookTester expose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('error').textContent).toContain('503')
    })
    expect(screen.getByTestId('connected').textContent).toBe('false')
  })

  it('sets error when fetch throws', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network down'))

    render(<HookTester expose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('error').textContent).toContain('Network down')
    })
    expect(screen.getByTestId('connected').textContent).toBe('false')
  })

  it('polls every 5 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetchSpy = vi.spyOn(global, 'fetch')
    // First poll — health OK, state OK
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockState } as Response)
    // Second poll
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockState } as Response)

    render(<HookTester expose={() => {}} />)

    // Let first render + fetch settle
    await vi.advanceTimersByTimeAsync(100)
    expect(fetchSpy).toHaveBeenCalledTimes(2) // health + state

    // Advance 5s → second poll
    await vi.advanceTimersByTimeAsync(5_000)
    expect(fetchSpy).toHaveBeenCalledTimes(4) // health + state × 2

    vi.useRealTimers()
  })

  it('refresh triggers immediate re-fetch', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValue({ ok: true, json: async () => mockHealth } as Response)

    let captured: ReturnType<typeof usePlatformState> | null = null
    render(<HookTester expose={(r) => { captured = r }} />)

    await waitFor(() => {
      expect(screen.getByTestId('connected').textContent).toBe('true')
    })
    const initialCallCount = fetchSpy.mock.calls.length

    // Trigger refresh
    await act(async () => {
      ;(captured as ReturnType<typeof usePlatformState>).refresh()
    })

    // refresh calls fetchData directly → 2 more calls (health + state)
    expect(fetchSpy).toHaveBeenCalledTimes(initialCallCount + 2)
  })
})
