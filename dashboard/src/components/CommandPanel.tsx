import { useState, useEffect, useRef } from 'react'
import { CONFIG } from '../config'

interface RobotInfo {
  id: string
  brand: string
  state: string
  battery: string
  lastSeen: string
}

type CommandAction = 'pause' | 'resume' | 'stop' | 'cancel_order' | 'recharge' | 'reboot' | 'stateRequest' | 'factsheetRequest'

const COMMAND_LABELS: Record<CommandAction, { label: string; color: string; icon: string }> = {
  pause:             { label: 'Pause',            color: '#f59e0b', icon: '⏸️' },
  resume:            { label: 'Resume',           color: '#22c55e', icon: '▶️' },
  stop:              { label: 'Stop',             color: '#dc2626', icon: '🛑' },
  cancel_order:      { label: 'Cancel Order',     color: '#ef4444', icon: '❌' },
  recharge:          { label: 'Recharge',         color: '#22c55e', icon: '🔋' },
  reboot:            { label: 'Reboot',           color: '#8b5cf6', icon: '🔄' },
  stateRequest:      { label: 'State',            color: '#6b7280', icon: '📡' },
  factsheetRequest:  { label: 'Factsheet',        color: '#6b7280', icon: '📋' },
}

interface Props {
  onRefresh?: () => void
}

export function CommandPanel({ onRefresh }: Props) {
  const [robots, setRobots] = useState<RobotInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, { ok: boolean; msg: string } | null>>({})
  const pollRef = useRef<() => Promise<void>>(async () => {})

  useEffect(() => {
    let active = true
    async function poll() {
      try {
        const res = await fetch(`${CONFIG.apiBase}/v1/robots/status`, { cache: 'no-store' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (active) { setRobots(data.robots || []); setError(null) }
      } catch (err) {
        if (active) setError((err as Error).message)
      } finally {
        if (active) setLoading(false)
      }
    }
    pollRef.current = poll
    poll()
    const id = setInterval(poll, 5000)
    return () => { active = false; clearInterval(id) }
  }, [])
  async function sendCommand(robotId: string, action: CommandAction) {
    setSending(`${robotId}:${action}`)
    setResults(prev => ({ ...prev, [robotId]: null }))
    try {
      const res = await fetch(`${CONFIG.apiBase}/v1/robots/${encodeURIComponent(robotId)}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      const data = await res.json()
      if (res.ok) {
        setResults(prev => ({ ...prev, [robotId]: { ok: true, msg: `Command "${action}" sent` } }))
        // Brief delay to let backend process before refreshing state
        setTimeout(() => {
          pollRef.current()
          onRefresh?.()
        }, action === 'reboot' ? 1500 : 300)
      } else {
        setResults(prev => ({ ...prev, [robotId]: { ok: false, msg: data.error || 'Failed' } }))
      }
    } catch (err) {
      setResults(prev => ({ ...prev, [robotId]: { ok: false, msg: (err as Error).message } }))
    } finally {
      setSending(null)
    }
  }

  if (loading) return <Panel>Loading robots…</Panel>
  if (error) return <Panel><ErrorBox msg={error} /></Panel>
  if (robots.length === 0) return <Panel>No robots connected</Panel>

  return (
    <div>
      <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 12px' }}>
        Send VDA5050 instantActions commands to connected robots.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {robots.map(robot => {
          const busy = sending?.startsWith(robot.id + ':')
          const result = results[robot.id]
          return (
            <div key={robot.id} style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12,
            }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                flexWrap: 'wrap', gap: 8,
              }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>
                    {robot.id}
                    <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 8 }}>
                      {robot.brand}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    State: <StateBadge state={robot.state} />
                    &nbsp;·&nbsp; Battery: {robot.battery}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {(Object.keys(COMMAND_LABELS) as CommandAction[]).map(action => {
                    const { label, color, icon } = COMMAND_LABELS[action]
                    const isBusy = busy && sending === `${robot.id}:${action}`
                    return (
                      <button key={action} onClick={() => sendCommand(robot.id, action)}
                        disabled={!!sending}
                        style={{
                          padding: '5px 10px', fontSize: 12, fontWeight: 600,
                          background: color, color: '#fff', border: 'none',
                          borderRadius: 4, cursor: sending ? 'not-allowed' : 'pointer',
                          opacity: sending ? 0.5 : 1,
                        }}>
                        {isBusy ? '⋯' : icon} {label}
                      </button>
                    )
                  })}
                </div>
              </div>
              {result && (
                <div style={{
                  marginTop: 8, padding: '4px 8px', borderRadius: 4, fontSize: 12,
                  background: result.ok ? '#f0fdf4' : '#fef2f2',
                  color: result.ok ? '#15803d' : '#991b1b',
                }}>
                  {result.msg}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── Sub-components ── */

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 14 }}>
      {children}
    </div>
  )
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div style={{
      background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
      padding: '8px 12px', borderRadius: 6, fontSize: 13,
    }}>
      API unavailable: {msg}
    </div>
  )
}

function StateBadge({ state }: { state: string }) {
  const colors: Record<string, string> = {
    ONLINE: '#22c55e', MOVING: '#3b82f6', EXECUTING: '#f59e0b',
    ERROR: '#ef4444', CHARGING: '#a855f7', IDLE: '#6b7280',
    PAUSED: '#f97316', UNAVAILABLE: '#9ca3af',
  }
  const bg = colors[state.toUpperCase()] || '#9ca3af'
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: 4,
      background: bg, color: '#fff', fontSize: 11, fontWeight: 600,
    }}>
      {state}
    </span>
  )
}
