/* VDA5050 v2.0 TypeScript interfaces */

export interface VDA5050Header {
  headerId: number
  timestamp: string
  version: string
  manufacturer: string
  serialNumber: string
}

/* ── Connection ── */

export type ConnectionState = 'ONLINE' | 'OFFLINE' | 'CONNECTIONBROKEN'

export interface ConnectionMessage extends VDA5050Header {
  connectionState: ConnectionState
}

/* ── State ── */

export type OperatingMode = 'AUTOMATIC' | 'SEMIAUTOMATIC' | 'MANUAL' | 'SERVICE' | 'TEACHIN'

export type ActionStatus = 'WAITING' | 'INITIALIZING' | 'RUNNING' | 'PAUSED' | 'FINISHED' | 'FAILED'

export interface ActionState {
  actionId: string
  actionType: string
  actionStatus: ActionStatus
  actionDescription?: string
  resultDescription?: string
}

export interface NodeState {
  nodeId: string
  sequenceId: number
  nodeDescription?: string
  released: boolean
}

export interface EdgeState {
  edgeId: string
  sequenceId: number
  edgeDescription?: string
  released: boolean
}

export interface BatteryState {
  batteryCharge: number
  batteryVoltage?: number
  batteryHealth?: number
  charging?: boolean
}

export interface AGVPosition {
  x: number
  y: number
  theta: number
  lastNodeId?: string
  positionInitialized: boolean
}

export interface SafetyState {
  eStop: boolean
  fieldViolation?: boolean
  safetyCarDistance?: number
}

export interface Error {
  errorType: string
  errorLevel: 'WARNING' | 'FATAL'
  errorDescription?: string
  errorReferences?: string[]
}

/* Derived/display state mapped from raw VDA5050 state */
export type RobotDisplayState =
  | 'IDLE'
  | 'MOVING'
  | 'EXECUTING'
  | 'PAUSED'
  | 'CHARGING'
  | 'ERROR'
  | 'UNAVAILABLE'
  | 'INIT'
  | 'OFFLINE'
  | 'UNKNOWN'

export interface StateMessage extends VDA5050Header {
  orderId?: string
  orderUpdateId?: number
  lastNodeId?: string
  lastNodeSequenceId?: number
  nodeStates: NodeState[]
  edgeStates: EdgeState[]
  actionStates: ActionState[]
  batteryState: BatteryState
  operatingMode: OperatingMode
  driving: boolean
  paused: boolean
  newBaseRequest: boolean
  distanceSinceLastNode?: number
  errors: Error[]
  safetyState: SafetyState
  agvPosition?: AGVPosition
}

/* ── Order ── */

export interface ActionParameter {
  key: string
  value: string
}

export interface VDA5050Action {
  actionType: string
  actionId: string
  blockingType: 'NONE' | 'SOFT' | 'HARD'
  actionParameters?: ActionParameter[]
}

export interface Node {
  nodeId: string
  sequenceId: number
  nodePosition?: {
    x: number
    y: number
    theta: number
    allowedDeviationXY?: number
    allowedDeviationTheta?: number
  }
  actions?: VDA5050Action[]
}

export interface Edge {
  edgeId: string
  sequenceId: number
  startNodeId: string
  endNodeId: string
  maxSpeed?: number
  actions?: VDA5050Action[]
}

export interface OrderMessage extends VDA5050Header {
  orderId: string
  orderUpdateId: number
  nodes: Node[]
  edges: Edge[]
}

/* ── Instant Actions ── */

export interface InstantActionsMessage extends VDA5050Header {
  actions: VDA5050Action[]
}

/* ── Robot summary for dashboard display ── */

export interface RobotSummary {
  manufacturer: string
  serialNumber: string
  id: string               // "manufacturer/serialNumber"
  displayState: RobotDisplayState
  battery: number
  position: { x: number; y: number; theta: number } | null
  orderId: string | null
  operatingMode: OperatingMode
  errors: Error[]
  safetyState: SafetyState
  lastSeen: string
  connected: boolean
  driving: boolean
  paused: boolean
}

export function deriveDisplayState(s: StateMessage, connected: boolean): RobotDisplayState {
  if (!connected) return 'OFFLINE'

  const hasFatal = s.errors?.some(e => e.errorLevel === 'FATAL')
  if (hasFatal) return 'ERROR'

  if (s.operatingMode !== 'AUTOMATIC' && s.operatingMode !== 'SEMIAUTOMATIC') return 'UNAVAILABLE'

  // Reference: VDA5050 §6.10 — CHARGING is detected via batteryState.charging flag,
  // not by battery level alone. Battery at 100% means full, not actively charging.
  if (s.batteryState?.charging) return 'CHARGING'

  if (s.paused) return 'PAUSED'
  if (s.driving) return 'MOVING'
  if (s.actionStates?.some(a => a.actionStatus === 'RUNNING' || a.actionStatus === 'INITIALIZING')) return 'EXECUTING'

  return 'IDLE'
}

/* ── v5.0 Traffic Coordinator types ── */

export interface V5RobotState {
  mode: string          // IDLE | TASKING | CHARGING | ERROR
  pose: [number, number] // [x, y]
  boot_id?: string
  degraded?: boolean
  sensor_health?: number  // 0.0–1.0
  battery_percent?: number
  velocity?: number
  lane_id?: string        // current lane the robot is on
  errors?: string[]
}

/** Traffic intersection state from the v5 coordinator */
export interface V5IntersectionState {
  intersection_id: string
  state: 'RED' | 'YELLOW' | 'GREEN'
  robots_waiting: number
  timer: number
  lanes: Record<string, {
    state: 'RED' | 'YELLOW' | 'GREEN'
    robot_id?: string
  }>
}

/** A node in the lane graph */
export interface V5LaneNode {
  id: string
  x: number
  y: number
}

/** An edge (lane segment) in the lane graph */
export interface V5LaneEdge {
  id: string
  from: string
  to: string
}

/** Lane graph for the warehouse map */
export interface V5LaneGraph {
  nodes: V5LaneNode[]
  edges: V5LaneEdge[]
}

export interface V5PlatformState {
  robots: Record<string, V5RobotState>
  locked_zones: string[]
  pending_tasks: number
  active_assignments: number
  pending_commands: number
  metrics: Record<string, number>
  /** Optional intersection traffic-light states */
  intersections?: Record<string, V5IntersectionState>
  /** Optional lane graph for map rendering */
  lane_graph?: V5LaneGraph
}

/** Single WORM (Write-Once-Read-Many) playback event */
export interface WORMPlaybackEvent {
  id: string
  timestamp: string
  category: string
  robot_id: string
  payload: Record<string, unknown>
}

/** Response from /v1/v5/playback */
export interface WORMPlaybackResponse {
  events: WORMPlaybackEvent[]
  count: number
  duration: number
}

export interface V5CoordinatorHealth {
  status: string
  mode: string
  version: string
  supported_versions: string[]
  checks: string[]
}

export type SensorHealthLevel = 'HEALTHY' | 'DEGRADED' | 'CRITICAL'

export function sensorHealthColor(level: SensorHealthLevel): string {
  switch (level) {
    case 'HEALTHY': return '#22c55e'
    case 'DEGRADED': return '#eab308'
    case 'CRITICAL': return '#ef4444'
    default: return '#9ca3af'
  }
}

export function sensorHealthLabel(level: SensorHealthLevel): string {
  switch (level) {
    case 'HEALTHY': return 'Healthy'
    case 'DEGRADED': return 'Degraded'
    case 'CRITICAL': return 'Critical'
    default: return 'Unknown'
  }
}

export function deriveSensorHealth(sensor_health: number | undefined): SensorHealthLevel {
  if (sensor_health === undefined || sensor_health >= 0.8) return 'HEALTHY'
  if (sensor_health >= 0.4) return 'DEGRADED'
  return 'CRITICAL'
}

export function toRobotSummary(
  manufacturer: string,
  serialNumber: string,
  state: StateMessage | null,
  connection: ConnectionMessage | null,
): RobotSummary {
  const connected = connection?.connectionState === 'ONLINE'
  return {
    manufacturer,
    serialNumber,
    id: `${manufacturer}/${serialNumber}`,
    displayState: state ? deriveDisplayState(state, connected) : (connected ? 'IDLE' : 'OFFLINE'),
    battery: state?.batteryState?.batteryCharge ?? 0,
    position: state?.agvPosition ?? null,
    orderId: state?.orderId ?? null,
    operatingMode: state?.operatingMode ?? 'MANUAL',
    errors: state?.errors ?? [],
    safetyState: state?.safetyState ?? { eStop: false },
    lastSeen: state?.timestamp ?? connection?.timestamp ?? '',
    connected,
    driving: state?.driving ?? false,
    paused: state?.paused ?? false,
  }
}
