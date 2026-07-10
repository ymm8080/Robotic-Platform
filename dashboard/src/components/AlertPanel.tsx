import { useState, useEffect, useMemo, useRef } from 'react'
import { CONFIG } from '../config'
import { useSettings } from '../context/SettingsContext'
import { useAuth } from '../context/AuthContext'
import type { MqttState } from '../hooks/useMqtt'
import { usePlatformState } from '../hooks/usePlatformState'
import { toRobotSummary, deriveSensorHealth } from '../types/vda5050'
import { useAreaAccess } from '../hooks/useAreaAccess'

/** CowAgent alert push endpoint — use same hostname as dashboard for LAN access */
const COWAGENT_ALERT_PUSH_URL = `http://${window.location.hostname}:9899/api/alert-push`

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

interface RobotApiStatus {
  id: string
  brand: string
  state: string
  battery: string
  lastSeen: string
  position?: { x: number; y: number }
  orderId?: string | null
}

interface Props {
  mqtt?: MqttState
  apiRobots?: RobotApiStatus[]
}

interface TaskApiResponse {
  orderNo: string
  type?: string
  priority?: number
  robotBrand?: string | null
  robotSerial?: string | null
  status: string
  errorMessage?: string | null
  createdAt?: string
  completedAt?: string | null
}

export function AlertPanel({ mqtt, apiRobots }: Props) {
  const { settings } = useSettings()
  const { isAdmin, canViewRobot } = useAreaAccess()
  const { currentUser } = useAuth()
  const v5 = usePlatformState()
  const [alerts, setAlerts] = useState<AlertEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<SeverityFilter>('ALL')
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set())
  const [taskAlerts, setTaskAlerts] = useState<AlertEntry[]>([])
  const pushedAlertIds = useRef<Set<string>>(new Set())

  // ── Robot-level alerts derived from MQTT/API data + user thresholds ──
  const robotAlerts = useMemo<AlertEntry[]>(() => {
    const entries: AlertEntry[] = []
    const seen = new Set<string>()

    // From MQTT data
    if (mqtt) {
      mqtt.robots.forEach((stream, id) => {
        const [mfr, sn] = id.split('/')
        const summary = toRobotSummary(mfr, sn, stream.state, stream.connection)

        // Battery below threshold
        if (summary.battery < settings.batteryThreshold) {
          entries.push({
            id: `robot-batt-${id}`,
            level: summary.battery < (settings.batteryThreshold / 2) ? 'P0' : 'P1',
            service: 'robot',
            message: `🤖 ${id}: Battery at ${Math.round(summary.battery)}% (threshold: ${settings.batteryThreshold}%)`,
          })
        }

        // Robot in ERROR state
        if (settings.robotErrorAlertEnabled && summary.displayState === 'ERROR') {
          const errMsgs = summary.errors.map(e => e.errorDescription).filter(Boolean).join('; ')
          entries.push({
            id: `robot-err-${id}`,
            level: 'P1',
            service: 'robot',
            message: `🤖 ${id}: ERROR state${errMsgs ? ` — ${errMsgs}` : ''}`,
          })
        }

        // Robot OFFLINE
        if (settings.offlineAlertEnabled && summary.displayState === 'OFFLINE') {
          entries.push({
            id: `robot-off-${id}`,
            level: 'P2',
            service: 'robot',
            message: `🤖 ${id}: Robot is offline`,
          })
        }

        seen.add(id)
      })
    }

    // From API fallback data
    if (apiRobots) {
      for (const r of apiRobots) {
        if (seen.has(r.id)) continue
        const battery = parseFloat(r.battery) || 0
        if (battery < settings.batteryThreshold) {
          entries.push({
            id: `robot-batt-${r.id}`,
            level: battery < (settings.batteryThreshold / 2) ? 'P0' : 'P1',
            service: 'robot',
            message: `🤖 ${r.id} (${r.brand}): Battery at ${Math.round(battery)}% (threshold: ${settings.batteryThreshold}%)`,
          })
        }
        if (settings.robotErrorAlertEnabled && r.state?.toUpperCase() === 'ERROR') {
          entries.push({
            id: `robot-err-${r.id}`,
            level: 'P1',
            service: 'robot',
            message: `🤖 ${r.id}: Robot in ERROR state`,
          })
        }
        if (settings.offlineAlertEnabled && (r.state?.toUpperCase() === 'OFFLINE' || r.state?.toUpperCase() === 'UNAVAILABLE')) {
          entries.push({
            id: `robot-off-${r.id}`,
            level: 'P2',
            service: 'robot',
            message: `🤖 ${r.id}: Robot is ${r.state?.toUpperCase() || 'offline'}`,
          })
        }
        seen.add(r.id)
      }
    }

    // Filter by area access (admin sees all)
    return isAdmin ? entries : entries.filter(a => {
      // Extract robot ID from alert ID: e.g. "robot-batt-kuka/001" -> "kuka/001"
      const parts = a.id.split('-')
      if (parts.length >= 3) {
        const robotId = parts.slice(2).join('-')
        return canViewRobot(robotId)
      }
      return true // non-robot alerts always visible
    })
  // mqtt.robots Map ref changes on each state push — intentional, alerts must react to live robot state changes
  }, [mqtt?.robots, apiRobots, settings.batteryThreshold, settings.offlineAlertEnabled, settings.robotErrorAlertEnabled, isAdmin, canViewRobot])

  // ── Task-level alerts: poll every 30s ──
  useEffect(() => {
    let active = true
    async function fetchTaskAlerts() {
      try {
        const res = await fetch(`${CONFIG.apiBase}/v1/orders?limit=50`, { cache: 'no-store' })
        if (!res.ok) return
        const data = await res.json()
        if (!active) return

        const orders: TaskApiResponse[] = data.orders ?? []
        const entries: AlertEntry[] = []

        for (const o of orders) {
          const robot = o.robotBrand && o.robotSerial ? `${o.robotBrand}/${o.robotSerial}` : 'unassigned'
          if (o.status === 'FAILED') {
            entries.push({
              id: `task-fail-${o.orderNo}`,
              level: 'P1',
              service: 'task',
              message: `📋 ${o.orderNo} FAILED on ${robot}${o.errorMessage ? ` — ${o.errorMessage}` : ''}`,
            })
          }
          if (o.status === 'CANCELLED') {
            entries.push({
              id: `task-cancel-${o.orderNo}`,
              level: 'P2',
              service: 'task',
              message: `📋 ${o.orderNo} CANCELLED on ${robot}`,
            })
          }
          if (o.status === 'SUSPENDED') {
            entries.push({
              id: `task-suspend-${o.orderNo}`,
              level: 'P2',
              service: 'task',
              message: `📋 ${o.orderNo} SUSPENDED on ${robot}${o.errorMessage ? ` — ${o.errorMessage}` : ''}`,
            })
          }
        }

        if (active) setTaskAlerts(entries)
      } catch {
        // task API unavailable — not critical
      }
    }
    fetchTaskAlerts()
    const id = setInterval(fetchTaskAlerts, 30000)
    return () => { active = false; clearInterval(id) }
  }, [])

  // ── System health polling ──
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
        if (health.resources?.errorRatePercent != null && health.resources.errorRatePercent > settings.errorRateThresholdPct) {
          entries.push({
            id: `alert-error-rate`, level: health.resources.errorRatePercent > (settings.errorRateThresholdPct * 2) ? 'P0' : 'P1',
            service: 'sap-bridge',
            message: `Error rate at ${health.resources.errorRatePercent.toFixed(1)}% (threshold: ${settings.errorRateThresholdPct}%). Check services.`,
          })
        }
        if (health.resources?.cpuPercent != null && health.resources.cpuPercent > settings.cpuThreshold) {
          entries.push({
            id: `alert-cpu`, level: health.resources.cpuPercent > (settings.cpuThreshold + 10) ? 'P1' : 'P2',
            service: 'nodered',
            message: `CPU at ${health.resources.cpuPercent.toFixed(0)}% (threshold: ${settings.cpuThreshold}%). Consider scaling.`,
          })
        }
        if (health.resources?.memoryPercent != null && health.resources.memoryPercent > settings.memoryThreshold) {
          entries.push({
            id: `alert-memory`, level: health.resources.memoryPercent > (settings.memoryThreshold + 10) ? 'P1' : 'P2',
            service: 'nodered',
            message: `Memory at ${health.resources.memoryPercent.toFixed(0)}% (threshold: ${settings.memoryThreshold}%). Risk of OOM.`,
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
  }, [settings.cpuThreshold, settings.memoryThreshold, settings.errorRateThresholdPct])

  // ── v5 coordinator alerts ──
  const v5Alerts = useMemo<AlertEntry[]>(() => {
    const entries: AlertEntry[] = []
    if (!v5.state) return entries

    // Degraded robots
    Object.entries(v5.state.robots).forEach(([robotId, r]) => {
      if (r.degraded) {
        entries.push({
          id: `v5-degraded-${robotId}`,
          level: 'P1',
          service: 'coordinator',
          message: `🤖 ${robotId}: Robot is DEGRADED. Sensor health: ${r.sensor_health !== undefined ? (r.sensor_health * 100).toFixed(0) + '%' : 'unknown'}`,
        })
      }
      const health = deriveSensorHealth(r.sensor_health)
      if (health === 'CRITICAL') {
        entries.push({
          id: `v5-sensor-crit-${robotId}`,
          level: 'P0',
          service: 'coordinator',
          message: `🤖 ${robotId}: Sensor health CRITICAL (${r.sensor_health !== undefined ? (r.sensor_health * 100).toFixed(0) + '%' : 'unknown'}). Robot may be unsafe.`,
        })
      }
    })

    // Zone lockdowns
    if (v5.state.locked_zones.length > 0) {
      entries.push({
        id: 'v5-zones-locked',
        level: 'P2',
        service: 'coordinator',
        message: `🔒 ${v5.state.locked_zones.length} zone(s) locked: ${v5.state.locked_zones.join(', ')}`,
      })
    }

    // Coordinator health degraded
    if (v5.health && v5.health.status !== 'healthy') {
      entries.push({
        id: 'v5-coordinator-health',
        level: v5.health.status === 'degraded' ? 'P1' : 'P0',
        service: 'coordinator',
        message: `v5 Coordinator status: ${v5.health.status}. Mode: ${v5.health.mode}.`,
      })
    }

    // Coordinator disconnected
    if (!v5.connected && v5.error) {
      entries.push({
        id: 'v5-coordinator-down',
        level: 'P1',
        service: 'coordinator',
        message: `v5 Coordinator unreachable: ${v5.error}`,
      })
    }

    return entries
  }, [v5.state, v5.health, v5.connected, v5.error])

  // Merge all alert sources
  const allAlerts = useMemo(() => {
    const merged = [...alerts, ...robotAlerts, ...taskAlerts, ...v5Alerts]
    // Dedup by id (robotAlerts have stable ids)
    const seen = new Set<string>()
    return merged.filter(a => {
      if (seen.has(a.id)) return false
      seen.add(a.id)
      return true
    })
  }, [alerts, robotAlerts, taskAlerts])

  const ack = (alertId: string) => {
    setAcknowledged(prev => new Set(prev).add(alertId))
  }

  // ── Push new alerts to CowAgent (WeChat + Email) ──
  useEffect(() => {
    const newAlerts = allAlerts.filter(a => !pushedAlertIds.current.has(a.id))
    if (newAlerts.length === 0) return
    // Mark as pushed immediately to prevent duplicates
    newAlerts.forEach(a => pushedAlertIds.current.add(a.id))
    const payload = {
      alerts: newAlerts.map(a => ({
        id: a.id,
        level: a.level,
        service: a.service,
        message: a.message,
        timestamp: a.timestamp || new Date().toISOString(),
      })),
      user_email: currentUser?.email || '',
    }
    fetch(COWAGENT_ALERT_PUSH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => { /* CowAgent may be offline; silently ignore */ })
  }, [allAlerts, currentUser])

  const filtered = filter === 'ALL' ? allAlerts : allAlerts.filter(a => a.level === filter)

  if (loading) return <Panel>Loading alerts…</Panel>
  if (error) return <Panel><ErrorBox msg={error} /></Panel>

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#6b7280', marginRight: 4 }}>Filter:</span>
        {(['ALL', 'P0', 'P1', 'P2'] as SeverityFilter[]).map(level => {
          const count = level === 'ALL' ? allAlerts.length : allAlerts.filter(a => a.level === level).length
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
        {allAlerts.filter(a => !acknowledged.has(a.id)).length} unacknowledged
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
