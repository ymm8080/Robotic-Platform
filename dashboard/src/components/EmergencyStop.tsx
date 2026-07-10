import { useState, useEffect } from 'react'
import { CONFIG } from '../config'
import { usePlatformState } from '../hooks/usePlatformState'

interface RobotInfo {
  id: string
  brand: string
  state: string
  battery: string
}

export function EmergencyStop() {
  const v5 = usePlatformState()
  const [confirming, setConfirming] = useState(false)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [zoneResult, setZoneResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [robots, setRobots] = useState<RobotInfo[]>([])
  const [targetRobotId, setTargetRobotId] = useState('*')
  const [loadingRobots, setLoadingRobots] = useState(true)

  // Fetch live robot list
  useEffect(() => {
    fetch(`${CONFIG.apiBase}/v1/robots/status`, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : Promise.reject('unavailable'))
      .then(data => {
        if (data.robots?.length) {
          setRobots(data.robots)
        }
      })
      .catch(() => {})
      .finally(() => setLoadingRobots(false))
  }, [])

  async function handleEStop() {
    setSending(true)
    setResult(null)

    const targets = targetRobotId === '*'
      ? robots
      : robots.filter(r => r.id === targetRobotId)

    if (targets.length === 0) {
      setResult({ ok: false, msg: 'No robots to stop' })
      setSending(false)
      return
    }

    try {
      const results = await Promise.allSettled(
        targets.map(robot =>
          fetch(`${CONFIG.apiBase}/v1/robots/${encodeURIComponent(robot.id)}/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'stop' }),
          }).then(async r => {
            const body = await r.json()
            if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`)
            return { robotId: robot.id, ok: true }
          })
        )
      )

      const succeeded = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length

      if (targetRobotId !== '*') {
        setResult({
          ok: succeeded > 0,
          msg: succeeded > 0
            ? `E-Stop sent to ${targetRobotId}`
            : `E-Stop failed for ${targetRobotId}`,
        })
      } else {
        setResult({
          ok: succeeded > 0,
          msg: `E-Stop sent to ${succeeded} robot(s)${failed > 0 ? `, ${failed} failed` : ''}`,
        })
      }
    } catch (err) {
      setResult({ ok: false, msg: `Send failed: ${(err as Error).message}` })
    } finally {
      setSending(false)
      setConfirming(false)
    }
  }

  if (!confirming) {
    return (
      <button onClick={() => setConfirming(true)}
        style={{
          width: '100%', padding: '20px', fontSize: 28, fontWeight: 800,
          background: '#dc2626', color: '#fff', border: 'none', borderRadius: 12,
          cursor: 'pointer', boxShadow: '0 4px 12px rgba(220,38,38,0.4)',
          letterSpacing: 2,
        }}>
        🚨 EMERGENCY STOP
      </button>
    )
  }

  const onlineRobots = robots.filter(r => r.state !== 'UNAVAILABLE')
  const hasRobots = onlineRobots.length > 0

  return (
    <div style={{
      background: '#fef2f2', border: '3px solid #dc2626', borderRadius: 12, padding: 20,
    }}>
      <h3 style={{ margin: '0 0 12px', color: '#991b1b', fontSize: 18 }}>
        ⚠️ Confirm Emergency Stop
      </h3>
      <p style={{ fontSize: 14, color: '#7f1d1d', marginBottom: 12 }}>
        This sends an instant emergency stop command (VDA5050 instantAction). The robot will halt immediately.
      </p>

      {loadingRobots ? (
        <div style={{ textAlign: 'center', padding: 12, color: '#9ca3af', fontSize: 13 }}>
          Loading robot list…
        </div>
      ) : !hasRobots ? (
        <div style={{ textAlign: 'center', padding: 12, color: '#991b1b', fontSize: 13 }}>
          No online robots available
        </div>
      ) : (
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
            Target Robot
          </label>
          <select value={targetRobotId} onChange={e => setTargetRobotId(e.target.value)}
            style={{ width: '100%', padding: '8px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}>
            <option value="*">All robots ({onlineRobots.length})</option>
            {onlineRobots.map(r => (
              <option key={r.id} value={r.id}>
                {r.id} — {r.brand} [{r.state}] {r.battery}
              </option>
            ))}
          </select>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={handleEStop} disabled={sending || !hasRobots}
          style={{
            flex: 1, padding: '12px', fontSize: 16, fontWeight: 700,
            background: sending || !hasRobots ? '#9ca3af' : '#dc2626', color: '#fff',
            border: 'none', borderRadius: 8, cursor: sending || !hasRobots ? 'not-allowed' : 'pointer',
          }}>
          {sending ? 'Sending…' : 'Confirm Stop'}
        </button>
        <button onClick={() => { setConfirming(false); setResult(null) }}
          style={{
            padding: '12px 20px', fontSize: 14, background: '#fff', color: '#374151',
            border: '1px solid #d1d5db', borderRadius: 8, cursor: 'pointer',
          }}>
          Cancel
        </button>
      </div>

      {result && (
        <div style={{
          marginTop: 12, padding: 8, borderRadius: 4, fontSize: 13,
          background: result.ok ? '#f0fdf4' : '#fef2f2',
          color: result.ok ? '#15803d' : '#991b1b',
        }}>
          {result.msg}
        </div>
      )}

      {/* v5 zone lockdown */}
      {v5.connected && v5.state && (
        <div style={{
          marginTop: 16, padding: 14, background: '#f9fafb',
          border: '1px solid #e5e7eb', borderRadius: 8,
        }}>
          <h4 style={{ fontSize: 13, fontWeight: 600, color: '#374151', margin: '0 0 6px' }}>
            🔒 v5 Zone Lockdown
          </h4>
          <p style={{ fontSize: 12, color: '#6b7280', margin: '0 0 8px' }}>
            Lock all zones to prevent robot movement. Unlock to resume.
          </p>
          {v5.state.locked_zones.length > 0 ? (
            <div>
              <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 6 }}>
                {v5.state.locked_zones.length} zone(s) locked: {v5.state.locked_zones.join(', ')}
              </div>
              <button onClick={async () => {
                setZoneResult(null)
                try {
                  const results = await Promise.allSettled(
                    v5.state!.locked_zones.map(z =>
                      fetch(`${CONFIG.apiBase}/v1/v5/zone/${encodeURIComponent(z)}/unlock`,
                        { method: 'POST' })
                    )
                  )
                  const ok = results.filter(r => r.status === 'fulfilled').length
                  setZoneResult({ ok: ok > 0, msg: `Unlocked ${ok}/${results.length} zones` })
                } catch (err) {
                  setZoneResult({ ok: false, msg: `Unlock failed: ${(err as Error).message}` })
                }
              }}
                style={{
                  padding: '6px 14px', fontSize: 13, fontWeight: 600,
                  background: '#15803d', color: '#fff', border: 'none',
                  borderRadius: 4, cursor: 'pointer',
                }}>
                Unlock All Zones
              </button>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: '#22c55e' }}>
              No zones locked — all clear
            </div>
          )}
          {zoneResult && (
            <div style={{
              marginTop: 8, padding: 6, borderRadius: 4, fontSize: 12,
              background: zoneResult.ok ? '#f0fdf4' : '#fef2f2',
              color: zoneResult.ok ? '#15803d' : '#991b1b',
            }}>
              {zoneResult.msg}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
