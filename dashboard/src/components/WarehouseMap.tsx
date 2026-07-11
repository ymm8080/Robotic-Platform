import { useMemo, useState } from 'react'
import type { MqttState } from '../hooks/useMqtt'
import { usePlatformState } from '../hooks/usePlatformState'
import { toRobotSummary } from '../types/vda5050'
import type { RobotDisplayState } from '../types/vda5050'
import { displayStateColor, displayStateLabel, relativeTime } from '../utils/format'
import { apiRobotsToDisplay, type ApiRobot } from '../utils/api-adapter'
import { useAreaAccess } from '../hooks/useAreaAccess'
import { loadAreas, type WareArea } from '../hooks/useAreas'

const CANVAS_W = 850
const CANVAS_H = 310
const ROBOT_R = 10

interface MapRobot {
  id: string; x: number; y: number; state: RobotDisplayState; battery: number
  brand?: string; lastSeen?: string; orderId?: string | null; areaId?: string
  returningToCharge?: boolean; chargingStation?: { id: string; x: number; y: number }
  /** v5-specific mode for color-coding (when MQTT state unavailable) */
  v5Mode?: string
}

/** Map v5 mode to display state for color-coding */
function v5ModeToState(mode: string): RobotDisplayState {
  switch (mode) {
    case 'IDLE': return 'IDLE'
    case 'TASKING': return 'MOVING'
    case 'CHARGING': return 'CHARGING'
    case 'ERROR': return 'ERROR'
    default: return 'UNKNOWN'
  }
}

/** Color for v5 robot dot: green=IDLE, blue=TASKING, yellow=CHARGING, red=ERROR */
function v5RobotDotColor(mode: string): string {
  switch (mode) {
    case 'IDLE': return '#22c55e'     // green
    case 'TASKING': return '#3b82f6'  // blue
    case 'CHARGING': return '#eab308' // yellow
    case 'ERROR': return '#ef4444'    // red
    default: return '#9ca3af'
  }
}

interface Props {
  mqtt: MqttState
  apiRobots?: ApiRobot[]
}

export function WarehouseMap({ mqtt, apiRobots }: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [selectedRobot, setSelectedRobot] = useState<MapRobot | null>(null)
  const { isAdmin, userAreaIds, canViewRobot, canViewArea, robotAreaId } = useAreaAccess()

  // Get v5 platform state for lane graph and v5 robot data
  const { state: v5State } = usePlatformState()

  // Load warehouse areas → zones
  const allZones = loadAreas().map((area: WareArea) => ({
    id: area.id,
    label: area.name,
    x: area.zoneX,
    y: area.zoneY,
    w: area.zoneW,
    h: area.zoneH,
    color: area.zoneColor,
  }))

  // Filter zones by user access
  const visibleZones = useMemo(() => {
    if (isAdmin) return allZones
    return allZones.filter(z => canViewArea(z.id))
  }, [allZones, isAdmin, canViewArea])

  function toCanvas(pos: { x: number; y: number }): { x: number; y: number } {
    return {
      x: Math.max(ROBOT_R, Math.min(CANVAS_W - ROBOT_R, pos.x)),
      y: Math.max(ROBOT_R, Math.min(CANVAS_H - ROBOT_R, pos.y)),
    }
  }

  // Get zone for a robot based on area assignment
  function areaZoneForRobot(id: string) {
    const areaId = robotAreaId(id)
    if (!areaId) return null
    return allZones.find(z => z.id === areaId) || null
  }

  const { displayRobots, stations } = useMemo(() => {
    const seen = new Set<string>()
    const list: MapRobot[] = []

    // 1. v5 robots from platform state (with pose positions)
    if (v5State?.robots) {
      Object.entries(v5State.robots).forEach(([id, v5r]) => {
        seen.add(id)
        const pos = v5r.pose
        const cv = toCanvas({ x: pos[0], y: pos[1] })
        list.push({
          id,
          x: cv.x,
          y: cv.y,
          state: v5ModeToState(v5r.mode),
          battery: Math.round(v5r.battery_percent ?? 50),
          brand: id,
          areaId: robotAreaId(id),
          v5Mode: v5r.mode,
        })
      })
    }

    // 2. MQTT robots with real positions (overrides v5 if already seen)
    mqtt.robots.forEach((stream, id) => {
      const [mfr, sn] = id.split('/')
      const summary = toRobotSummary(mfr, sn, stream.state, stream.connection)
      seen.add(id)
      if (summary.position && summary.connected) {
        const cv = toCanvas(summary.position)
        // Replace v5 entry or add new
        const existing = list.findIndex(r => r.id === id)
        const entry: MapRobot = {
          id, x: cv.x, y: cv.y, state: summary.displayState,
          battery: Math.round(summary.battery), brand: `${mfr}/${sn}`,
          lastSeen: summary.lastSeen, orderId: summary.orderId,
          areaId: robotAreaId(id),
        }
        if (existing >= 0) {
          list[existing] = { ...list[existing], ...entry }
        } else {
          list.push(entry)
        }
      }
    })

    // 3. API robots (for positions not covered by MQTT)
    const csMap: { id: string; x: number; y: number; assignedRobot: string | null; occupied: boolean }[] = []
    if (apiRobots) {
      let apiIdx = 0
      for (const r of apiRobotsToDisplay(apiRobots)) {
        if (seen.has(r.id) || !r.connected) continue
        seen.add(r.id)

        let cv: { x: number; y: number }
        if (r.position) {
          cv = toCanvas(r.position)
        } else {
          const zone = areaZoneForRobot(r.id)
          const offsetX = (apiIdx % 3) * 30 - 30
          const offsetY = Math.floor(apiIdx / 3) * 20 - 10
          if (zone) {
            cv = {
              x: Math.max(ROBOT_R, Math.min(CANVAS_W - ROBOT_R, zone.x + zone.w / 2 + offsetX)),
              y: Math.max(ROBOT_R, Math.min(CANVAS_H - ROBOT_R, zone.y + zone.h / 2 + offsetY)),
            }
          } else {
            cv = { x: CANVAS_W / 2 + offsetX, y: CANVAS_H / 2 + offsetY }
          }
        }
        apiIdx++

        const aid = robotAreaId(r.id)
        list.push({
          id: r.id, x: cv.x, y: cv.y, state: r.state, battery: r.battery,
          brand: r.brand, lastSeen: r.lastSeen, orderId: r.orderId,
          areaId: aid,
          returningToCharge: r.returningToCharge,
          chargingStation: r.chargingStation,
        })
        if (r.chargingStation && !csMap.find(s => s.id === r.chargingStation!.id)) {
          const scv = toCanvas(r.chargingStation)
          csMap.push({
            id: r.chargingStation.id, x: scv.x, y: scv.y,
            assignedRobot: r.id,
            occupied: r.state === 'CHARGING' || !!r.returningToCharge,
          })
        }
      }
    }

    return { displayRobots: list, stations: csMap }
  }, [mqtt.robots, apiRobots, v5State, robotAreaId, allZones])

  // Filter robots by area access
  const { filteredRobots, filteredStations } = useMemo(() => {
    const filtered = displayRobots.filter(r => canViewRobot(r.id))
    const filteredStationIds = new Set(
      filtered.filter(r => r.chargingStation).map(r => r.chargingStation!.id)
    )
    const fStations = stations.filter(cs => filteredStationIds.has(cs.id))
    return { filteredRobots: filtered, filteredStations: fStations }
  }, [displayRobots, stations, canViewRobot])

  const positioned = filteredRobots.length

  // Count robots by v5 mode for legend
  const modeCounts = useMemo(() => {
    const counts: Record<string, number> = { IDLE: 0, TASKING: 0, CHARGING: 0, ERROR: 0 }
    filteredRobots.forEach(r => {
      const mode = r.v5Mode || (() => {
        switch (r.state) {
          case 'MOVING': case 'EXECUTING': return 'TASKING'
          case 'CHARGING': return 'CHARGING'
          case 'ERROR': return 'ERROR'
          default: return 'IDLE'
        }
      })()
      counts[mode] = (counts[mode] ?? 0) + 1
    })
    return counts
  }, [filteredRobots])

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>🏭 仓库地图</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', fontSize: 11 }}>
          {v5State?.lane_graph && (
            <span style={{ color: '#8b5cf6' }}>Lane graph active</span>
          )}
          {!isAdmin && userAreaIds.length > 0 && (
            <span style={{ color: '#6b7280' }}>
              Showing {visibleZones.length}/{allZones.length} zones
            </span>
          )}
        </div>
      </div>

      <svg viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} style={{ width: '100%', height: 'auto', maxHeight: 320 }}>
        {/* Dynamic zones from warehouse areas */}
        {visibleZones.map(z => (
          <g key={z.id}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h}
              fill={z.color} stroke="#cbd5e1" strokeWidth={1} rx={4} />
            <text x={z.x + z.w / 2} y={z.y + 16}
              textAnchor="middle" fontSize={11} fill="#475569" fontWeight={600}>
              {z.label}
            </text>
            <text x={z.x + z.w / 2} y={z.y + 32}
              textAnchor="middle" fontSize={9} fill="#9ca3af">
              {z.id}
            </text>
          </g>
        ))}

        {/* Dimmed inaccessible zones for non-admin */}
        {!isAdmin && allZones.filter(z => !canViewArea(z.id)).map(z => (
          <g key={z.id} opacity={0.15}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h}
              fill="#e5e7eb" stroke="#d1d5db" strokeWidth={0.5} rx={4} />
            <text x={z.x + z.w / 2} y={z.y + 16}
              textAnchor="middle" fontSize={9} fill="#9ca3af">
              {z.label} (restricted)
            </text>
          </g>
        ))}

        {/* v5 Lane graph edges */}
        {v5State?.lane_graph?.edges?.map(edge => (
          <g key={edge.id}>
            {(() => {
              const fromNode = v5State.lane_graph?.nodes.find(n => n.id === edge.from)
              const toNode = v5State.lane_graph?.nodes.find(n => n.id === edge.to)
              if (!fromNode || !toNode) return null
              return (
                <line
                  x1={fromNode.x} y1={fromNode.y}
                  x2={toNode.x} y2={toNode.y}
                  stroke="#cbd5e1" strokeWidth={2}
                  strokeLinecap="round"
                />
              )
            })()}
          </g>
        ))}

        {/* v5 Lane graph nodes */}
        {v5State?.lane_graph?.nodes?.map(node => (
          <g key={node.id}>
            <circle cx={node.x} cy={node.y} r={4}
              fill="#94a3b8" stroke="#fff" strokeWidth={1.5} />
            <text x={node.x} y={node.y - 8}
              textAnchor="middle" fontSize={8} fill="#64748b">
              {node.id}
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

        {/* Charging stations */}
        {filteredStations.map(cs => (
          <g key={cs.id}>
            <rect x={cs.x - 8} y={cs.y - 8} width={16} height={16}
              fill={cs.occupied ? '#22c55e' : '#e5e7eb'}
              stroke={cs.occupied ? '#15803d' : '#9ca3af'} strokeWidth={1.5} rx={3} />
            <text x={cs.x} y={cs.y + 4} textAnchor="middle" fontSize={11}>🔌</text>
            <text x={cs.x} y={cs.y + 18} textAnchor="middle" fontSize={8} fill="#6b7280">
              {cs.id}
            </text>
            {cs.assignedRobot && filteredRobots.find(r => r.id === cs.assignedRobot) && (
              <line
                x1={cs.x} y1={cs.y - 8}
                x2={filteredRobots.find(r => r.id === cs.assignedRobot)!.x}
                y2={filteredRobots.find(r => r.id === cs.assignedRobot)!.y}
                stroke={cs.occupied ? '#22c55e' : '#d1d5db'}
                strokeWidth={1} strokeDasharray="4,3" opacity={0.5}
              />
            )}
          </g>
        ))}

        {/* Robots - color-coded by v5 mode */}
        {filteredRobots.map(r => {
          // Determine color: v5 mode takes priority, fallback to displayState
          const v5Color = r.v5Mode ? v5RobotDotColor(r.v5Mode) : null
          const color = v5Color ?? displayStateColor(r.state)
          const isHovered = hoveredId === r.id
          return (
            <g key={r.id}
              onMouseEnter={() => setHoveredId(r.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => setSelectedRobot(selectedRobot?.id === r.id ? null : r)}
              style={{ cursor: 'pointer', transition: 'all 0.3s' }}
            >
              {r.state === 'ERROR' && (
                <circle cx={r.x} cy={r.y} r={ROBOT_R + 4}
                  fill="none" stroke="#ef4444" strokeWidth={2} opacity={0.5}>
                  <animate attributeName="r" values="12;16;12" dur="1s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={r.x} cy={r.y} r={isHovered ? ROBOT_R + 3 : ROBOT_R}
                fill={color} stroke="#fff" strokeWidth={2}
                opacity={r.state === 'OFFLINE' ? 0.4 : 1} />
              <text x={r.x} y={r.y - ROBOT_R - 4} textAnchor="middle"
                fontSize={9} fill={r.battery > 20 ? '#22c55e' : '#ef4444'}
                fontWeight={700}>
                {r.battery}%
              </text>
              {isHovered && (
                <g>
                  <rect x={r.x - 45} y={r.y + ROBOT_R + 4} width={90} height={32}
                    rx={4} fill="#1f2937" opacity={0.9} />
                  <text x={r.x} y={r.y + ROBOT_R + 18} textAnchor="middle"
                    fontSize={9} fill="#fff" fontWeight={600}>
                    {r.id}
                  </text>
                  <text x={r.x} y={r.y + ROBOT_R + 28} textAnchor="middle"
                    fontSize={8} fill="#9ca3af">
                    {r.v5Mode ? `Mode: ${r.v5Mode}` : displayStateLabel(r.state)} · ({r.x.toFixed(0)}, {r.y.toFixed(0)})
                  </text>
                </g>
              )}
            </g>
          )
        })}

        {/* Legend */}
        <g transform="translate(10, 290)">
          {/* v5 mode color legend */}
          <circle cx={5} cy={-8} r={5} fill="#22c55e" />
          <text x={13} y={-5} fontSize={9} fill="#6b7280">IDLE</text>
          <circle cx={55} cy={-8} r={5} fill="#3b82f6" />
          <text x={63} y={-5} fontSize={9} fill="#6b7280">TASKING</text>
          <circle cx={125} cy={-8} r={5} fill="#eab308" />
          <text x={133} y={-5} fontSize={9} fill="#6b7280">CHARGING</text>
          <circle cx={195} cy={-8} r={5} fill="#ef4444" />
          <text x={203} y={-5} fontSize={9} fill="#6b7280">ERROR</text>
          <text x={255} y={-5} fontSize={9} fill="#6b7280">
            · {positioned} robots
          </text>
          {!isAdmin && (
            <text x={340} y={-5} fontSize={9} fill="#f59e0b">
              · 区域过滤生效
            </text>
          )}
        </g>
      </svg>

      {positioned === 0 && (
        <div style={{ textAlign: 'center', padding: 20, color: '#9ca3af', fontSize: 13 }}>
          {mqtt.connected ? '等待机器人位置更新…' : '未连接机器人数据源'}
          {!isAdmin && userAreaIds.length > 0 && ' (或当前区域无机器人)'}
        </div>
      )}

      {selectedRobot && (
        <div style={{
          marginTop: 12, background: '#fff',
          border: `2px solid ${selectedRobot.v5Mode ? v5RobotDotColor(selectedRobot.v5Mode) : displayStateColor(selectedRobot.state)}`,
          borderRadius: 8, padding: 14,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <h4 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>
              {selectedRobot.id}
              {selectedRobot.v5Mode && (
                <span style={{
                  marginLeft: 8, fontSize: 11, fontWeight: 600,
                  color: v5RobotDotColor(selectedRobot.v5Mode),
                }}>
                  [{selectedRobot.v5Mode}]
                </span>
              )}
              {selectedRobot.brand && (
                <span style={{ fontSize: 12, color: '#9ca3af', marginLeft: 6, fontWeight: 400 }}>
                  {selectedRobot.brand}
                </span>
              )}
            </h4>
            <button onClick={() => setSelectedRobot(null)}
              style={{ padding: '2px 8px', fontSize: 12, border: 'none', background: '#f3f4f6',
                borderRadius: 4, cursor: 'pointer', color: '#6b7280' }}>
              ✕
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
            <div>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>状态</div>
              <span style={{
                display: 'inline-block', padding: '2px 8px', borderRadius: 10,
                fontSize: 12, fontWeight: 600,
                background: selectedRobot.v5Mode
                  ? `${v5RobotDotColor(selectedRobot.v5Mode)}20`
                  : `${displayStateColor(selectedRobot.state)}20`,
                color: selectedRobot.v5Mode
                  ? v5RobotDotColor(selectedRobot.v5Mode)
                  : displayStateColor(selectedRobot.state),
              }}>
                {selectedRobot.v5Mode ?? displayStateLabel(selectedRobot.state)}
                {selectedRobot.returningToCharge && ' → 🔌'}
              </span>
            </div>
            <div>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>电量</div>
              <div style={{ fontWeight: 700, color: selectedRobot.battery > 20 ? '#22c55e' : '#ef4444' }}>
                {selectedRobot.battery}%
              </div>
            </div>
            <div>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>位置 (仓库坐标)</div>
              <div style={{ fontFamily: 'monospace', fontSize: 12 }}>
                X: {selectedRobot.x.toFixed(0)} · Y: {selectedRobot.y.toFixed(0)}
              </div>
            </div>
            <div>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>仓库区域</div>
              <div style={{ fontSize: 12, color: selectedRobot.areaId ? '#3b82f6' : '#9ca3af', fontWeight: 600 }}>
                {selectedRobot.areaId || '未分配'}
              </div>
            </div>
            <div>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>充电站</div>
              <div style={{ fontSize: 12 }}>
                {selectedRobot.chargingStation
                  ? `${selectedRobot.chargingStation.id} (${selectedRobot.chargingStation.x}, ${selectedRobot.chargingStation.y})`
                  : '—'}
              </div>
            </div>
            <div>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>当前任务</div>
              <div style={{ fontSize: 12, color: selectedRobot.orderId ? '#374151' : '#9ca3af' }}>
                {selectedRobot.orderId || '空闲 (无任务)'}
              </div>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <div style={{ color: '#9ca3af', fontSize: 11, marginBottom: 2 }}>最后更新</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                {selectedRobot.lastSeen ? relativeTime(selectedRobot.lastSeen) : '—'}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
