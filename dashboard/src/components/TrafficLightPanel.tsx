import { usePlatformState } from '../hooks/usePlatformState'

/** Traffic light status per intersection lane */
interface IntersectionState {
  node: string
  lanes: { lane_id: string; state: 'GREEN' | 'YELLOW' | 'RED'; robot_id?: string }[]
}

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

export function TrafficLightPanel() {
  const { state, health, connected, error, refresh } = usePlatformState()

  // Derive intersection states from coordinator platform state
  // The v5 coordinator exposes intersection traffic lights in the metrics
  // and locked_zones gives us intersection status
  const intersections: IntersectionState[] = (() => {
    if (!state) return []

    // Map from the coordinator state — each locked zone corresponds to an intersection
    // with a RED light; unlocked zones may be GREEN
    const results: IntersectionState[] = []
    const locked = new Set(state.locked_zones)

    // Extract intersection data from metrics if available
    const intersectionNodes = Object.keys(state.metrics)
      .filter(k => k.startsWith('intersection_'))
      .map(k => k.replace('intersection_', ''))

    if (intersectionNodes.length > 0) {
      for (const node of intersectionNodes) {
        const laneKeys = Object.keys(state.metrics)
          .filter(k => k.startsWith(`lane_${node}_`))
        const lanes = laneKeys.map(k => {
          const laneId = k.replace(`lane_${node}_`, '')
          const isLocked = locked.has(laneId) || locked.has(node)
          return {
            lane_id: laneId,
            state: (isLocked ? 'RED' : 'GREEN') as 'GREEN' | 'RED',
          }
        })
        results.push({ node, lanes })
      }
    }

    // Fallback: derive from locked zones alone
    if (results.length === 0 && locked.size > 0) {
      const laneStates: IntersectionState['lanes'] = []
      locked.forEach(zone => {
        laneStates.push({ lane_id: zone, state: 'RED' })
      })
      if (laneStates.length > 0) {
        results.push({ node: 'X1', lanes: laneStates })
      }
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
          <div key={intersection.node} style={{
            background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14,
          }}>
            <div style={{
              fontSize: 14, fontWeight: 600, marginBottom: 10,
              color: '#374151',
            }}>
              Intersection {intersection.node}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {intersection.lanes.length > 0 ? intersection.lanes.map(lane => (
                <div key={lane.lane_id} style={{
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
                    {lane.lane_id}
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
