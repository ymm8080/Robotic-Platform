import type { RobotSummary } from '../types/vda5050'
import { displayStateLabel, displayStateColor } from '../utils/format'

export function RobotCard({ robot }: { robot: RobotSummary }) {
  const color = displayStateColor(robot.displayState)
  const label = displayStateLabel(robot.displayState)

  return (
    <div style={{
      background: '#fff',
      border: `1px solid ${robot.connected ? '#e5e7eb' : '#fecaca'}`,
      borderLeft: `4px solid ${color}`,
      borderRadius: 8,
      padding: '12px 16px',
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      opacity: robot.connected ? 1 : 0.6,
    }}>
      {/* ID + state */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 15 }}>{robot.id}</div>
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
          {robot.manufacturer} · {robot.serialNumber}
        </div>
        {robot.orderId && (
          <div style={{ fontSize: 12, color: '#3b82f6', marginTop: 2 }}>
            任务: {robot.orderId}
          </div>
        )}
      </div>

      {/* State badge */}
      <div style={{
        background: `${color}18`,
        color,
        fontWeight: 600,
        fontSize: 13,
        padding: '4px 10px',
        borderRadius: 20,
        whiteSpace: 'nowrap',
      }}>
        {label}
      </div>

      {/* Battery */}
      <div style={{ textAlign: 'center', minWidth: 48 }}>
        <div style={{
          fontSize: 14,
          fontWeight: 600,
          color: robot.battery > 50 ? '#22c55e' : robot.battery > 20 ? '#eab308' : '#ef4444',
        }}>
          {Math.round(robot.battery)}%
        </div>
        <div style={{ fontSize: 10, color: '#9ca3af' }}>电量</div>
      </div>

      {/* Position / errors */}
      <div style={{ minWidth: 80, textAlign: 'right', fontSize: 12, color: '#6b7280' }}>
        {robot.position ? (
          <div>({robot.position.x.toFixed(1)}, {robot.position.y.toFixed(1)})</div>
        ) : (
          <div style={{ color: '#d1d5db' }}>—</div>
        )}
        {robot.errors.length > 0 && (
          <div style={{ color: '#ef4444', fontSize: 11, marginTop: 2 }}>
            ⚠ {robot.errors.length} 错误
          </div>
        )}
        {robot.safetyState.eStop && (
          <div style={{ color: '#ef4444', fontSize: 11, fontWeight: 600 }}>急停!</div>
        )}
      </div>
    </div>
  )
}
