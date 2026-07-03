import { useState, useEffect, type FormEvent } from 'react'
import { CONFIG } from '../config'

interface RobotOption { id: string; brand: string; state: string }

const ACTION_TYPES = ['navigate', 'pick', 'place', 'lift', 'drop', 'scoop', 'charge']

export function OrderForm({ onCreated }: { onCreated: () => void }) {
  const [robots, setRobots] = useState<RobotOption[]>([])
  const [robotId, setRobotId] = useState('')
  const [orderId, setOrderId] = useState('')
  const [actionType, setActionType] = useState('navigate')
  const [targetX, setTargetX] = useState('')
  const [targetY, setTargetY] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)

  // Fetch available robots (free ones first)
  useEffect(() => {
    fetch(`${CONFIG.apiBase}/v1/robots/status`, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        const list = (data.robots || []).map((r: any) => ({ id: r.id, brand: r.brand, state: r.state }))
        // Sort: free robots first, then busy ones
        list.sort((a: RobotOption, b: RobotOption) => {
          const aBusy = a.state === 'MOVING' || a.state === 'EXECUTING'
          const bBusy = b.state === 'MOVING' || b.state === 'EXECUTING'
          return Number(aBusy) - Number(bBusy)
        })
        setRobots(list)
        if (!robotId && list.length > 0) setRobotId(list[0].id)
      })
      .catch(() => {})
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!robotId) return

    setSending(true)
    setResult(null)

    const robot = robots.find(r => r.id === robotId)
    const oid = orderId || `ORD-${Date.now().toString(36).toUpperCase()}`
    const nodeId = `NODE-${Date.now().toString(36).toUpperCase()}`
    const nodes = [{
      nodeId, sequenceId: 0,
      nodePosition: { x: parseFloat(targetX) || 0, y: parseFloat(targetY) || 0, theta: 0, allowedDeviationXY: 0.5, allowedDeviationTheta: 5.0 },
      actions: actionType !== 'navigate' ? [{ actionType, actionId: `ACT-${Date.now()}`, blockingType: 'SOFT', actionParameters: [] }] : [],
    }]

    try {
      const res = await fetch(`${CONFIG.apiBase}/v1/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manufacturer: robot?.brand || '', serialNumber: robotId, orderId: oid, nodes, edges: [] }),
      })
      const data = await res.json()
      if (res.ok) {
        setResult({ ok: true, msg: `Order ${oid} → ${robotId}` })
        setOrderId('')
        onCreated()
      } else {
        setResult({ ok: false, msg: data.error || 'Send failed' })
      }
    } catch (err) {
      setResult({ ok: false, msg: `Network: ${(err as Error).message}` })
    } finally {
      setSending(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>Create Order</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {/* Robot picker */}
        <div style={{ gridColumn: '1 / -1' }}>
          <label style={labelStyle}>Assign to Robot</label>
          <select value={robotId} onChange={e => setRobotId(e.target.value)} style={inputStyle}>
            {robots.map(r => (
              <option key={r.id} value={r.id}>{r.id} — {r.brand} [{r.state}]</option>
            ))}
          </select>
        </div>
        <Input label="Order ID" value={orderId} onChange={v => setOrderId(v)} placeholder="auto-generated if empty" />
        <div>
          <label style={labelStyle}>Action</label>
          <select value={actionType} onChange={e => setActionType(e.target.value)} style={inputStyle}>
            {ACTION_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <Input label="Target X" value={targetX} onChange={v => setTargetX(v)} placeholder="warehouse coord" />
        <Input label="Target Y" value={targetY} onChange={v => setTargetY(v)} placeholder="warehouse coord" />
      </div>
      <button type="submit" disabled={sending || !robotId}
        style={{
          marginTop: 12, padding: '8px 20px', background: sending ? '#9ca3af' : '#3b82f6',
          color: '#fff', border: 'none', borderRadius: 6, fontWeight: 600, cursor: sending ? 'not-allowed' : 'pointer', fontSize: 14,
        }}>
        {sending ? 'Sending…' : 'Send Order'}
      </button>
      {result && (
        <div style={{ marginTop: 8, fontSize: 13, color: result.ok ? '#22c55e' : '#ef4444' }}>{result.msg}</div>
      )}
    </form>
  )
}

function Input({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={inputStyle} />
    </div>
  )
}

const labelStyle: React.CSSProperties = { display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 2 }
const inputStyle: React.CSSProperties = { width: '100%', padding: '6px 8px', fontSize: 13, border: '1px solid #d1d5db', borderRadius: 4, boxSizing: 'border-box' }
