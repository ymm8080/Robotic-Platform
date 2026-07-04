import { useEffect, useState, useCallback, useMemo } from 'react'
import { CONFIG } from '../config'
import { useAreaAccess } from '../hooks/useAreaAccess'

interface Order {
  orderNo: string
  type: string
  priority: number
  robotBrand: string | null
  robotSerial: string | null
  status: string
  errorMessage: string | null
  createdAt: string
  updatedAt: string | null
  completedAt: string | null
}

const STATUS_COLOR: Record<string, string> = {
  CREATED: '#3b82f6',
  ASSIGNED: '#8b5cf6',
  IN_PROGRESS: '#22c55e',
  COMPLETED: '#6b7280',
  FAILED: '#ef4444',
  CANCELLED: '#f97316',
  SUSPENDED: '#eab308',
}

const TYPE_COLOR: Record<string, string> = {
  MOVE: '#3b82f6',
  PICK: '#22c55e',
  PUT: '#f59e0b',
  CHARGE: '#a855f7',
}

const PRIORITY_LABEL: Record<number, string> = {
  0: '🔴 Critical',
  1: '🟠 High',
  2: '🟡 Normal',
  3: '🟢 Low',
}

export function TaskList() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { isAdmin, canViewTask } = useAreaAccess()

  // Filter orders by area access
  const filteredOrders = useMemo(() => {
    if (isAdmin) return orders
    return orders.filter(o => canViewTask({
      robotId: o.robotBrand && o.robotSerial ? `${o.robotBrand}/${o.robotSerial}` : undefined,
    }))
  }, [orders, isAdmin, canViewTask])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fetch(`${CONFIG.apiBase}/v1/orders?limit=50`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => setOrders(data.orders ?? []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30s
  useEffect(() => {
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
          📋 Task List ({filteredOrders.length}{!isAdmin && filteredOrders.length !== orders.length ? ` / ${orders.length} total` : ''})
        </h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={load} disabled={loading}
            style={{
              padding: '4px 12px', fontSize: 12, border: '1px solid #d1d5db',
              borderRadius: 4, background: '#fff', cursor: 'pointer',
            }}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
          padding: '8px 12px', borderRadius: 6, marginBottom: 12, fontSize: 13,
        }}>
          Load error: {error}
        </div>
      )}

      {loading && filteredOrders.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 14 }}>
          Loading…
        </div>
      ) : filteredOrders.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 14 }}>
          No orders yet
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {filteredOrders.slice(0, 100).map(o => (
            <div key={o.orderNo} style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
              padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 12, fontSize: 13,
            }}>
              {/* Order ID + type + robot */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{o.orderNo}</span>
                  <span style={{
                    padding: '1px 5px', borderRadius: 3, fontSize: 10, fontWeight: 600,
                    background: `${TYPE_COLOR[o.type] || '#6b7280'}18`,
                    color: TYPE_COLOR[o.type] || '#6b7280',
                  }}>
                    {o.type}
                  </span>
                  <span style={{ fontSize: 10, color: '#9ca3af' }}>
                    {PRIORITY_LABEL[o.priority] || `P${o.priority}`}
                  </span>
                </div>
                <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>
                  {o.robotBrand && o.robotSerial
                    ? `🤖 ${o.robotBrand}/${o.robotSerial}`
                    : 'Unassigned'}
                  {o.errorMessage && (
                    <span style={{ color: '#ef4444', marginLeft: 8 }}>
                      ⚠️ {o.errorMessage}
                    </span>
                  )}
                </div>
              </div>

              {/* Status badge */}
              <div style={{
                background: `${STATUS_COLOR[o.status] || '#6b7280'}18`,
                color: STATUS_COLOR[o.status] || '#6b7280',
                padding: '3px 10px', borderRadius: 12, fontWeight: 600, fontSize: 11,
                whiteSpace: 'nowrap',
              }}>
                {o.status.replace('_', ' ')}
              </div>

              {/* Timestamps */}
              <div style={{ color: '#9ca3af', fontSize: 10, textAlign: 'right', whiteSpace: 'nowrap' }}>
                <div>{o.createdAt ? new Date(o.createdAt).toLocaleString() : '-'}</div>
                {o.completedAt && (
                  <div style={{ color: '#22c55e' }}>
                    ✓ {new Date(o.completedAt).toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
