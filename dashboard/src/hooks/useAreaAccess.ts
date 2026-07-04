/**
 * RBAC: Area-based access control hook.
 *
 * Non-admin users can only view objects (robots, tasks, zones) belonging
 * to the warehouse areas assigned to them (currentUser.functionAreas).
 * Admins bypass all filters — they see everything.
 *
 * Falls back gracefully when used outside AuthProvider (tests, etc.)
 * by treating the caller as admin (no restrictions).
 */

import { useContext } from 'react'
import { AuthContextRaw } from '../context/AuthContext'
import { loadAreas } from './useAreas'

// ── Robot-to-area assignment storage ──

const ROBOT_AREA_KEY = 'robot_dashboard_robot_areas'

export interface RobotAreaAssignment {
  robotId: string
  areaId: string
}

export function loadRobotAreas(): Map<string, string> {
  try {
    const raw = localStorage.getItem(ROBOT_AREA_KEY)
    if (!raw) return new Map()
    const arr: RobotAreaAssignment[] = JSON.parse(raw)
    return new Map(arr.map(a => [a.robotId, a.areaId]))
  } catch {
    return new Map()
  }
}

export function saveRobotAreas(map: Map<string, string>): void {
  const arr: RobotAreaAssignment[] = Array.from(map.entries()).map(([robotId, areaId]) => ({ robotId, areaId }))
  localStorage.setItem(ROBOT_AREA_KEY, JSON.stringify(arr))
}

export function assignRobotToArea(robotId: string, areaId: string): void {
  const map = loadRobotAreas()
  map.set(robotId, areaId)
  saveRobotAreas(map)
}

export function unassignRobot(robotId: string): void {
  const map = loadRobotAreas()
  map.delete(robotId)
  saveRobotAreas(map)
}

// ── Hook ──

export interface AreaAccess {
  /** Whether the current user is admin (sees everything) */
  isAdmin: boolean
  /** Area IDs the user has access to */
  userAreaIds: string[]
  /** Check if user can view a specific area/zone */
  canViewArea: (areaId: string) => boolean
  /** Check if user can view a robot (by ID) */
  canViewRobot: (robotId: string) => boolean
  /** Check if user can view a task/order (by robot assignment or zone) */
  canViewTask: (task: { orderId?: string; manufacturer?: string; serialNumber?: string; robotId?: string }) => boolean
  /** Get all area IDs that exist */
  allAreaIds: string[]
  /** Get the area ID for a robot */
  robotAreaId: (robotId: string) => string | undefined
}

export function useAreaAccess(): AreaAccess {
  // Use raw context for graceful null handling (won't throw outside AuthProvider)
  const auth = useContext(AuthContextRaw)

  // Outside AuthProvider (tests, etc.): treat as admin (no restrictions)
  const isAdmin = auth?.isAdmin ?? true
  const currentUser = auth?.currentUser ?? null

  const allAreas = loadAreas()
  const allAreaIds = allAreas.map(a => a.id)

  // Admin sees all areas
  const userAreaIds: string[] = isAdmin
    ? allAreaIds
    : (currentUser?.functionAreas ?? []).filter(id => allAreaIds.includes(id))

  const robotAreas = loadRobotAreas()

  function canViewArea(areaId: string): boolean {
    if (isAdmin) return true
    return userAreaIds.includes(areaId)
  }

  function canViewRobot(robotId: string): boolean {
    if (isAdmin) return true
    // Check if robot is assigned to one of the user's areas
    const areaId = robotAreas.get(robotId)
    if (areaId) return userAreaIds.includes(areaId)
    // Also try matching by robot ID prefix (e.g. "kuka/001" might match)
    for (const [rid, aid] of robotAreas) {
      if (rid === robotId || robotId.includes(rid) || rid.includes(robotId)) {
        return userAreaIds.includes(aid)
      }
    }
    // Unassigned robot → non-admin users never see it (prevents data leak)
    return false
  }

  function canViewTask(task: { orderId?: string; manufacturer?: string; serialNumber?: string; robotId?: string }): boolean {
    if (isAdmin) return true
    // Build robot ID from task data
    const rid = task.robotId
      || (task.manufacturer && task.serialNumber ? `${task.manufacturer}/${task.serialNumber}` : undefined)
    if (rid) return canViewRobot(rid)
    // Tasks without robot association: non-admin never sees them
    return false
  }

  function robotAreaId(robotId: string): string | undefined {
    const areaId = robotAreas.get(robotId)
    if (areaId) return areaId
    for (const [rid, aid] of robotAreas) {
      if (rid === robotId || robotId.includes(rid) || rid.includes(robotId)) {
        return aid
      }
    }
    return undefined
  }

  return { isAdmin, userAreaIds, canViewArea, canViewRobot, canViewTask, allAreaIds, robotAreaId }
}
