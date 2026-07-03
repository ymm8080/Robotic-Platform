import { useState, useEffect } from 'react'
import { CONFIG } from '../config'

interface ServiceStatus {
  status: string
  connected?: boolean
  uptimeSeconds?: number
}

interface Resources {
  safeMode?: boolean
  throttleActive?: boolean
  cpuPercent?: number
  memoryPercent?: number
  errorRatePercent?: number
  noderedStatus?: string
  sapBridgeStatus?: string
  mqttStatus?: string
}

interface FleetSummary {
  total: number
  online: number
  error: number
  moving: number
  idle: number
  charging: number
}

interface SystemHealthData {
  timestamp: string
  services: Record<string, ServiceStatus>
  resources: Resources
  fleet: FleetSummary
  version: string
}

export function SystemHealth() {
  const [data, setData] = useState<SystemHealthData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    async function fetchHealth() {
      try {
        const res = await fetch(`${CONFIG.apiBase}/v1/system/health`, { cache: 'no-store' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json()
        if (active) { setData(json); setError(null) }
      } catch (err) {
        if (active) setError((err as Error).message)
      } finally {
        if (active) setLoading(false)
      }
    }
    fetchHealth()
    const id = setInterval(fetchHealth, 10000)
    return () => { active = false; clearInterval(id) }
  }, [])

  if (loading) return <Panel title="System Health">Loading…</Panel>
  if (error) return <Panel title="System Health"><ErrorBox msg={error} /></Panel>
  if (!data) return <Panel title="System Health">No data</Panel>

  const serviceNames: Record<string, string> = {
    sapBridge: 'SAP Bridge',
    mqtt: 'MQTT Broker',
    redis: 'Redis',
    database: 'Database',
    watchdog: 'Watchdog',
  }

  const svcOrder = ['sapBridge', 'mqtt', 'redis', 'database', 'watchdog']

  return (
    <div>
      {/* Service status grid */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
        gap: 10, marginBottom: 16,
      }}>
        {svcOrder.map(key => {
          const svc = data.services[key]
          const ok = svc?.connected ?? (svc?.status === 'healthy')
          return (
            <div key={key} style={{
              background: '#fff', border: `2px solid ${ok ? '#22c55e' : '#ef4444'}`,
              borderRadius: 8, padding: 12, textAlign: 'center',
            }}>
              <div style={{
                width: 12, height: 12, borderRadius: '50%',
                background: ok ? '#22c55e' : '#ef4444',
                display: 'inline-block', marginBottom: 6,
              }} />
              <div style={{ fontSize: 13, fontWeight: 600 }}>{serviceNames[key] || key}</div>
              <div style={{ fontSize: 11, color: ok ? '#15803d' : '#991b1b' }}>
                {svc?.status || 'unknown'}
              </div>
              {svc?.uptimeSeconds !== undefined && (
                <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 2 }}>
                  {fmtUptime(svc.uptimeSeconds)}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Resource gauges row */}
      {data.resources && Object.keys(data.resources).length > 0 && (
        <div style={{
          display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16,
        }}>
          {data.resources.cpuPercent != null && (
            <Gauge label="CPU" value={data.resources.cpuPercent} unit="%"
              warn={70} crit={85} />
          )}
          {data.resources.memoryPercent != null && (
            <Gauge label="Memory" value={data.resources.memoryPercent} unit="%"
              warn={80} crit={95} />
          )}
          {data.resources.errorRatePercent != null && (
            <Gauge label="Error Rate" value={data.resources.errorRatePercent} unit="%"
              warn={3} crit={10} />
          )}
        </div>
      )}

      {/* Fleet summary */}
      <div style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 8px', color: '#374151' }}>
          Fleet Status
        </h3>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Stat label="Total" value={data.fleet.total} color="#3b82f6" />
          <Stat label="Online" value={data.fleet.online} color="#22c55e" />
          <Stat label="Moving" value={data.fleet.moving} color="#3b82f6" />
          <Stat label="Idle" value={data.fleet.idle} color="#9ca3af" />
          <Stat label="Errors" value={data.fleet.error} color="#ef4444" />
          <Stat label="Charging" value={data.fleet.charging} color="#a855f7" />
        </div>
      </div>

      {/* Safety indicators */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {data.resources?.safeMode && (
          <div style={{
            background: '#fef2f2', border: '2px solid #dc2626', color: '#991b1b',
            padding: '6px 14px', borderRadius: 6, fontSize: 13, fontWeight: 700,
          }}>
            SAFE MODE ACTIVE
          </div>
        )}
        {data.resources?.throttleActive && (
          <div style={{
            background: '#fffbeb', border: '2px solid #f59e0b', color: '#92400e',
            padding: '6px 14px', borderRadius: 6, fontSize: 13, fontWeight: 700,
          }}>
            THROTTLE ACTIVE
          </div>
        )}
      </div>

      {/* Timestamp */}
      <div style={{ marginTop: 12, fontSize: 10, color: '#d1d5db', textAlign: 'right' }}>
        Updated: {data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '-'}
        &nbsp;·&nbsp; v{data.version}
      </div>
    </div>
  )
}

/* ── Helper sub-components ── */

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 12px' }}>{title}</h2>
      <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 14 }}>
        {children}
      </div>
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

function Gauge({ label, value, unit, warn, crit }: {
  label: string; value: number; unit: string; warn: number; crit: number
}) {
  const color = value >= crit ? '#ef4444' : value >= warn ? '#f59e0b' : '#22c55e'
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
      padding: '10px 14px', minWidth: 120, flex: 1,
    }}>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value.toFixed(0)}{unit}</div>
      <div style={{
        height: 4, background: '#f3f4f6', borderRadius: 2, marginTop: 6, overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: color,
          borderRadius: 2, transition: 'width 0.5s',
        }} />
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
      padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <span style={{ fontSize: 13, color: '#6b7280' }}>{label}</span>
      <span style={{ fontWeight: 700, fontSize: 18, color }}>{value}</span>
    </div>
  )
}

function fmtUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}
