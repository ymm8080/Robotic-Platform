import { useMemo, useState } from 'react'
import type { MqttState } from '../hooks/useMqtt'
import { toRobotSummary } from '../types/vda5050'
import type { RobotDisplayState } from '../types/vda5050'
import { batteryColor, displayStateLabel, relativeTime, displayStateColor } from '../utils/format'
import { apiRobotsToDisplay, type ApiRobot } from '../utils/api-adapter'
import { useAreaAccess } from '../hooks/useAreaAccess'

type SortField = 'battery' | 'state' | 'id' | 'updated'
type SortDir = 'asc' | 'desc'

interface Props {
  mqtt: MqttState
  apiRobots?: ApiRobot[]
}

export function BatteryPanel({ mqtt, apiRobots }: Props) {
  const [sortField, setSortField] = useState<SortField>('battery')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const { isAdmin, canViewRobot } = useAreaAccess()

  const robots = useMemo(() => {
    const seen = new Set<string>()
    const list: {
      id: string
      battery: number
      state: RobotDisplayState
      lastSeen: string
      connected: boolean
    }[] = []

    // 1. MQTT data first (real-time, higher fidelity)
    mqtt.robots.forEach((stream, id) => {
      const [mfr, sn] = id.split('/')
      const summary = toRobotSummary(mfr, sn, stream.state, stream.connection)
      seen.add(id)
      list.push({
        id,
        battery: Math.round(summary.battery),
        state: summary.displayState,
        lastSeen: summary.lastSeen,
        connected: summary.connected,
      })
    })

    // 2. API data as fallback (REST, available without MQTT broker)
    if (apiRobots) {
      for (const r of apiRobotsToDisplay(apiRobots)) {
        if (!seen.has(r.id)) {
          seen.add(r.id)
          list.push(r)
        }
      }
    }

    // Filter by area access (admin sees all)
    const filtered = isAdmin ? list : list.filter(r => canViewRobot(r.id))

    filtered.sort((a, b) => {
      let cmp = 0
      if (sortField === 'battery') cmp = a.battery - b.battery
      else if (sortField === 'state') cmp = a.state.localeCompare(b.state)
      else if (sortField === 'id') cmp = a.id.localeCompare(b.id)
      else if (sortField === 'updated') cmp = a.lastSeen.localeCompare(b.lastSeen)
      return sortDir === 'asc' ? cmp : -cmp
    })

    return filtered
  }, [mqtt.robots, apiRobots, sortField, sortDir, isAdmin, canViewRobot])

  const lowBattery = robots.filter(r => r.battery < 20 && r.connected).length
  const charging = robots.filter(r => r.state === 'CHARGING').length

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  function SortIcon({ field }: { field: SortField }) {
    if (sortField !== field) return <span style={{ color: '#d1d5db' }}> ↕</span>
    return <span>{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>
  }

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>🔋 电量总览</h3>
        <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
          <span style={{ color: '#ef4444' }}>低电量: {lowBattery}</span>
          <span style={{ color: '#a855f7' }}>充电中: {charging}</span>
          <span style={{ color: '#6b7280' }}>总计: {robots.length}</span>
        </div>
      </div>

      {robots.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13 }}>
          暂无机器人数据
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb' }}>
                <Th onClick={() => toggleSort('id')}>机器人 <SortIcon field="id" /></Th>
                <Th onClick={() => toggleSort('battery')}>电量 <SortIcon field="battery" /></Th>
                <Th>电量条</Th>
                <Th onClick={() => toggleSort('state')}>状态 <SortIcon field="state" /></Th>
                <Th onClick={() => toggleSort('updated')}>最后更新 <SortIcon field="updated" /></Th>
              </tr>
            </thead>
            <tbody>
              {robots.map(r => (
                <tr key={r.id} style={{
                  borderBottom: '1px solid #f3f4f6',
                  opacity: r.connected ? 1 : 0.5,
                }}>
                  <td style={{ padding: '6px 4px', fontWeight: 600 }}>{r.id}</td>
                  <td style={{ padding: '6px 4px', fontWeight: 700, color: batteryColor(r.battery) }}>
                    {r.battery}%
                  </td>
                  <td style={{ padding: '6px 4px', width: 120 }}>
                    <div style={{
                      height: 8, width: 100, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden',
                    }}>
                      <div style={{
                        height: '100%', width: `${Math.min(100, r.battery)}%`,
                        background: batteryColor(r.battery), borderRadius: 4,
                        transition: 'width 0.5s',
                      }} />
                    </div>
                  </td>
                  <td style={{ padding: '6px 4px' }}>
                    <span style={{
                      display: 'inline-block', padding: '1px 6px', borderRadius: 10,
                      fontSize: 11, fontWeight: 600,
                      background: `${displayStateColor(r.state)}18`,
                      color: displayStateColor(r.state),
                    }}>
                      {displayStateLabel(r.state)}
                    </span>
                  </td>
                  <td style={{ padding: '6px 4px', color: '#9ca3af', fontSize: 11 }}>
                    {r.lastSeen ? relativeTime(r.lastSeen) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Low battery alert banner */}
      {lowBattery > 0 && (
        <div style={{
          marginTop: 8, padding: '6px 10px', borderRadius: 4,
          background: '#fef2f2', border: '1px solid #fecaca',
          fontSize: 12, color: '#991b1b',
        }}>
          ⚠️ {lowBattery} 台机器人电量低于 20%，建议安排充电
        </div>
      )}
    </div>
  )
}

function Th({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <th onClick={onClick} style={{
      padding: '6px 4px', fontSize: 12, color: '#6b7280',
      fontWeight: 600, textAlign: 'left', cursor: onClick ? 'pointer' : 'default',
      userSelect: 'none',
    }}>
      {children}
    </th>
  )
}