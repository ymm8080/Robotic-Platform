import type { RobotSummary, V5RobotState } from '../types/vda5050'
import { deriveSensorHealth, sensorHealthLabel } from '../types/vda5050'
import { displayStateLabel, displayStateColor } from '../utils/format'

/** Color for v5 mode badge */
function v5ModeColor(mode: string): string {
  switch (mode) {
    case 'IDLE': return '#6b7280'
    case 'TASKING': return '#3b82f6'
    case 'CHARGING': return '#a855f7'
    case 'ERROR': return '#ef4444'
    default: return '#9ca3af'
  }
}

function v5ModeLabel(mode: string): string {
  switch (mode) {
    case 'IDLE': return '空闲'
    case 'TASKING': return '任务中'
    case 'CHARGING': return '充电中'
    case 'ERROR': return '错误'
    default: return mode
  }
}

export function RobotCard({ robot, v5Robot }: { robot: RobotSummary; v5Robot?: V5RobotState }) {
  const color = displayStateColor(robot.displayState)
  const label = displayStateLabel(robot.displayState)
  const sensorLevel = deriveSensorHealth(v5Robot?.sensor_health)
  const sensorColor = sensorLevel === 'HEALTHY' ? '#22c55e' : sensorLevel === 'DEGRADED' ? '#eab308' : '#ef4444'

  // Use v5 battery when available, fall back to VDA5050 battery
  const batteryPct = v5Robot?.battery_percent ?? robot.battery
  const batteryValue = Math.round(batteryPct)
  const batteryBarColor = batteryValue > 50 ? '#22c55e' : batteryValue > 20 ? '#eab308' : '#ef4444'

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
        {/* v5 lane_id */}
        {v5Robot?.lane_id && (
          <div style={{ fontSize: 11, color: '#8b5cf6', marginTop: 2, fontFamily: 'monospace' }}>
            Lane: {v5Robot.lane_id}
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

      {/* v5 mode badge */}
      {v5Robot?.mode && (
        <div style={{
          background: `${v5ModeColor(v5Robot.mode)}18`,
          color: v5ModeColor(v5Robot.mode),
          fontWeight: 600,
          fontSize: 12,
          padding: '4px 8px',
          borderRadius: 4,
          whiteSpace: 'nowrap',
        }}>
          {v5ModeLabel(v5Robot.mode)}
        </div>
      )}

      {/* Battery with visual bar */}
      <div style={{ textAlign: 'center', minWidth: 56 }}>
        <div style={{
          fontSize: 14,
          fontWeight: 700,
          color: batteryBarColor,
        }}>
          {batteryValue}%
        </div>
        <div style={{
          width: 40, height: 6,
          background: '#e5e7eb',
          borderRadius: 3,
          margin: '2px auto 0',
          overflow: 'hidden',
        }}>
          <div style={{
            width: `${Math.max(2, batteryValue)}%`,
            height: '100%',
            background: batteryBarColor,
            borderRadius: 3,
            transition: 'width 0.3s',
          }} />
        </div>
        <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 1 }}>电量</div>
      </div>

      {/* v5: velocity */}
      {v5Robot?.velocity !== undefined && (
        <div style={{ textAlign: 'center', minWidth: 48 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
            {v5Robot.velocity.toFixed(1)}
          </div>
          <div style={{ fontSize: 10, color: '#9ca3af' }}>m/s</div>
        </div>
      )}

      {/* v5: sensor health + degraded */}
      {v5Robot && (
        <div style={{ textAlign: 'center', minWidth: 60 }}>
          {v5Robot.degraded && (
            <div style={{
              fontSize: 10, fontWeight: 700, color: '#ef4444',
              background: '#fef2f2', padding: '1px 6px', borderRadius: 4,
              marginBottom: 2,
            }}>
              DEGRADED
            </div>
          )}
          {v5Robot.sensor_health !== undefined && (
            <div style={{ fontSize: 11, color: sensorColor }}>
              <span style={{ fontWeight: 600 }}>
                {sensorHealthLabel(sensorLevel)}
              </span>
            </div>
          )}
        </div>
      )}

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
