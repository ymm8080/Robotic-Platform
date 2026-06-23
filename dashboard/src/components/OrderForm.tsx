import { useState, type FormEvent } from 'react'

const ACTION_TYPES = ['pick', 'place', 'navigate', 'lift', 'drop', 'charge']

export function OrderForm({ onCreated }: { onCreated: () => void }) {
  const [manufacturer, setManufacturer] = useState('Quicktron')
  const [serialNumber, setSerialNumber] = useState('')
  const [orderId, setOrderId] = useState('')
  const [actionType, setActionType] = useState('navigate')
  const [targetX, setTargetX] = useState('')
  const [targetY, setTargetY] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!manufacturer || !serialNumber || !orderId) return

    setSending(true)
    setResult(null)

    const nodeId = `NODE-${Date.now().toString(36).toUpperCase()}`
    const nodes = [{
      nodeId,
      sequenceId: 0,
      nodePosition: {
        x: parseFloat(targetX) || 0,
        y: parseFloat(targetY) || 0,
        theta: 0,
        allowedDeviationXY: 0.5,
        allowedDeviationTheta: 5.0,
      },
      actions: actionType !== 'navigate' ? [{
        actionType,
        actionId: `ACT-${Date.now()}`,
        blockingType: 'SOFT' as const,
        actionParameters: [],
      }] : [],
    }]

    try {
      const res = await fetch('/api/v1/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manufacturer,
          serialNumber,
          orderId,
          nodes,
          edges: [],
        }),
      })
      const data = await res.json()
      if (res.ok) {
        setResult({ ok: true, msg: `订单 ${orderId} 已发送` })
        setOrderId('')
        onCreated()
      } else {
        setResult({ ok: false, msg: data.error || '发送失败' })
      }
    } catch (err) {
      setResult({ ok: false, msg: `网络错误: ${(err as Error).message}` })
    } finally {
      setSending(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 600 }}>手动下单</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <Input label="品牌" value={manufacturer} onChange={v => setManufacturer(v)} />
        <Input label="序列号" value={serialNumber} onChange={v => setSerialNumber(v)} placeholder="e.g. QC-001" />
        <Input label="订单ID" value={orderId} onChange={v => setOrderId(v)} placeholder="自动生成留空" />
        <div>
          <label style={labelStyle}>动作</label>
          <select value={actionType} onChange={e => setActionType(e.target.value)} style={inputStyle}>
            {ACTION_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <Input label="目标 X" value={targetX} onChange={v => setTargetX(v)} placeholder="0.0" />
        <Input label="目标 Y" value={targetY} onChange={v => setTargetY(v)} placeholder="0.0" />
      </div>
      <button type="submit" disabled={sending || !serialNumber || !manufacturer}
        style={{
          marginTop: 12,
          padding: '8px 20px',
          background: sending ? '#9ca3af' : '#3b82f6',
          color: '#fff',
          border: 'none',
          borderRadius: 6,
          fontWeight: 600,
          cursor: sending ? 'not-allowed' : 'pointer',
          fontSize: 14,
        }}>
        {sending ? '发送中…' : '发送订单'}
      </button>
      {result && (
        <div style={{ marginTop: 8, fontSize: 13, color: result.ok ? '#22c55e' : '#ef4444' }}>
          {result.msg}
        </div>
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
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        style={inputStyle} />
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 12, color: '#6b7280', marginBottom: 2,
}
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '6px 8px', fontSize: 13, border: '1px solid #d1d5db',
  borderRadius: 4, boxSizing: 'border-box',
}
