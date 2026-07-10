import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { ZoneLockdownPanel } from './ZoneLockdownPanel'

const mockHealth = {
  status: 'healthy',
  mode: 'active',
  version: '5.0.0',
  supported_versions: ['5.0'],
  checks: ['mqtt', 'redis'],
}

const mockStateWithLocks = {
  robots: {
    'mir-001': { mode: 'TASKING', pose: [1, 2] },
  },
  locked_zones: ['X1', 'L_A_B', 'CHARGER_BAY'],
  pending_tasks: 2,
  active_assignments: 1,
  pending_commands: 0,
  metrics: {},
}

const mockStateNoLocks = {
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

describe('ZoneLockdownPanel', () => {
  it('shows warning when not connected', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<ZoneLockdownPanel />)
    expect(screen.getByText('🔒 Zone Lockdown')).toBeInTheDocument()
    expect(screen.getByText(/Coordinator not connected/)).toBeInTheDocument()
  })

  it('shows "all clear" when connected with no locked zones', async () => {
    mockFetchOk(mockHealth, mockStateNoLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('No zones currently locked — all clear')).toBeInTheDocument()
    })
  })

  it('renders locked zones list when zones are locked', async () => {
    mockFetchOk(mockHealth, mockStateWithLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('X1')).toBeInTheDocument()
    })
    expect(screen.getByText('L_A_B')).toBeInTheDocument()
    expect(screen.getByText('CHARGER_BAY')).toBeInTheDocument()
  })

  it('shows LOCKED status label for locked zones', async () => {
    mockFetchOk(mockHealth, mockStateWithLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('X1')).toBeInTheDocument()
    })
    // All zones in mockStateWithLocks are locked
    const lockedLabels = screen.getAllByText('LOCKED')
    expect(lockedLabels.length).toBe(3)
  })

  it('shows locked zones count in header', async () => {
    mockFetchOk(mockHealth, mockStateWithLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('Locked Zones (3)')).toBeInTheDocument()
    })
  })

  it('has Unlock button for each locked zone', async () => {
    mockFetchOk(mockHealth, mockStateWithLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('X1')).toBeInTheDocument()
    })
    // Scope to locked zones list to exclude manual control Unlock button
    const lockedZonesSection = screen.getByText('Locked Zones (3)').closest('div')!
    const unlockButtons = within(lockedZonesSection).getAllByText('Unlock')
    expect(unlockButtons.length).toBe(3)
  })

  it('has Manual Zone Control section', async () => {
    mockFetchOk(mockHealth, mockStateNoLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('Manual Zone Control')).toBeInTheDocument()
    })
  })

  it('Manual Zone input accepts text', async () => {
    mockFetchOk(mockHealth, mockStateNoLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText(/Zone ID/)
    fireEvent.change(input, { target: { value: 'ZONE_CUSTOM' } })
    expect(input).toHaveValue('ZONE_CUSTOM')
  })

  it('Lock/Unlock buttons disabled when input is empty', async () => {
    mockFetchOk(mockHealth, mockStateNoLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('Manual Zone Control')).toBeInTheDocument()
    })
    const lockBtn = screen.getByText('Lock')
    const unlockBtn = screen.getByText('Unlock')
    expect(lockBtn).toBeDisabled()
    expect(unlockBtn).toBeDisabled()
  })

  it('Lock/Unlock buttons enabled when input has text', async () => {
    mockFetchOk(mockHealth, mockStateNoLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText(/Zone ID/)
    fireEvent.change(input, { target: { value: 'CUSTOM_ZONE' } })

    const lockBtn = screen.getByText('Lock')
    const unlockBtn = screen.getByText('Unlock')
    expect(lockBtn).not.toBeDisabled()
    expect(unlockBtn).not.toBeDisabled()
  })

  it('pressing Enter on input triggers lock action', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    // health + state (initial)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockStateNoLocks } as Response)
    // POST lock (triggered by Enter)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ok' }) } as Response)

    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText(/Zone ID/)
    fireEvent.change(input, { target: { value: 'ENTER_ZONE' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/v1/v5/zone/ENTER_ZONE/lock'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('clicking Lock sends POST to lock endpoint', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockStateNoLocks } as Response)
    // POST lock
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ok' }) } as Response)

    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    fireEvent.change(screen.getByPlaceholderText(/Zone ID/), { target: { value: 'CLICK_ZONE' } })
    fireEvent.click(screen.getByText('Lock'))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/v1/v5/zone/CLICK_ZONE/lock'),
        expect.any(Object),
      )
    })
  })

  it('clicking Unlock sends POST to unlock endpoint', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockStateWithLocks } as Response)
    // POST unlock for X1
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ok' }) } as Response)

    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText('X1')).toBeInTheDocument()
    })
    // Find unlock button scoped to the X1 row (the flex container wrapping name + button)
    const x1Row = screen.getByText('X1').closest('div')!.parentElement!
    const unlockBtn = within(x1Row).getByText('Unlock')
    fireEvent.click(unlockBtn)

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/v1/v5/zone/X1/unlock'),
        expect.any(Object),
      )
    })
  })

  it('shows success in command history after action', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockStateNoLocks } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'ok' }) } as Response)

    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    fireEvent.change(screen.getByPlaceholderText(/Zone ID/), { target: { value: 'SUCCESS_ZONE' } })
    fireEvent.click(screen.getByText('Lock'))

    await waitFor(() => {
      expect(screen.getByText('Command History')).toBeInTheDocument()
    })
    expect(screen.getByText(/\[LOCK\] SUCCESS_ZONE/)).toBeInTheDocument()
    expect(screen.getByText(/locked successfully/)).toBeInTheDocument()
  })

  it('shows error in command history when API returns failure', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockStateNoLocks } as Response)
    fetchSpy.mockResolvedValueOnce({
      ok: false, status: 500,
      json: async () => ({ error: 'Internal server error' }),
    } as Response)

    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    fireEvent.change(screen.getByPlaceholderText(/Zone ID/), { target: { value: 'FAIL_ZONE' } })
    fireEvent.click(screen.getByText('Lock'))

    await waitFor(() => {
      expect(screen.getByText(/\[LOCK\] FAIL_ZONE/)).toBeInTheDocument()
    })
    expect(screen.getByText(/Internal server error/)).toBeInTheDocument()
  })

  it('handles network error gracefully', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockHealth } as Response)
    fetchSpy.mockResolvedValueOnce({ ok: true, json: async () => mockStateNoLocks } as Response)
    fetchSpy.mockRejectedValueOnce(new Error('Network error'))

    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Zone ID/)).toBeInTheDocument()
    })
    fireEvent.change(screen.getByPlaceholderText(/Zone ID/), { target: { value: 'NET_ZONE' } })
    fireEvent.click(screen.getByText('Lock'))

    await waitFor(() => {
      expect(screen.getByText(/Network error: Network error/)).toBeInTheDocument()
    })
  })

  it('shows zone input hint text', async () => {
    mockFetchOk(mockHealth, mockStateNoLocks)
    render(<ZoneLockdownPanel />)
    await waitFor(() => {
      expect(screen.getByText(/Manual zone lock\/unlock/)).toBeInTheDocument()
    })
  })

  it('starts with unconnected status indicator', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<ZoneLockdownPanel />)
    // The panel shows a red dot when disconnected (inline background style)
    // We verify the warning message renders instead
    expect(screen.getByText(/Coordinator not connected/)).toBeInTheDocument()
  })
})
