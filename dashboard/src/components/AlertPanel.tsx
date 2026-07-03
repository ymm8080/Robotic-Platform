import { useState, useEffect } from 'react'
import { CONFIG } from '../config'

interface AlertEntry {
  id: string
  timestamp?: string
  level: 'P0' | 'P1' | 'P2'
  service: string
  message: string
}

type SeverityFilter = 'ALL' | 'P0' | 'P1' | 'P2'

let alertSeq = 0
function nextAlertId(): string { return `alert-${Date.now()}-${++alertSeq}` }

export function AlertPanel() {
  const [alerts, setAlerts] = useState<AlertEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<SeverityFilter>('ALL')
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set())

  useEffect(() => {
    let active = true
    async function fetchAlerts() {
      try {
        // Try system health first for watchdog metrics
        const res = await fetch(`${CONFIG.apiBase}/v1/system/health`, { cache: 'no-store' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const health = await res.json()

        if (!active) return

        const entries: AlertEntry[] = []

        // Derive alerts from system health data
        if (health.resources?.safeMode) {
          entries.push({
            id: `alert-safe-mode`, level: 'P0', service: 'watchdog',
            message: 'SAFE MODE ACTIVE — all new orders rejected. Check Node-RED or Redis health.',
          })
        }
        if (health.resources?.throttleActive) {
          entries.push({
            id: `alert-throttle`, level: 'P1', service: 'watchdog',
            message: 'Throttle active — order dispatch rate reduced. CPU or checkpoint threshold exceeded.',
          })
        }
        if (health.resources?.errorRatePercent != null && health.resources.errorRatePercent > 5) {
          entries.push({
            id: `alert-error-rate`, level: health.resources.errorRatePercent > 10 ? 'P0' : 'P1',
            service: 'sap-bridge',
            message: `Error rate at ${health.resources.errorRatePercent.toFixed(1)}% (threshold: 5%). Check services.`,
          })
        }
        if (health.resources?.cpuPercent != null && health.resources.cpuPercent > 80) {
          entries.push({
            id: `alert-cpu`, level: health.resources.cpuPercent > 90 ? 'P1' : 'P2',
            service: 'nodered',
            message: `CPU at ${health.resources.cpuPercent.toFixed(0)}%. Consider scaling.`,
          })
        }
        if (health.resources?.memoryPercent != null && health.resources.memoryPercent > 85) {
          entries.push({
            id: `alert-memory`, level: health.resources.memoryPercent > 95 ? 'P1' : 'P2',
            service: 'nodered',
            message: `Memory at ${health.resources.memoryPercent.toFixed(0)}%. Risk of OOM.`,
          })
        }
        if (health.fleet?.error > 0) {
          entries.push({
            id: `alert-fleet-error`, level: health.fleet.error > 2 ? 'P1' : 'P2',
            service: 'fleet',
            message: `${health.fleet.error} robot(s) in ERROR state. Check robot detail for diagnostics.`,
          })
        }

        // Check individual services
        for (const [name, svc] of Object.entries(health.services || {}) as [string, any][]) {
          if (svc?.connected === false || svc?.status === 'disconnected') {
            const svcNames: Record<string, string> = {
              mqtt: 'MQTT Broker', redis: 'Redis', database: 'Database', watchdog: 'Watchdog',
            }
            entries.push({
              id: `alert-svc-${name}`, level: name === 'mqtt' || name === 'redis' ? 'P0' : 'P1',
              service: name,
              message: `${svcNames[name] || name} is disconnected. Robot communication may be affected.`,
            })
          }
        }

        if (active) {
          setAlerts(entries)
          setError(null)
        }
      } catch (err) {
        if (active) setError((err as Error).message)
      } finally {
        if (active) setLoading(false)
      }
    }
    fetchAlerts()
    const id = setInterval(fetchAlerts, 10000)
    return () => { active = false; clearInterval(id) }
  }, [])

  const ack = (alertId: string) => {
    setAcknowledged(prev => new Set(prev).add(alertId))
  }

  const filtered = filter === 'ALL' ? alerts : alerts.filter(a => a.level === filter)

  if (loading) return <Panel>Loading alerts…</Panel>
  if (error) return <Panel><ErrorBox msg={error} /></Panel>

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#6b7280', marginRight: 4 }}>Filter:</span>
        {(['ALL', 'P0', 'P1', 'P2'] as SeverityFilter[]).map(level => {
          const count = level === 'ALL' ? alerts.length : alerts.filter(a => a.level === level).length
          const active = filter === level
          return (
            <button key={level} onClick={() => setFilter(level)}
              style={{
                padding: '4px 10px', fontSize: 12, fontWeight: active ? 700 : 500,
                border: `1px solid ${active ? '#3b82f6' : '#e5e7eb'}`,
                borderRadius: 4, cursor: 'pointer',
                background: active ? '#3b82f6' : '#fff',
                color: active ? '#fff' : '#374151',
              }}>
              {level === 'ALL' ? 'All' : level} ({count})
            </button>
          )
        })}
      </div>

      {/* Alert list */}
      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 32, color: '#22c55e', fontSize: 14 }}>
          No active alerts
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {filtered.map((alert) => {
            const isAcked = acknowledged.has(alert.id)
            return (
              <div key={alert.id} style={{
                background: isAcked ? '#f9fafb' : levelBg(alert.level),
                border: `1px solid ${isAcked ? '#e5e7eb' : levelBorder(alert.level)}`,
                borderRadius: 8, padding: '10px 14px',
                opacity: isAcked ? 0.6 : 1,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{
                        padding: '1px 6px', borderRadius: 4, fontSize: 11, fontWeight: 700,
                        color: '#fff', background: levelColor(alert.level),
                      }}>
                        {alert.level}
                      </span>
                      <span style={{ fontSize: 11, color: '#6b7280' }}>{alert.service}</span>
                    </div>
                    <div style={{ fontSize: 13, color: '#374151' }}>{alert.message}</div>
                  </div>
                  {!isAcked && (
                    <button onClick={() => ack(alert.id)}
                      style={{
                        padding: '3px 8px', fontSize: 11, fontWeight: 600,
                        background: '#fff', color: '#374151', border: '1px solid #d1d5db',
                        borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap',
                      }}>
                      Ack
                    </button>
                  )}
                  {isAcked && (
                    <span style={{ fontSize: 11, color: '#9ca3af', whiteSpace: 'nowrap' }}>
                      ✓ Acked
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Summary */}
      <div style={{ marginTop: 12, fontSize: 11, color: '#9ca3af', textAlign: 'right' }}>
        {alerts.filter(a => !acknowledged.has(a.id)).length} unacknowledged
        &nbsp;·&nbsp; updated every 10s
      </div>
    </div>
  )
}

/* ── Helpers ── */

function levelColor(level: string): string {
  switch (level) {
    case 'P0': return '#dc2626'
    case 'P1': return '#f59e0b'
    case 'P2': return '#3b82f6'
    default: return '#9ca3af'
  }
}

function levelBg(level: string): string {
  switch (level) {
    case 'P0': return '#fef2f2'
    case 'P1': return '#fffbeb'
    case 'P2': return '#eff6ff'
    default: return '#fff'
  }
}

function levelBorder(level: string): string {
  switch (level) {
    case 'P0': return '#fecaca'
    case 'P1': return '#fde68a'
    case 'P2': return '#bfdbfe'
    default: return '#e5e7eb'
  }
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
