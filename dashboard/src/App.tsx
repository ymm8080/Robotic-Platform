import { useState } from 'react'
import { useMqtt } from './hooks/useMqtt'
import { RobotList } from './components/RobotList'
import { RobotDetail } from './components/RobotDetail'
import { OrderForm } from './components/OrderForm'
import { TaskList } from './components/TaskList'
import { EmergencyStop } from './components/EmergencyStop'
import { WarehouseMap } from './components/WarehouseMap'
import { BatteryPanel } from './components/BatteryPanel'

type Tab = 'robots' | 'map' | 'battery' | 'orders' | 'tasks'

export default function App() {
  const mqtt = useMqtt()
  const [tab, setTab] = useState<Tab>('robots')
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null)
  const [showEStop, setShowEStop] = useState(false)

  const tabs: { key: Tab; label: string }[] = [
    { key: 'robots', label: '🤖 机器人' },
    { key: 'map', label: '🗺️ 地图' },
    { key: 'battery', label: '🔋 电量' },
    { key: 'orders', label: '📦 下单' },
    { key: 'tasks', label: '📋 任务' },
  ]

  return (
    <div style={{
      maxWidth: 1024,
      margin: '0 auto',
      padding: '16px',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12, paddingBottom: 10, borderBottom: '2px solid #f3f4f6',
      }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
            🤖 机器人调度看板
          </h1>
          <p style={{ fontSize: 11, color: '#9ca3af', margin: '2px 0 0 0' }}>
            SAP-EWM · VDA5050 · {mqtt.robots.size} 台机器人
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* E-Stop button (compact) */}
          {!showEStop && (
            <button onClick={() => setShowEStop(true)}
              style={{
                padding: '8px 14px', fontSize: 14, fontWeight: 700,
                background: '#dc2626', color: '#fff', border: 'none',
                borderRadius: 8, cursor: 'pointer',
              }}>
              🚨 急停
            </button>
          )}
          {/* Connection indicator */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            fontSize: 12, color: mqtt.connected ? '#22c55e' : '#ef4444',
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: mqtt.connected ? '#22c55e' : '#ef4444', display: 'inline-block',
            }} />
            {mqtt.connected ? '已连接' : '断开'}
          </div>
        </div>
      </div>

      {/* E-Stop panel */}
      {showEStop && (
        <div style={{ marginBottom: 12 }}>
          <EmergencyStop />
          <button onClick={() => setShowEStop(false)}
            style={{
              marginTop: 4, padding: '4px 12px', fontSize: 12,
              border: 'none', background: 'none', color: '#6b7280',
              cursor: 'pointer', textDecoration: 'underline',
            }}>
            收起急停面板
          </button>
        </div>
      )}

      {/* Tab nav */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 12, flexWrap: 'wrap' }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => { setTab(t.key); setSelectedRobotId(null) }}
            style={{
              padding: '6px 14px', fontSize: 13, fontWeight: tab === t.key ? 700 : 500,
              border: 'none', borderRadius: 6, cursor: 'pointer',
              background: tab === t.key ? '#3b82f6' : '#f3f4f6',
              color: tab === t.key ? '#fff' : '#374151',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === 'robots' && (
        selectedRobotId
          ? <RobotDetail robotId={selectedRobotId} onBack={() => setSelectedRobotId(null)} mqtt={mqtt} />
          : <RobotList mqtt={mqtt} onRobotClick={id => setSelectedRobotId(id)} />
      )}
      {tab === 'map' && <WarehouseMap mqtt={mqtt} />}
      {tab === 'battery' && <BatteryPanel mqtt={mqtt} />}
      {tab === 'orders' && <OrderForm onCreated={() => setTab('tasks')} />}
      {tab === 'tasks' && <TaskList />}
    </div>
  )
}
