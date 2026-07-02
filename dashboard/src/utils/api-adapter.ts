/**
 * Adapter: converts REST API robot data into display formats
 * used by MQTT-native components (BatteryPanel, WarehouseMap, etc.)
 */

import type { RobotDisplayState } from '../types/vda5050'

export interface ChargingStation {
  id: string
  x: number
  y: number
  assignedRobot: string | null
  occupied: boolean
}

export interface ApiRobot {
  id: string
  brand: string
  state: string
  battery: string
  lastSeen: string
  position?: { x: number; y: number }
  orderId?: string | null
  returningToCharge?: boolean
  chargingStation?: { id: string; x: number; y: number }
}

export interface DisplayRobot {
  id: string
  brand: string
  battery: number
  state: RobotDisplayState
  lastSeen: string
  connected: boolean
  position?: { x: number; y: number }
  orderId?: string | null
  returningToCharge?: boolean
  chargingStation?: { id: string; x: number; y: number }
}

const STATE_MAP: Record<string, RobotDisplayState> = {
  ONLINE: 'IDLE',
  IDLE: 'IDLE',
  MOVING: 'MOVING',
  EXECUTING: 'EXECUTING',
  PAUSED: 'PAUSED',
  CHARGING: 'CHARGING',
  ERROR: 'ERROR',
  UNAVAILABLE: 'UNAVAILABLE',
  INIT: 'INIT',
  OFFLINE: 'OFFLINE',
}

export function apiRobotToDisplay(r: ApiRobot): DisplayRobot {
  return {
    id: r.id,
    brand: r.brand,
    battery: parseInt(r.battery) || 0,
    state: STATE_MAP[r.state.toUpperCase()] || 'UNKNOWN',
    lastSeen: r.lastSeen,
    connected: r.state.toUpperCase() !== 'OFFLINE' && r.state.toUpperCase() !== 'UNAVAILABLE',
    position: r.position,
    orderId: r.orderId,
    returningToCharge: r.returningToCharge,
    chargingStation: r.chargingStation,
  }
}

export function apiRobotsToDisplay(robots: ApiRobot[]): DisplayRobot[] {
  return robots.map(apiRobotToDisplay)
}
