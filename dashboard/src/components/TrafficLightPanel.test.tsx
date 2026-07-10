import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { TrafficLightPanel } from './TrafficLightPanel'

const mockHealth = {
  status: 'healthy',
  mode: 'active',
  version: '5.0.0',
  supported_versions: ['5.0'],
  checks: ['mqtt', 'redis'],
}

const mockStateConnected = {
  robots: {
    'mir-001': { mode: 'TASKING', pose: [1, 2] },
    'mir-002': { mode: 'IDLE', pose: [3, 4] },
  },
  locked_zones: ['X1', 'L_X1_A'],
  pending_tasks: 3,
  active_assignments: 2,
  pending_commands: 0,
  metrics: {
    intersection_X1: 1,
    lane_X1_L_X1_A: 1,
    lane_X1_L_X1_B: 1,
  },
}

const mockStateNoIntersections = {
  robots: {},
  locked_zones: [],
  pending_tasks: 0,
  active_assignments: 0,
  pending_commands: 0,
  metrics: {},
}

function mockFetchOk(...responses: object[]) {
  const spy = vi.spyOn(global, 'fetch')
  for (const body of responses) {
    spy.mockResolvedValueOnce({ ok: true, json: async () => body } as Response)
  }
  return spy
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TrafficLightPanel', () => {
  it('shows waiting state when not connected', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<TrafficLightPanel />)
    expect(screen.getByText('🚦 Traffic Lights')).toBeInTheDocument()
    expect(screen.getByText('Waiting for coordinator connection…')).toBeInTheDocument()
  })

  it('shows disconnected status indicator', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<TrafficLightPanel />)
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
  })

  it('shows coordinator version when health is available', async () => {
    mockFetchOk(mockHealth, mockStateConnected)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('v5.0.0')).toBeInTheDocument()
    })
  })

  it('shows "v5 Coordinator" when connected', async () => {
    mockFetchOk(mockHealth, mockStateConnected)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('v5 Coordinator')).toBeInTheDocument()
    })
  })

  it('shows error when coordinator is unreachable', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Connection refused'))
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText(/Connection refused/)).toBeInTheDocument()
    })
  })

  it('shows "No intersections configured" when connected but no metrics', async () => {
    mockFetchOk(mockHealth, mockStateNoIntersections)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('No intersections configured')).toBeInTheDocument()
    })
  })

  it('renders intersection cards when metrics contain intersection data', async () => {
    mockFetchOk(mockHealth, mockStateConnected)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('Intersection X1')).toBeInTheDocument()
    })
    // Lanes should appear
    expect(screen.getByText('L_X1_A')).toBeInTheDocument()
    expect(screen.getByText('L_X1_B')).toBeInTheDocument()
  })

  it('shows RED for locked lanes', async () => {
    mockFetchOk(mockHealth, mockStateConnected)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('Intersection X1')).toBeInTheDocument()
    })
    // L_X1_A is in locked_zones → RED; X1 node also locked → all lanes RED
    const redElements = screen.getAllByText('RED')
    expect(redElements.length).toBeGreaterThanOrEqual(1)
  })

  it('renders Platform Overview when state is available', async () => {
    mockFetchOk(mockHealth, mockStateConnected)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('Platform Overview')).toBeInTheDocument()
    })
    expect(screen.getByText('Active Robots')).toBeInTheDocument()
    expect(screen.getByText('Locked Zones')).toBeInTheDocument()
    expect(screen.getByText('Pending Tasks')).toBeInTheDocument()
    expect(screen.getByText('Active Assignments')).toBeInTheDocument()
    // Check values (multiple stats may share the same value)
    const twos = screen.getAllByText('2')
    expect(twos.length).toBe(3) // Active Robots, Locked Zones, Active Assignments
    expect(screen.getByText('3')).toBeInTheDocument() // Pending Tasks
  })

  it('falls back to locked-zone-only display when no intersection metrics', async () => {
    const stateWithLocks = {
      ...mockStateNoIntersections,
      locked_zones: ['ZONE_A', 'ZONE_B'],
    }
    mockFetchOk(mockHealth, stateWithLocks)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('Intersection X1')).toBeInTheDocument()
    })
    expect(screen.getByText('ZONE_A')).toBeInTheDocument()
    expect(screen.getByText('ZONE_B')).toBeInTheDocument()
  })

  it('refresh button is present when connected', async () => {
    mockFetchOk(mockHealth, mockStateConnected)
    render(<TrafficLightPanel />)
    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument()
    })
  })
})
