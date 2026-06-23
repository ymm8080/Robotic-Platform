import { useEffect, useState } from 'react'

interface Order {
  orderId: string
  manufacturer: string
  serialNumber: string
  status: string
  createdAt: string
  nodes: unknown[]
  edges: unknown[]
}

export function TaskList() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    fetch('/api/v1/orders')
      .then(r => r.json())
      .then(data => setOrders(data.orders ?? []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const statusColor: Record<string, string> = {
    ASSIGNED: '#3b82f6',
    IN_PROGRESS: '#22c55e',
    COMPLETED: '#6b7280',
    FAILED: '#ef4444',
    CANCELLED: '#f97316',
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>任务列表</h3>
        <button onClick={load} style={{
          padding: '4px 12px', fontSize: 12, border: '1px solid #d1d5db',
          borderRadius: 4, background: '#fff', cursor: 'pointer',
        }}>
          刷新
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 14 }}>加载中…</div>
      ) : orders.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 14 }}>暂无订单</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {orders.map(o => (
            <div key={o.orderId} style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
              padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 12, fontSize: 13,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{o.orderId}</div>
                <div style={{ color: '#6b7280', fontSize: 12 }}>{o.manufacturer}/{o.serialNumber}</div>
              </div>
              <div style={{
                background: `${statusColor[o.status] || '#6b7280'}18`,
                color: statusColor[o.status] || '#6b7280',
                padding: '2px 8px', borderRadius: 12, fontWeight: 600, fontSize: 12,
              }}>
                {o.status}
              </div>
              <div style={{ color: '#9ca3af', fontSize: 11 }}>
                {o.createdAt ? new Date(o.createdAt).toLocaleTimeString('zh-CN') : '-'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
