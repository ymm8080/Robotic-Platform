import { useMemo } from 'react'
import { CONFIG } from '../config'
import type { RobotMap, MqttState } from '../hooks/useMqtt'
import { toRobotSummary } from '../types/vda5050'
import { sortRobots, relativeTime } from '../utils/format'
import { RobotCard } from './RobotCard'

export function RobotList({ mqtt, onRobotClick }: { mqtt: MqttState; onRobotClick?: (id: string) => void }) {
  const summaries = useMemo(() => {
    const list: ReturnType<typeof toRobotSummary>[] = []
    const now = Date.now()

    mqtt.robots.forEach((stream, id) => {
      const [manufacturer, serialNumber] = id.split('/')
      const summary = toRobotSummary(manufacturer, serialNumber, stream.state, stream.connection)

      // Mark stale if no state update within threshold
      if (summary.connected && stream.state) {
        const age = now - new Date(stream.state.timestamp).getTime()
        if (age > CONFIG.staleThresholdMs) {
          summary.displayState = 'UNKNOWN'
        }
      }

      list.push(summary)
    })

    return sortRobots(list)
  }, [mqtt.robots])

  const online = summaries.filter(r => r.connected).length
  const errors = summaries.filter(r => r.displayState === 'ERROR').length
  const moving = summaries.filter(r => r.displayState === 'MOVING' || r.displayState === 'EXECUTING').length

  return (
    <div>
      {/* Stats bar */}
      <div style={{
        display: 'flex',
        gap: 16,
        marginBottom: 16,
        flexWrap: 'wrap',
      }}>
        <Stat label="连接状态" value={mqtt.connected ? '已连接' : '断开'} color={mqtt.connected ? '#22c55e' : '#ef4444'} />
        <Stat label="总机器人" value={summaries.length} color="#3b82f6" />
        <Stat label="在线" value={online} color="#22c55e" />
        <Stat label="运行中" value={moving} color="#3b82f6" />
        <Stat label="错误" value={errors} color="#ef4444" />
      </div>

      {/* Error message */}
      {mqtt.error && (
        <div style={{
          background: '#fef2f2',
          border: '1px solid #fecaca',
          color: '#b91c1c',
          padding: '8px 12px',
          borderRadius: 6,
          marginBottom: 12,
          fontSize: 13,
        }}>
          MQTT 错误: {mqtt.error}
        </div>
      )}

      {/* Robot cards */}
      {summaries.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '48px 16px',
          color: '#9ca3af',
          fontSize: 14,
        }}>
          {mqtt.connected ? '等待机器人上线…' : '正在连接 MQTT Broker…'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {summaries.map(r => (
            <div key={r.id} onClick={() => onRobotClick?.(r.id)} style={{ cursor: onRobotClick ? 'pointer' : 'default' }}>
              <RobotCard robot={r} />
            </div>
          ))}
        </div>
      )}

      {/* Footage */}
      <div style={{ marginTop: 12, fontSize: 11, color: '#d1d5db', textAlign: 'right' }}>
        最后更新: {summaries.length > 0 ? relativeTime(summaries[0].lastSeen) : '-'}
      </div>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e5e7eb',
      borderRadius: 8,
      padding: '8px 16px',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    }}>
      <span style={{ fontSize: 13, color: '#6b7280' }}>{label}</span>
      <span style={{ fontWeight: 700, fontSize: 18, color }}>{value}</span>
    </div>
  )
}
