import { useEffect, useState, useCallback } from 'react'
import { CONFIG } from '../config'

interface Order {
  orderId: string
  manufacturer: string
  serialNumber: string
  status: string
  createdAt: string
  nodes: unknown[]
  edges: unknown[]
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

export function TaskList() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
          Task List ({orders.length})
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

      {loading && orders.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 14 }}>
          Loading…
        </div>
      ) : orders.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 14 }}>
          No orders yet
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {orders.slice(0, 100).map(o => (
            <div key={o.orderId} style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
              padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 12, fontSize: 13,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{o.orderId}</div>
                <div style={{ color: '#6b7280', fontSize: 12 }}>{o.manufacturer}/{o.serialNumber}</div>
              </div>
              <div style={{
                background: `${STATUS_COLOR[o.status] || '#6b7280'}18`,
                color: STATUS_COLOR[o.status] || '#6b7280',
                padding: '2px 8px', borderRadius: 12, fontWeight: 600, fontSize: 12,
              }}>
                {o.status}
              </div>
              <div style={{ color: '#9ca3af', fontSize: 11 }}>
                {o.createdAt ? new Date(o.createdAt).toLocaleString() : '-'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
