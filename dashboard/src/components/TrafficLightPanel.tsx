import { usePlatformState } from '../hooks/usePlatformState'
import type { V5IntersectionState } from '../types/vda5050'

function trafficLightColor(state: string): string {
  switch (state) {
    case 'GREEN': return '#22c55e'
    case 'YELLOW': return '#eab308'
    case 'RED': return '#ef4444'
    default: return '#9ca3af'
  }
}

function trafficLightBg(state: string): string {
  switch (state) {
    case 'GREEN': return '#f0fdf4'
    case 'YELLOW': return '#fefce8'
    case 'RED': return '#fef2f2'
    default: return '#f9fafb'
  }
}

/** Format timer value (seconds) as mm:ss */
function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function TrafficLightPanel() {
  const { state, health, connected, error, refresh } = usePlatformState()

  // Derive intersection states from coordinator platform state
  // Priority 1: explicit intersections field from /v1/v5/state
  // Priority 2: fallback from metrics + locked_zones
  const intersections: V5IntersectionState[] = (() => {
    if (!state) return []

    // Use explicit intersection data if provided by the API
    if (state.intersections && Object.keys(state.intersections).length > 0) {
      return Object.values(state.intersections)
    }

    // Fallback: derive from metrics + locked_zones
    const results: V5IntersectionState[] = []
    const locked = new Set(state.locked_zones)

    const intersectionKeys = Object.keys(state.metrics)
      .filter(k => k.startsWith('intersection_'))
      .map(k => k.replace('intersection_', ''))

    if (intersectionKeys.length > 0) {
      for (const node of intersectionKeys) {
        const stateVal = (state.metrics[`intersection_${node}`] ?? 0) as 0 | 1 | 2
        const waiting = state.metrics[`waiting_${node}`] ?? 0
        const timer = state.metrics[`timer_${node}`] ?? 0
        const laneKeys = Object.keys(state.metrics)
          .filter(k => k.startsWith(`lane_${node}_`))
        const lanes: Record<string, { state: 'RED' | 'YELLOW' | 'GREEN'; robot_id?: string }> = {}
        for (const k of laneKeys) {
          const laneId = k.replace(`lane_${node}_`, '')
          const isLocked = locked.has(laneId) || locked.has(node)
          lanes[laneId] = {
            state: isLocked ? 'RED' : 'GREEN',
          }
        }
        results.push({
          intersection_id: node,
          state: ['GREEN', 'YELLOW', 'RED'][Math.min(stateVal, 2)] as 'RED' | 'YELLOW' | 'GREEN',
          robots_waiting: waiting,
          timer,
          lanes,
        })
      }
    }

    // Fallback: derive from locked zones alone
    if (results.length === 0 && locked.size > 0) {
      const lanes: Record<string, { state: 'RED' | 'YELLOW' | 'GREEN' }> = {}
      locked.forEach(zone => {
        lanes[zone] = { state: 'RED' }
      })
      results.push({
        intersection_id: 'X1',
        state: 'RED',
        robots_waiting: 0,
        timer: 0,
        lanes,
      })
    }

    return results
  })()

  return (
    <div>
      {/* Header with refresh + coordinator status */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12,
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
          🚦 Traffic Lights
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: connected ? '#22c55e' : '#ef4444',
            display: 'inline-block',
          }} />
          <span style={{ fontSize: 12, color: connected ? '#22c55e' : '#ef4444' }}>
            {connected ? 'v5 Coordinator' : 'Disconnected'}
          </span>
          {health && (
            <span style={{ fontSize: 11, color: '#9ca3af' }}>
              v{health.version}
            </span>
          )}
          <button onClick={refresh}
            style={{
              padding: '4px 10px', fontSize: 11, fontWeight: 500,
              border: '1px solid #d1d5db', borderRadius: 4,
              background: '#fff', cursor: 'pointer',
            }}>
            Refresh
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
          padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 13,
        }}>
          Coordinator unreachable: {error}
        </div>
      )}

      {/* Empty state */}
      {!connected && !error && (
        <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 14 }}>
          Waiting for coordinator connection…
          <br />
          <span style={{ fontSize: 12, marginTop: 4, display: 'inline-block' }}>
            Start the traffic coordinator or set ENABLE_V5=true on sap-bridge
          </span>
        </div>
      )}

      {/* No intersections */}
      {connected && intersections.length === 0 && (
        <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 14 }}>
          No intersections configured
          <br />
          <span style={{ fontSize: 12, marginTop: 4, display: 'inline-block' }}>
            Add intersections to the facility map YAML to see traffic lights
          </span>
        </div>
      )}

      {/* Intersection cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {intersections.map(intersection => (
          <div key={intersection.intersection_id} style={{
            background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14,
          }}>
            <div style={{
              fontSize: 14, fontWeight: 600, marginBottom: 10,
              color: '#374151', display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span>Intersection {intersection.intersection_id}</span>
              {/* Overall intersection state */}
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 8px', borderRadius: 12,
                fontSize: 11, fontWeight: 700,
                background: trafficLightBg(intersection.state),
                color: trafficLightColor(intersection.state),
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: trafficLightColor(intersection.state),
                  display: 'inline-block',
                }} />
                {intersection.state}
              </span>
            </div>

            {/* Robots waiting + timer */}
            <div style={{
              display: 'flex', gap: 16, marginBottom: 10,
              fontSize: 12, color: '#6b7280',
            }}>
              <div>
                <span style={{ fontWeight: 600, color: '#374151' }}>
                  {intersection.robots_waiting}
                </span> robots waiting
              </div>
              <div>
                Timer: <span style={{ fontWeight: 600, color: '#374151' }}>
                  {formatTimer(intersection.timer)}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.keys(intersection.lanes).length > 0
                ? Object.entries(intersection.lanes).map(([laneId, lane]) => (
                  <div key={laneId} style={{
                    background: trafficLightBg(lane.state),
                    border: `2px solid ${trafficLightColor(lane.state)}`,
                    borderRadius: 8, padding: '8px 14px',
                    minWidth: 100, textAlign: 'center',
                  }}>
                    <div style={{
                      width: 16, height: 16, borderRadius: '50%',
                      background: trafficLightColor(lane.state),
                      margin: '0 auto 6px',
                      boxShadow: `0 0 8px ${trafficLightColor(lane.state)}80`,
                    }} />
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#374151' }}>
                      {laneId}
                    </div>
                    <div style={{
                      fontSize: 11, fontWeight: 700, marginTop: 2,
                      color: trafficLightColor(lane.state),
                    }}>
                      {lane.state}
                    </div>
                    {lane.robot_id && (
                      <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 1 }}>
                        {lane.robot_id}
                      </div>
                    )}
                  </div>
                )) : (
                  <div style={{ fontSize: 12, color: '#9ca3af', padding: '8px 0' }}>
                    No lanes — waiting for map data
                  </div>
                )}
            </div>
          </div>
        ))}
      </div>

      {/* Platform overview stats */}
      {state && (
        <div style={{
          marginTop: 16, padding: 12, background: '#f9fafb',
          border: '1px solid #e5e7eb', borderRadius: 8,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
            Platform Overview
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
            <Stat label="Active Robots" value={Object.keys(state.robots).length} />
            <Stat label="Locked Zones" value={state.locked_zones.length} />
            <Stat label="Pending Tasks" value={state.pending_tasks} />
            <Stat label="Active Assignments" value={state.active_assignments} />
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ color: '#6b7280' }}>{label}</span>
      <span style={{ fontWeight: 700, color: '#374151' }}>{value}</span>
    </div>
  )
}
