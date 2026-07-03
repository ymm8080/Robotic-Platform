import { useMemo } from 'react'
import { CONFIG } from '../config'
import type { RobotMap, MqttState } from '../hooks/useMqtt'
import { toRobotSummary } from '../types/vda5050'
import type { RobotDisplayState } from '../types/vda5050'
import { sortRobots, relativeTime } from '../utils/format'
import { RobotCard } from './RobotCard'

interface RobotApiStatus {
  id: string
  brand: string
  state: string
  battery: string
  lastSeen: string
  position?: { x: number; y: number }
  orderId?: string | null
}

export function RobotList({ mqtt, apiRobots, onRobotClick }: {
  mqtt: MqttState; apiRobots?: RobotApiStatus[]; onRobotClick?: (id: string) => void
}) {
  // Use MQTT data when available, fall back to API data
  const summaries = useMemo(() => {
    const mqttSummaries: ReturnType<typeof toRobotSummary>[] = []
    const now = Date.now()

    if (mqtt.robots.size > 0) {
      mqtt.robots.forEach((stream, id) => {
        const [manufacturer, serialNumber] = id.split('/')
        const summary = toRobotSummary(manufacturer, serialNumber, stream.state, stream.connection)
        if (summary.connected && stream.state) {
          const age = now - new Date(stream.state.timestamp).getTime()
          if (age > CONFIG.staleThresholdMs) {
            summary.displayState = 'UNKNOWN'
          }
        }
        mqttSummaries.push(summary)
      })
      return sortRobots(mqttSummaries)
    }

    // Fallback to API data
    if (apiRobots && apiRobots.length > 0) {
      return sortRobots(apiRobots.map(r => ({
        id: r.id,
        manufacturer: r.brand,
        serialNumber: r.id,
        displayState: (r.state || 'UNKNOWN') as RobotDisplayState,
        battery: parseFloat(r.battery) || 0,
        connected: true,
        driving: r.state === 'MOVING',
        paused: false,
        position: r.position ? { ...r.position, theta: 0 } : null,
        orderId: r.orderId || null,
        errors: [],
        operatingMode: 'AUTOMATIC',
        safetyState: { eStop: false },
        lastSeen: r.lastSeen,
      })))
    }

    return []
  }, [mqtt.robots, apiRobots])

  const online = summaries.filter(r => r.connected).length
  const errors = summaries.filter(r => r.displayState === 'ERROR').length
  const moving = summaries.filter(r => r.displayState === 'MOVING' || r.displayState === 'EXECUTING').length

  return (
    <div>
      {/* Stats bar */}
      <div style={{
        display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap',
      }}>
        <Stat label="Connection" value={mqtt.connected ? 'MQTT' : apiRobots?.length ? 'API' : 'Off'} color={mqtt.connected || (apiRobots?.length ?? 0) > 0 ? '#22c55e' : '#ef4444'} />
        <Stat label="Total" value={summaries.length} color="#3b82f6" />
        <Stat label="Online" value={online} color="#22c55e" />
        <Stat label="Running" value={moving} color="#3b82f6" />
        <Stat label="Errors" value={errors} color="#ef4444" />
      </div>

      {/* MQTT error message */}
      {mqtt.error && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
          padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 13,
        }}>
          MQTT error: {mqtt.error}
        </div>
      )}

      {/* Empty state */}
      {summaries.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 16px', color: '#9ca3af', fontSize: 14 }}>
          {mqtt.connected ? 'Waiting for robots to connect…' : 'Connecting to MQTT broker…'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {summaries.map(r => (
            <div key={r.id} onClick={() => onRobotClick?.(r.id)}
              style={{ cursor: onRobotClick ? 'pointer' : 'default' }}>
              <RobotCard robot={r} data-source={mqtt.robots.size > 0 ? 'mqtt' : 'api'} />
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{ marginTop: 12, fontSize: 11, color: '#d1d5db', textAlign: 'right' }}>
        Last update: {summaries.length > 0 ? relativeTime(summaries[0].lastSeen) : '-'}
        {apiRobots && apiRobots.length > 0 && mqtt.robots.size === 0 && ' (API mode)'}
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string | number; color: string }) {
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
