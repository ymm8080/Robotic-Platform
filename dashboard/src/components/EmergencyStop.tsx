import { useState, useEffect } from 'react'
import { CONFIG } from '../config'

const DEFAULT_BRANDS = ['KUKA', 'MIR', 'OTTO', 'GeekPlus', 'HaiRobotics', 'Quicktron']

export function EmergencyStop() {
  const [confirming, setConfirming] = useState(false)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [targetBrand, setTargetBrand] = useState('*')
  const [brands, setBrands] = useState<string[]>(DEFAULT_BRANDS)

  // Fetch live brand list from API
  useEffect(() => {
    fetch(`${CONFIG.apiBase}/v1/strategies`)
      .then(r => r.json())
      .then(data => {
        if (data.strategies?.length) {
          setBrands(data.strategies.map((s: { brand: string }) => s.brand))
        }
      })
      .catch(() => {})  // Fall back to defaults
  }, [])

  async function handleEStop() {
    setSending(true)
    setResult(null)

    try {
      const selectedBrands = targetBrand === '*' ? brands : [targetBrand]
      const results = await Promise.allSettled(
        selectedBrands.map(brand =>
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
              source: 'emergency-stop',
            }),
          }).then(r => r.json())
        )
      )

      const success = results.filter(r => r.status === 'fulfilled').length
      setResult({
        ok: success > 0,
        msg: `E-Stop sent (${success}/${selectedBrands.length} brands)`,
      })
    } catch (err) {
      setResult({ ok: false, msg: `Send failed: ${(err as Error).message}` })
    } finally {
      setSending(false)
      setConfirming(false)
    }
  }

  if (!confirming) {
    return (
      <button onClick={() => setConfirming(true)}
        style={{
          width: '100%', padding: '20px', fontSize: 28, fontWeight: 800,
          background: '#dc2626', color: '#fff', border: 'none', borderRadius: 12,
          cursor: 'pointer', boxShadow: '0 4px 12px rgba(220,38,38,0.4)',
          letterSpacing: 2,
        }}>
        🚨 EMERGENCY STOP
      </button>
    )
  }

  return (
    <div style={{
      background: '#fef2f2', border: '3px solid #dc2626', borderRadius: 12, padding: 20,
    }}>
      <h3 style={{ margin: '0 0 12px', color: '#991b1b', fontSize: 18 }}>
        ⚠️ Confirm Emergency Stop
      </h3>
      <p style={{ fontSize: 14, color: '#7f1d1d', marginBottom: 12 }}>
        This will cancel all current robot tasks. Moving robots will stop at next node.
      </p>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 13, color: '#6b7280', marginBottom: 4 }}>
          Target Brand (* = all)
        </label>
        <select value={targetBrand} onChange={e => setTargetBrand(e.target.value)}
          style={{ width: '100%', padding: '8px', fontSize: 14, border: '1px solid #d1d5db', borderRadius: 4 }}>
          <option value="*">All brands ({brands.length})</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={handleEStop} disabled={sending}
          style={{
            flex: 1, padding: '12px', fontSize: 16, fontWeight: 700,
            background: sending ? '#9ca3af' : '#dc2626', color: '#fff',
            border: 'none', borderRadius: 8, cursor: sending ? 'not-allowed' : 'pointer',
          }}>
          {sending ? 'Sending…' : 'Confirm Stop'}
        </button>
        <button onClick={() => { setConfirming(false); setResult(null) }}
          style={{
            padding: '12px 20px', fontSize: 14, background: '#fff', color: '#374151',
            border: '1px solid #d1d5db', borderRadius: 8, cursor: 'pointer',
          }}>
          Cancel
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
