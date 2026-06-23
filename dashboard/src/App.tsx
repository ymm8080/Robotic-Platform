import { useState } from 'react'
import { useMqtt } from './hooks/useMqtt'
import { RobotList } from './components/RobotList'
import { RobotDetail } from './components/RobotDetail'
import { OrderForm } from './components/OrderForm'
import { TaskList } from './components/TaskList'

type Tab = 'robots' | 'orders' | 'tasks'

export default function App() {
  const mqtt = useMqtt()
  const [tab, setTab] = useState<Tab>('robots')
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null)

  const tabs: { key: Tab; label: string }[] = [
    { key: 'robots', label: '🤖 机器人' },
    { key: 'orders', label: '📦 下单' },
    { key: 'tasks', label: '📋 任务' },
  ]

  return (
    <div style={{
      maxWidth: 960,
      margin: '0 auto',
      padding: '24px 16px',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 16, paddingBottom: 12, borderBottom: '2px solid #f3f4f6',
      }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
            🤖 机器人调度看板
          </h1>
          <p style={{ fontSize: 12, color: '#9ca3af', margin: '4px 0 0 0' }}>
            SAP-EWM 机器人调度平台 · VDA5050 实时监控
          </p>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          fontSize: 13, color: mqtt.connected ? '#22c55e' : '#ef4444',
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: mqtt.connected ? '#22c55e' : '#ef4444', display: 'inline-block',
          }} />
          {mqtt.connected ? 'MQTT 已连接' : 'MQTT 断开'}
        </div>
      </div>

      {/* Tab nav */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => { setTab(t.key); setSelectedRobotId(null) }}
            style={{
              padding: '8px 16px', fontSize: 14, fontWeight: tab === t.key ? 700 : 500,
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
      {tab === 'orders' && <OrderForm onCreated={() => setTab('tasks')} />}
      {tab === 'tasks' && <TaskList />}
    </div>
  )
}
