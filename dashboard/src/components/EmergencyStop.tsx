import { useState } from 'react'
import { CONFIG } from '../config'

export function EmergencyStop() {
  const [confirming, setConfirming] = useState(false)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [targetBrand, setTargetBrand] = useState('*')  // * = all brands

  async function handleEStop() {
    setSending(true)
    setResult(null)

    try {
      // Send emergency stop via instantActions topic for all robots
      const actions = [{
        actionType: 'cancelOrder',
        actionId: `ESTOP-${Date.now()}`,
        blockingType: 'NONE',
        actionParameters: [],
      }]

      // For each brand or all brands, publish E-Stop
      const brands = targetBrand === '*' ? ['KUKA', 'MIR', 'OTTO'] : [targetBrand]
      const results = await Promise.allSettled(
        brands.map(brand =>
          fetch(`${CONFIG.apiBase}/v1/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              manufacturer: brand,
              serialNumber: 'ESTOP-ALL',
              orderId: `ESTOP-${Date.now()}`,
              orderType: 'MOVE',
              priority: 0,
              nodes: [],
              edges: [],
            }),
          }).then(r => r.json())
        )
      )

      const success = results.filter(r => r.status === 'fulfilled').length
      setResult({
        ok: success > 0,
        msg: `急停指令已发送 (${success}/${brands.length} 个品牌)`,
      })
    } catch (err) {
      setResult({ ok: false, msg: `发送失败: ${(err as Error).message}` })
    } finally {
      setSending(false)
      setConfirming(false)
    }
  }

  if (!confirming) {
    return (
      <button
        onClick={() => setConfirming(true)}
        style={{
          width: '100%',
          padding: '20px',
          fontSize: 28,
          fontWeight: 800,
          background: '#dc2626',
          color: '#fff',
          border: 'none',
          borderRadius: 12,
          cursor: 'pointer',
          boxShadow: '0 4px 12px rgba(220,38,38,0.4)',
          letterSpacing: 2,
        }}
      >
        🚨 紧急停止
      </button>
    )
  }

  return (
    <div style={{
      background: '#fef2f2',
      border: '3px solid #dc2626',
      borderRadius: 12,
      padding: 20,
    }}>
      <h3 style={{ margin: '0 0 12px', color: '#991b1b', fontSize: 18 }}>
        ⚠️ 确认紧急停止
      </h3>
      <p style={{ fontSize: 14, color: '#7f1d1d', marginBottom: 12 }}>
        此操作将取消所有机器人的当前任务，已执行操作不受影响。
      </p>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
          目标品牌（* = 全部）
        </label>
        <select
          value={targetBrand}
          onChange={e => setTargetBrand(e.target.value)}
          style={{
            width: '100%', padding: '8px', fontSize: 14,
            border: '1px solid #d1d5db', borderRadius: 4,
          }}
        >
          <option value="*">全部品牌</option>
          <option value="KUKA">KUKA</option>
          <option value="MIR">MiR</option>
          <option value="OTTO">OTTO</option>
        </select>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={handleEStop}
          disabled={sending}
          style={{
            flex: 1, padding: '12px', fontSize: 16, fontWeight: 700,
            background: sending ? '#9ca3af' : '#dc2626', color: '#fff',
            border: 'none', borderRadius: 8, cursor: sending ? 'not-allowed' : 'pointer',
          }}
        >
          {sending ? '发送中…' : '确认停止'}
        </button>
        <button
          onClick={() => { setConfirming(false); setResult(null) }}
          style={{
            padding: '12px 20px', fontSize: 14,
            background: '#fff', color: '#374151',
            border: '1px solid #d1d5db', borderRadius: 8, cursor: 'pointer',
          }}
        >
          取消
        </button>
      </div>

      {result && (
        <div style={{
          marginTop: 12, padding: 8, borderRadius: 4, fontSize: 13,
          background: result.ok ? '#f0fdf4' : '#fef2f2',
          color: result.ok ? '#15803d' : '#991b1b',
        }}>
          {result.msg}
        </div>
      )}
    </div>
  )
}
