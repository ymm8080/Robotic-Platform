import { useState, useCallback } from 'react'
import { CONFIG } from '../config'
import { usePlatformState } from '../hooks/usePlatformState'

interface LockResult {
  zoneId: string
  action: 'lock' | 'unlock'
  ok: boolean
  message: string
}

export function ZoneLockdownPanel() {
  const { state, connected } = usePlatformState()
  const [customZone, setCustomZone] = useState('')
  const [sending, setSending] = useState<string | null>(null) // zone being acted on
  const [results, setResults] = useState<LockResult[]>([])

  const lockedZones = state?.locked_zones ?? []
  const lockedSet = new Set(lockedZones)

  const sendZoneAction = useCallback(async (zoneId: string, action: 'lock' | 'unlock') => {
    setSending(zoneId)
    try {
      const res = await fetch(
        `${CONFIG.apiBase}/v1/v5/zone/${encodeURIComponent(zoneId)}/${action}`,
        { method: 'POST', cache: 'no-store' },
      )
      const body = await res.json().catch(() => ({}))
      const ok = res.ok || body?.status === 'ok'
      setResults(prev => [{
        zoneId, action,
        ok,
        message: ok
          ? `Zone "${zoneId}" ${action}ed successfully`
          : `Failed: ${body?.error || `HTTP ${res.status}`}`,
      }, ...prev.slice(0, 19)]) // keep last 20 results
    } catch (err) {
      setResults(prev => [{
        zoneId, action, ok: false,
        message: `Network error: ${(err as Error).message}`,
      }, ...prev.slice(0, 19)])
    } finally {
      setSending(null)
    }
  }, [])

  const handleCustomLock = () => {
    const zone = customZone.trim()
    if (!zone) return
    sendZoneAction(zone, 'lock')
    setCustomZone('')
  }

  const handleCustomUnlock = () => {
    const zone = customZone.trim()
    if (!zone) return
    sendZoneAction(zone, 'unlock')
    setCustomZone('')
  }

  // Known zones from platform state
  const knownZones: string[] = (() => {
    const zones = new Set<string>()
    lockedZones.forEach(z => zones.add(z))
    // Also look in robot active lanes/position metadata
    if (state?.robots) {
      Object.values(state.robots).forEach(r => {
        if (r.mode !== 'IDLE') {
          // Add heuristic zones — robots typically report last node
        }
      })
    }
    return Array.from(zones).sort()
  })()

  return (
    <div>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12,
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
          🔒 Zone Lockdown
        </h2>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: connected ? '#22c55e' : '#ef4444',
          display: 'inline-block',
        }} />
      </div>

      {/* Coordinator status */}
      {!connected && (
        <div style={{
          background: '#fffbeb', border: '1px solid #fde68a', color: '#92400e',
          padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 13,
        }}>
          Coordinator not connected — zone commands are forwarded to the v5 coordinator.
          Start the traffic coordinator or check the sap-bridge ENABLE_V5 setting.
        </div>
      )}

      {/* Known locked zones */}
      <div style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
          Locked Zones ({knownZones.length})
        </h3>
        {knownZones.length === 0 ? (
          <div style={{
            textAlign: 'center', padding: 20, color: '#22c55e',
            fontSize: 13, background: '#f0fdf4', borderRadius: 6,
          }}>
            No zones currently locked — all clear
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {knownZones.map(zone => {
              const isLocked = lockedSet.has(zone)
              return (
                <div key={zone} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  background: isLocked ? '#fef2f2' : '#f0fdf4',
                  border: `1px solid ${isLocked ? '#fecaca' : '#bbf7d0'}`,
                  borderRadius: 6, padding: '8px 12px',
                }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 14, color: '#374151' }}>
                      {zone}
                    </span>
                    <span style={{
                      marginLeft: 8, fontSize: 11, fontWeight: 700,
                      color: isLocked ? '#dc2626' : '#15803d',
                    }}>
                      {isLocked ? 'LOCKED' : 'UNLOCKED'}
                    </span>
                  </div>
                  <button
                    onClick={() => sendZoneAction(zone, isLocked ? 'unlock' : 'lock')}
                    disabled={sending === zone}
                    style={{
                      padding: '4px 12px', fontSize: 12, fontWeight: 600,
                      background: sending === zone ? '#9ca3af' : (isLocked ? '#15803d' : '#dc2626'),
                      color: '#fff', border: 'none', borderRadius: 4,
                      cursor: sending === zone ? 'not-allowed' : 'pointer',
                    }}>
                    {sending === zone ? '…' : (isLocked ? 'Unlock' : 'Lock')}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Custom zone control */}
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14,
        marginBottom: 16,
      }}>
        <h3 style={{ fontSize: 13, fontWeight: 600, color: '#374151', margin: '0 0 8px' }}>
          Manual Zone Control
        </h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="text"
            value={customZone}
            onChange={e => setCustomZone(e.target.value)}
            placeholder="Zone ID (e.g. X1, L_A_B)"
            style={{
              flex: 1, padding: '6px 10px', fontSize: 13,
              border: '1px solid #d1d5db', borderRadius: 4,
            }}
            onKeyDown={e => {
              if (e.key === 'Enter') handleCustomLock()
            }}
          />
          <button onClick={handleCustomLock}
            disabled={!customZone.trim() || sending === customZone.trim()}
            style={{
              padding: '6px 14px', fontSize: 13, fontWeight: 600,
              background: !customZone.trim() ? '#d1d5db' : '#dc2626',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: !customZone.trim() ? 'not-allowed' : 'pointer',
            }}>
            Lock
          </button>
          <button onClick={handleCustomUnlock}
            disabled={!customZone.trim() || sending === customZone.trim()}
            style={{
              padding: '6px 14px', fontSize: 13, fontWeight: 600,
              background: !customZone.trim() ? '#d1d5db' : '#15803d',
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: !customZone.trim() ? 'not-allowed' : 'pointer',
            }}>
            Unlock
          </button>
        </div>
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
          Manual zone lock/unlock. Zone IDs should match facility map node/lane IDs.
        </div>
      </div>

      {/* Results log */}
      {results.length > 0 && (
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
            Command History
          </h3>
          <div style={{
            maxHeight: 200, overflowY: 'auto',
            border: '1px solid #e5e7eb', borderRadius: 6, background: '#f9fafb',
          }}>
            {results.map((r, i) => (
              <div key={i} style={{
                padding: '4px 10px', fontSize: 12,
                borderBottom: '1px solid #f3f4f6',
                color: r.ok ? '#15803d' : '#991b1b',
              }}>
                [{r.action.toUpperCase()}] {r.zoneId} — {r.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
