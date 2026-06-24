import { useState, useEffect } from 'react'
import { useMqtt } from './hooks/useMqtt'
import { RobotList } from './components/RobotList'
import { RobotDetail } from './components/RobotDetail'
import { OrderForm } from './components/OrderForm'
import { TaskList } from './components/TaskList'
import { EmergencyStop } from './components/EmergencyStop'
import { WarehouseMap } from './components/WarehouseMap'
import { BatteryPanel } from './components/BatteryPanel'
import { CONFIG } from './config'

type Tab = 'robots' | 'map' | 'battery' | 'orders' | 'tasks'

interface RobotApiStatus {
  id: string
  brand: string
  state: string
  battery: string
  lastSeen: string
}

export default function App() {
  const mqtt = useMqtt()
  const [tab, setTab] = useState<Tab>('robots')
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null)
  const [showEStop, setShowEStop] = useState(false)
  const [apiRobots, setApiRobots] = useState<RobotApiStatus[]>([])
  const [apiConnected, setApiConnected] = useState(false)

  // Poll REST API as fallback when MQTT unavailable
  useEffect(() => {
    let active = true
    async function poll() {
      try {
        const res = await fetch(`${CONFIG.apiBase}/v1/robots/status`, { cache: 'no-store' })
        if (!res.ok) throw new Error('API unavailable')
        const data = await res.json()
        if (!active) return
        if (data.robots) {
          setApiRobots(data.robots)
          setApiConnected(true)
        }
      } catch {
        if (active) setApiConnected(false)
      }
    }
    poll()
    const id = setInterval(poll, 15000)
    return () => { active = false; clearInterval(id) }
  }, [])

  const mqttRobotCount = mqtt.robots.size
  const apiRobotCount = apiRobots.length
  const hasData = mqttRobotCount > 0 || apiRobotCount > 0
  const isConnected = mqtt.connected || apiConnected

  const tabs: { key: Tab; label: string }[] = [
    { key: 'robots', label: `🤖 Robots (${mqttRobotCount || apiRobotCount})` },
    { key: 'map', label: '🗺️ Map' },
    { key: 'battery', label: '🔋 Battery' },
    { key: 'orders', label: '📦 Order' },
    { key: 'tasks', label: '📋 Tasks' },
  ]

  return (
    <div style={{
      maxWidth: 1024, margin: '0 auto', padding: '16px',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12, paddingBottom: 10, borderBottom: '2px solid #f3f4f6',
      }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
            🤖 Robot Dispatch Dashboard
          </h1>
          <p style={{ fontSize: 11, color: '#9ca3af', margin: '2px 0 0 0' }}>
            SAP-EWM · VDA5050 · {mqttRobotCount || apiRobotCount} robots
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!showEStop && (
            <button onClick={() => setShowEStop(true)}
              style={{
                padding: '8px 14px', fontSize: 14, fontWeight: 700,
                background: '#dc2626', color: '#fff', border: 'none',
                borderRadius: 8, cursor: 'pointer',
              }}>
              🚨 E-STOP
            </button>
          )}
          {/* Connection indicator */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            fontSize: 12, color: isConnected ? '#22c55e' : '#ef4444',
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: isConnected ? '#22c55e' : '#ef4444', display: 'inline-block',
            }} />
            {mqtt.connected ? 'MQTT' : apiConnected ? 'API' : 'Disconnected'}
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
            Close E-Stop
          </button>
        </div>
      )}

      {/* API disconnected warning */}
      {!isConnected && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
          padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 13,
        }}>
          Cannot reach backend — check if services are running
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
      {tab === 'robots' && hasData && (
        selectedRobotId
          ? <RobotDetail robotId={selectedRobotId} onBack={() => setSelectedRobotId(null)} mqtt={mqtt} />
          : <RobotList mqtt={mqtt} apiRobots={apiRobots} onRobotClick={id => setSelectedRobotId(id)} />
      )}
      {tab === 'robots' && !hasData && (
        <div style={{ textAlign: 'center', padding: 48, color: '#9ca3af', fontSize: 14 }}>
          {mqtt.connected ? 'Waiting for robot data…' : 'Connecting to backend…'}
        </div>
      )}
      {tab === 'map' && <WarehouseMap mqtt={mqtt} />}
      {tab === 'battery' && <BatteryPanel mqtt={mqtt} />}
      {tab === 'orders' && <OrderForm onCreated={() => setTab('tasks')} />}
      {tab === 'tasks' && <TaskList />}
    </div>
  )
}
