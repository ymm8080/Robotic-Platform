import { useState, useMemo } from 'react'
import { usePlatformState } from '../hooks/usePlatformState'
import type { WORMPlaybackEvent } from '../types/vda5050'

/** Color mapping for event categories */
function categoryColor(category: string): string {
  switch (category) {
    case 'state_change': return '#3b82f6'
    case 'mode_change': return '#8b5cf6'
    case 'error': return '#ef4444'
    case 'warning': return '#f59e0b'
    case 'task': return '#22c55e'
    case 'traffic': return '#eab308'
    case 'zone': return '#dc2626'
    case 'intersection': return '#f97316'
    default: return '#6b7280'
  }
}

function categoryBg(category: string): string {
  switch (category) {
    case 'state_change': return '#eff6ff'
    case 'mode_change': return '#f5f3ff'
    case 'error': return '#fef2f2'
    case 'warning': return '#fffbeb'
    case 'task': return '#f0fdf4'
    case 'traffic': return '#fefce8'
    case 'zone': return '#fef2f2'
    case 'intersection': return '#fff7ed'
    default: return '#f9fafb'
  }
}

function categoryLabel(category: string): string {
  switch (category) {
    case 'state_change': return 'State'
    case 'mode_change': return 'Mode'
    case 'error': return 'Error'
    case 'warning': return 'Warning'
    case 'task': return 'Task'
    case 'traffic': return 'Traffic'
    case 'zone': return 'Zone'
    case 'intersection': return 'Intersection'
    default: return category
  }
}

/** Format ISO timestamp to HH:mm:ss */
function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

/** Truncate payload to a short summary string */
function payloadSummary(payload: Record<string, unknown>): string {
  if (!payload || Object.keys(payload).length === 0) return ''
  const entries = Object.entries(payload)
  const firstVal = entries[0]?.[1]
  if (typeof firstVal === 'string') return firstVal.slice(0, 120)
  if (typeof firstVal === 'number' || typeof firstVal === 'boolean') return String(firstVal)
  return JSON.stringify(payload).slice(0, 120) + '…'
}

export function PlaybackPanel() {
  const { playbackEvents, playbackLoading } = usePlatformState()
  const [filterRobot, setFilterRobot] = useState<string>('')
  const [autoScroll, setAutoScroll] = useState(true)

  // Derive unique robot IDs for the filter dropdown
  const robotIds = useMemo(() => {
    const ids = new Set<string>()
    playbackEvents.forEach(e => {
      if (e.robot_id) ids.add(e.robot_id)
    })
    return Array.from(ids).sort()
  }, [playbackEvents])

  // Filter events by selected robot
  const filteredEvents = useMemo(() => {
    if (!filterRobot) return playbackEvents
    return playbackEvents.filter(e => e.robot_id === filterRobot)
  }, [playbackEvents, filterRobot])

  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 14,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 12,
      }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
          WORM Playback
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {playbackLoading && (
            <span style={{ fontSize: 11, color: '#9ca3af' }}>Loading…</span>
          )}
          <span style={{
            fontSize: 11, color: '#6b7280',
            background: '#f3f4f6', padding: '2px 8px', borderRadius: 4,
          }}>
            {filteredEvents.length} events
          </span>
          <label style={{ fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={e => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
        </div>
      </div>

      {/* Robot filter */}
      <div style={{ marginBottom: 12 }}>
        <select
          value={filterRobot}
          onChange={e => setFilterRobot(e.target.value)}
          style={{
            width: '100%', padding: '6px 10px', fontSize: 13,
            border: '1px solid #d1d5db', borderRadius: 4,
            background: '#fff',
          }}
        >
          <option value="">All robots</option>
          {robotIds.map(id => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
      </div>

      {/* Empty state */}
      {filteredEvents.length === 0 && (
        <div style={{
          textAlign: 'center', padding: 32, color: '#9ca3af', fontSize: 14,
        }}>
          {playbackLoading
            ? 'Loading WORM events…'
            : 'No WORM events in the last 5 minutes'}
        </div>
      )}

      {/* Scrollable timeline */}
      <div style={{
          maxHeight: 400, overflowY: 'auto',
          border: '1px solid #e5e7eb', borderRadius: 6,
          background: '#f9fafb',
        }}
      >
        {filteredEvents.map((event, i) => (
          <PlaybackEventRow key={event.id ?? i} event={event} isLast={i === filteredEvents.length - 1} />
        ))}
      </div>

      {/* Footer stats */}
      <div style={{
        marginTop: 12, display: 'flex', gap: 16, flexWrap: 'wrap',
        fontSize: 11, color: '#9ca3af',
      }}>
        <span>Data source: /v1/v5/playback?duration=300</span>
        <span>Auto-refresh every 10s</span>
      </div>
    </div>
  )
}

function PlaybackEventRow({ event, isLast }: { event: WORMPlaybackEvent; isLast: boolean }) {
  const color = categoryColor(event.category)
  const bg = categoryBg(event.category)
  const summary = payloadSummary(event.payload)

  return (
    <div style={{
      padding: '8px 12px',
      borderBottom: isLast ? 'none' : '1px solid #f3f4f6',
      background: bg,
      display: 'flex',
      gap: 10,
      alignItems: 'flex-start',
    }}>
      {/* Category badge */}
      <div style={{
        flexShrink: 0,
        background: `${color}20`,
        color,
        fontWeight: 600,
        fontSize: 10,
        padding: '2px 8px',
        borderRadius: 10,
        whiteSpace: 'nowrap',
        marginTop: 1,
      }}>
        {categoryLabel(event.category)}
      </div>

      {/* Timestamp */}
      <div style={{
        flexShrink: 0,
        fontSize: 11,
        color: '#6b7280',
        fontFamily: 'monospace',
        minWidth: 64,
        marginTop: 1,
      }}>
        {formatTime(event.timestamp)}
      </div>

      {/* Robot ID */}
      <div style={{
        flexShrink: 0,
        fontSize: 12,
        fontWeight: 600,
        color: '#374151',
        minWidth: 80,
      }}>
        {event.robot_id || '—'}
      </div>

      {/* Payload summary */}
      <div style={{
        fontSize: 12,
        color: '#6b7280',
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {summary || <span style={{ color: '#d1d5db' }}>No payload</span>}
      </div>
    </div>
  )
}
