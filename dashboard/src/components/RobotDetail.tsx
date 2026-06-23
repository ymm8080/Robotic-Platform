import { useMemo } from 'react'
import type { MqttState } from '../hooks/useMqtt'
import type { RobotSummary } from '../types/vda5050'
import { toRobotSummary } from '../types/vda5050'
import { displayStateLabel, displayStateColor, relativeTime } from '../utils/format'

export function RobotDetail({ robotId, mqtt, onBack }: {
  robotId: string; mqtt: MqttState; onBack: () => void
}) {
  const robot = useMemo<RobotSummary | null>(() => {
    const stream = mqtt.robots.get(robotId)
    if (!stream) return null
    const [mfr, sn] = robotId.split('/')
    return toRobotSummary(mfr, sn, stream.state, stream.connection)
  }, [robotId, mqtt.robots])

  if (!robot) {
    return (
      <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af' }}>
        机器人 {robotId} 不在线
        <br /><button onClick={onBack} style={backBtnStyle}>返回</button>
      </div>
    )
  }

  const state = robot
  const color = displayStateColor(state.displayState)
  const label = displayStateLabel(state.displayState)

  return (
    <div>
      <button onClick={onBack} style={backBtnStyle}>← 返回列表</button>

      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20, marginTop: 12,
      }}>
        {/* Heading */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>{robotId}</h2>
            <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }}>
              {state.manufacturer} · {state.operatingMode}
            </div>
          </div>
          <div style={{
            background: `${color}18`, color, fontWeight: 700, fontSize: 14,
            padding: '6px 14px', borderRadius: 20,
          }}>
            {label}
          </div>
        </div>

        {/* Info grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <InfoItem label="电量" value={`${Math.round(state.battery)}%`} />
          <InfoItem label="连接" value={state.connected ? '在线' : '离线'} />
          <InfoItem label="驾驶中" value={state.driving ? '是' : '否'} />
          <InfoItem label="已暂停" value={state.paused ? '是' : '否'} />
          <InfoItem label="当前位置" value={
            state.position ? `(${state.position.x.toFixed(1)}, ${state.position.y.toFixed(1)}, ${state.position.theta.toFixed(0)}°)` : '未知'
          } />
          <InfoItem label="当前任务" value={state.orderId || '-'} />
          <InfoItem label="最后更新" value={state.lastSeen ? relativeTime(state.lastSeen) : '-'} />
          <InfoItem label="急停状态" value={state.safetyState.eStop ? '⚠️ 急停!' : '正常'} />
        </div>

        {/* Errors */}
        {state.errors.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 14, color: '#ef4444' }}>错误 ({state.errors.length})</h4>
            {state.errors.map((e, i) => (
              <div key={i} style={{
                background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 4,
                padding: '6px 10px', marginBottom: 4, fontSize: 13,
              }}>
                <strong>[{e.errorLevel}]</strong> {e.errorType}
                {e.errorDescription && <span> — {e.errorDescription}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: '6px 0' }}>
      <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 500 }}>{value}</div>
    </div>
  )
}

const backBtnStyle: React.CSSProperties = {
  padding: '6px 14px', fontSize: 13, border: '1px solid #d1d5db',
  borderRadius: 4, background: '#fff', cursor: 'pointer',
}
