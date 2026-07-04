import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { CommandPanel } from './CommandPanel'

const mockRobots = {
  robots: [
    { id: 'RBT-001', brand: 'Geek+', state: 'ONLINE', battery: '85%', lastSeen: '2026-07-02T02:30:00Z' },
    { id: 'RBT-002', brand: 'Quicktron', state: 'MOVING', battery: '42%', lastSeen: '2026-07-02T02:29:00Z' },
    { id: 'RBT-003', brand: 'ForwardX', state: 'ERROR', battery: '10%', lastSeen: '2026-07-02T02:28:00Z' },
  ],
}

const emptyRobots = { robots: [] }

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CommandPanel — 指令下发控制台', () => {
  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<CommandPanel />)
    expect(screen.getByText('Loading robots…')).toBeInTheDocument()
  })

  it('renders robot list with brand and state on successful fetch', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockRobots,
    } as Response)

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText('RBT-001')).toBeInTheDocument()
    })
    expect(screen.getByText('RBT-002')).toBeInTheDocument()
    expect(screen.getByText('RBT-003')).toBeInTheDocument()
    // Each robot's brand appears as a span
    expect(screen.getByText('Geek+')).toBeInTheDocument()
    expect(screen.getByText('Quicktron')).toBeInTheDocument()
    expect(screen.getByText('ForwardX')).toBeInTheDocument()
  })

  it('shows command buttons for each robot', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => mockRobots,
    } as Response)

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText('RBT-001')).toBeInTheDocument()
    })
    // 3 robots × 8 commands = 24 command buttons
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBe(24)
  })

  it('shows "No robots connected" for empty fleet', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true, json: async () => emptyRobots,
    } as Response)

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText('No robots connected')).toBeInTheDocument()
    })
  })

  it('shows error state when API fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Timeout'))

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText(/Timeout/)).toBeInTheDocument()
    })
  })

  it('disables only the clicked button while sending command', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    // First call: robot list
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => mockRobots,
    } as Response)
    // Second call: POST command — pending forever
    fetchSpy.mockResolvedValueOnce(new Promise(() => {}) as unknown as Response)

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText('RBT-001')).toBeInTheDocument()
    })

    // Click Pause on first robot (RBT-001)
    const pauseBtns = screen.getAllByRole('button', { name: /Pause/ })
    fireEvent.click(pauseBtns[0])

    // Only the clicked Pause button on RBT-001 should be disabled; all other buttons stay enabled
    await waitFor(() => {
      const allBtns = screen.getAllByRole('button')
      // The first button (Pause on RBT-001) should be disabled
      expect(allBtns[0]).toBeDisabled()
      // All other 23 buttons should remain enabled
      for (let i = 1; i < allBtns.length; i++) {
        expect(allBtns[i]).not.toBeDisabled()
      }
    })
  })

  it('shows success result after command succeeds', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => mockRobots,
    } as Response)
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => ({ ok: true }),
    } as Response)

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText('RBT-001')).toBeInTheDocument()
    })

    const pauseBtns = screen.getAllByRole('button', { name: /Pause/ })
    fireEvent.click(pauseBtns[0])

    await waitFor(() => {
      expect(screen.getByText(/Command "pause" sent/)).toBeInTheDocument()
    })
  })

  it('shows error result when command API returns error', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockResolvedValueOnce({
      ok: true, json: async () => mockRobots,
    } as Response)
    fetchSpy.mockResolvedValueOnce({
      ok: false, json: async () => ({ error: 'Robot offline' }),
    } as Response)

    render(<CommandPanel />)

    await waitFor(() => {
      expect(screen.getByText('RBT-001')).toBeInTheDocument()
    })

    const pauseBtns = screen.getAllByRole('button', { name: /Pause/ })
    fireEvent.click(pauseBtns[0])

    await waitFor(() => {
      expect(screen.getByText('Robot offline')).toBeInTheDocument()
    })
  })
})
