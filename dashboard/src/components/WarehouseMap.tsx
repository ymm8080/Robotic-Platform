import { useMemo, useState } from 'react'
import type { MqttState } from '../hooks/useMqtt'
import { toRobotSummary } from '../types/vda5050'
import type { RobotDisplayState } from '../types/vda5050'
import { displayStateColor, displayStateLabel } from '../utils/format'

// Define warehouse zones
interface Zone {
  id: string
  label: string
  x: number
  y: number
  w: number
  h: number
  color: string
}

const ZONES: Zone[] = [
  { id: 'RECEIVING', label: '收货区', x: 10, y: 10, w: 180, h: 120, color: '#dbeafe' },
  { id: 'STORAGE-A', label: '高货架 A', x: 210, y: 10, w: 200, h: 280, color: '#f3e8ff' },
  { id: 'STORAGE-B', label: '高货架 B', x: 430, y: 10, w: 200, h: 280, color: '#fce7f3' },
  { id: 'PICKING', label: '拣选区', x: 650, y: 10, w: 180, h: 120, color: '#d1fae5' },
  { id: 'SHIPPING', label: '发货区', x: 650, y: 150, w: 180, h: 140, color: '#fef3c7' },
  { id: 'CHARGING', label: '充电站', x: 10, y: 160, w: 180, h: 130, color: '#e0e7ff' },
]

const CANVAS_W = 850
const CANVAS_H = 310
const ROBOT_R = 10

export function WarehouseMap({ mqtt }: { mqtt: MqttState }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  const robots = useMemo(() => {
    const list: { id: string; x: number; y: number; state: RobotDisplayState; battery: number }[] = []
    mqtt.robots.forEach((stream, id) => {
      const [mfr, sn] = id.split('/')
      const summary = toRobotSummary(mfr, sn, stream.state, stream.connection)
      if (summary.position && summary.connected) {
        // Map robot coords to canvas coords
        const px = Math.max(ROBOT_R, Math.min(CANVAS_W - ROBOT_R,
          10 + (summary.position.x / 100) * (CANVAS_W - 20)
        ))
        const py = Math.max(ROBOT_R, Math.min(CANVAS_H - ROBOT_R,
          10 + (summary.position.y / 100) * (CANVAS_H - 20)
        ))
        list.push({
          id,
          x: px,
          y: py,
          state: summary.displayState,
          battery: Math.round(summary.battery),
        })
      }
    })
    return list
  }, [mqtt.robots])

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 15, fontWeight: 600 }}>🏭 仓库地图</h3>

      <svg viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} style={{ width: '100%', height: 'auto', maxHeight: 320 }}>
        {/* Zones */}
        {ZONES.map(z => (
          <g key={z.id}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h}
              fill={z.color} stroke="#cbd5e1" strokeWidth={1} rx={4} />
            <text x={z.x + z.w / 2} y={z.y + 16}
              textAnchor="middle" fontSize={11} fill="#475569" fontWeight={600}>
              {z.label}
            </text>
          </g>
        ))}

        {/* Grid lines */}
        {Array.from({ length: 9 }, (_, i) => (
          <line key={`v${i}`} x1={(i + 1) * CANVAS_W / 10} y1={0}
            x2={(i + 1) * CANVAS_W / 10} y2={CANVAS_H}
            stroke="#f1f5f9" strokeWidth={0.5} />
        ))}
        {Array.from({ length: 4 }, (_, i) => (
          <line key={`h${i}`} x1={0} y1={(i + 1) * CANVAS_H / 5}
            x2={CANVAS_W} y2={(i + 1) * CANVAS_H / 5}
            stroke="#f1f5f9" strokeWidth={0.5} />
        ))}

        {/* Robots */}
        {robots.map(r => {
          const color = displayStateColor(r.state)
          const isHovered = hoveredId === r.id
          return (
            <g key={r.id}
              onMouseEnter={() => setHoveredId(r.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{ cursor: 'pointer', transition: 'all 0.3s' }}
            >
              {/* Glow for ERROR */}
              {r.state === 'ERROR' && (
                <circle cx={r.x} cy={r.y} r={ROBOT_R + 4}
                  fill="none" stroke="#ef4444" strokeWidth={2} opacity={0.5}>
                  <animate attributeName="r" values="12;16;12" dur="1s" repeatCount="indefinite" />
                </circle>
              )}
              {/* Robot dot */}
              <circle cx={r.x} cy={r.y} r={isHovered ? ROBOT_R + 3 : ROBOT_R}
                fill={color} stroke="#fff" strokeWidth={2}
                opacity={r.state === 'OFFLINE' ? 0.4 : 1} />
              {/* Battery indicator */}
              <text x={r.x} y={r.y - ROBOT_R - 4} textAnchor="middle"
                fontSize={9} fill={r.battery > 20 ? '#22c55e' : '#ef4444'}
                fontWeight={700}>
                {r.battery}%
              </text>
              {/* Tooltip */}
              {isHovered && (
                <g>
                  <rect x={r.x - 40} y={r.y + ROBOT_R + 4} width={80} height={28}
                    rx={4} fill="#1f2937" opacity={0.9} />
                  <text x={r.x} y={r.y + ROBOT_R + 20} textAnchor="middle"
                    fontSize={10} fill="#fff" fontWeight={600}>
                    {r.id} · {displayStateLabel(r.state)}
                  </text>
                </g>
              )}
            </g>
          )
        })}

        {/* Legend */}
        <g transform="translate(10, 290)">
          <text x={0} y={0} fontSize={10} fill="#6b7280">
            机器人: {robots.length} 在线 · {mqtt.robots.size - robots.length} 无位置
          </text>
        </g>
      </svg>

      {robots.length === 0 && (
        <div style={{ textAlign: 'center', padding: 20, color: '#9ca3af', fontSize: 13 }}>
          {mqtt.connected ? '等待机器人位置更新…' : '未连接 MQTT'}
        </div>
      )}
    </div>
  )
}
