import type { RobotDisplayState, RobotSummary } from '../types/vda5050'

const stateLabel: Record<RobotDisplayState, string> = {
  IDLE: '空闲',
  MOVING: '行驶中',
  EXECUTING: '执行中',
  PAUSED: '已暂停',
  CHARGING: '充电中',
  ERROR: '错误',
  UNAVAILABLE: '不可用',
  INIT: '启动中',
  OFFLINE: '离线',
  UNKNOWN: '未知',
}

const stateColor: Record<RobotDisplayState, string> = {
  IDLE: '#6b7280',
  MOVING: '#3b82f6',
  EXECUTING: '#22c55e',
  PAUSED: '#eab308',
  CHARGING: '#a855f7',
  ERROR: '#ef4444',
  UNAVAILABLE: '#f97316',
  INIT: '#94a3b8',
  OFFLINE: '#d1d5db',
  UNKNOWN: '#9ca3af',
}

export function displayStateLabel(state: RobotDisplayState): string {
  return stateLabel[state] ?? state
}

export function displayStateColor(state: RobotDisplayState): string {
  return stateColor[state] ?? '#9ca3af'
}

export function batteryColor(pct: number): string {
  if (pct > 50) return '#22c55e'
  if (pct > 20) return '#eab308'
  return '#ef4444'
}

export function relativeTime(iso: string): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 10) return '刚刚'
  if (s < 60) return `${s}秒前`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}分钟前`
  const h = Math.floor(m / 60)
  return `${h}小时前`
}

export function truncateOrderId(id: string | null): string {
  if (!id) return '-'
  return id.length > 24 ? id.slice(0, 24) + '…' : id
}

export function formatBattery(v: number): string {
  return `${Math.round(v)}%`
}

export function sortRobots(robots: RobotSummary[]): RobotSummary[] {
  const priority: Record<RobotDisplayState, number> = {
    ERROR: 0,
    UNAVAILABLE: 1,
    PAUSED: 2,
    OFFLINE: 3,
    MOVING: 4,
    EXECUTING: 5,
    CHARGING: 6,
    IDLE: 7,
    INIT: 8,
    UNKNOWN: 9,
  }
  return [...robots].sort((a, b) => {
    const pa = priority[a.displayState] ?? 99
    const pb = priority[b.displayState] ?? 99
    if (pa !== pb) return pa - pb
    return a.id.localeCompare(b.id)
  })
}
