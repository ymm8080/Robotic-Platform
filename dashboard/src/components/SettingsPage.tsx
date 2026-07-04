import { useSettings } from '../context/SettingsContext'
import type { SettingsField } from '../types/settings'

export function SettingsPage() {
  const { settings, updateSetting, resetDefaults, saveMessage, fields } = useSettings()

  return (
    <div>
      {/* Save indicator */}
      {saveMessage && (
        <div style={{
          marginBottom: 12, padding: '6px 12px', borderRadius: 6,
          background: saveMessage === 'Saved' ? '#f0fdf4' : '#eff6ff',
          border: `1px solid ${saveMessage === 'Saved' ? '#bbf7d0' : '#bfdbfe'}`,
          color: saveMessage === 'Saved' ? '#15803d' : '#1d4ed8',
          fontSize: 13, fontWeight: 600,
          display: 'inline-block',
        }}>
          ✓ {saveMessage}
        </div>
      )}

      {/* Thresholds section */}
      <Section title="Alert Thresholds"
        subtitle="Configure the thresholds below which alerts will be triggered">
        {fields.map(field => (
          <ThresholdRow
            key={field.key}
            field={field}
            value={settings[field.key] as number}
            onChange={v => updateSetting(field.key, v)}
          />
        ))}
      </Section>

      {/* Toggle preferences */}
      <Section title="Alert Preferences"
        subtitle="Choose which types of alerts to show">
        <ToggleRow
          label="Offline Robot Alerts"
          description="Show alert when a robot goes offline"
          checked={settings.offlineAlertEnabled}
          onChange={v => updateSetting('offlineAlertEnabled', v)}
        />
        <ToggleRow
          label="Robot Error Alerts"
          description="Show alert when a robot reports an error state"
          checked={settings.robotErrorAlertEnabled}
          onChange={v => updateSetting('robotErrorAlertEnabled', v)}
        />
      </Section>

      {/* Reset */}
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #e5e7eb' }}>
        <button
          onClick={resetDefaults}
          style={{
            padding: '8px 18px', fontSize: 13, fontWeight: 600,
            background: '#fff', color: '#6b7280', border: '1px solid #d1d5db',
            borderRadius: 6, cursor: 'pointer',
          }}>
          Reset to Defaults
        </button>
      </div>
    </div>
  )
}

/* ── Sub-components ── */

function Section({ title, subtitle, children }: {
  title: string; subtitle: string; children: React.ReactNode
}) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 2px', color: '#111827' }}>
        {title}
      </h3>
      <p style={{ fontSize: 12, color: '#9ca3af', margin: '0 0 12px' }}>
        {subtitle}
      </p>
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
        padding: '16px',
      }}>
        {children}
      </div>
    </div>
  )
}

function ThresholdRow({ field, value, onChange }: {
  field: SettingsField; value: number; onChange: (v: number) => void
}) {
  const pct = ((value - field.min) / (field.max - field.min)) * 100

  const color =
    value >= 80 ? '#ef4444' :
    value >= 50 ? '#f59e0b' :
    '#22c55e'

  return (
    <div style={{
      padding: '12px 0',
      borderBottom: '1px solid #f3f4f6',
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 8, gap: 12,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
            {field.label}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
            {field.description}
          </div>
        </div>
        {/* Number input + unit */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 2,
          minWidth: 72, justifyContent: 'flex-end',
        }}>
          <input type="number"
            min={field.min} max={field.max} step={field.step}
            value={value}
            onChange={e => {
              const v = parseInt(e.target.value) || 0
              onChange(Math.max(field.min, Math.min(field.max, v)))
            }}
            style={{
              width: 48, padding: '4px 6px', fontSize: 14, fontWeight: 700,
              textAlign: 'center', border: `1px solid #d1d5db`, borderRadius: 4,
              outline: 'none', color,
            }}
            onFocus={e => { e.currentTarget.style.borderColor = '#3b82f6' }}
            onBlur={e => { e.currentTarget.style.borderColor = '#d1d5db' }}
          />
          <span style={{ fontSize: 13, color: '#6b7280' }}>{field.unit}</span>
        </div>
      </div>

      {/* Slider */}
      <input type="range"
        min={field.min} max={field.max} step={field.step}
        value={value}
        onChange={e => onChange(parseInt(e.target.value))}
        style={{
          width: '100%', height: 6, appearance: 'none',
          background: `linear-gradient(to right, #22c55e 0%, #22c55e ${pct * 0.5}%, #f59e0b ${pct * 0.5}%, #f59e0b ${pct * 0.75}%, #ef4444 ${pct * 0.75}%, #ef4444 100%)`,
          borderRadius: 3, outline: 'none', cursor: 'pointer',
          accentColor: color,
        }}
      />
    </div>
  )
}

function ToggleRow({ label, description, checked, onChange }: {
  label: string; description: string; checked: boolean; onChange: (v: boolean) => void
}) {
  return (
    <div style={{
      padding: '12px 0', borderBottom: '1px solid #f3f4f6',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12,
    }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>{label}</div>
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{description}</div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        role="switch"
        aria-checked={checked}
        style={{
          width: 44, height: 24, borderRadius: 12, border: 'none',
          background: checked ? '#22c55e' : '#d1d5db',
          cursor: 'pointer', position: 'relative', flexShrink: 0,
          transition: 'background 0.15s',
        }}>
        <span style={{
          display: 'block', width: 18, height: 18, borderRadius: '50%',
          background: '#fff', boxShadow: '0 1px 2px rgba(0,0,0,0.15)',
          position: 'absolute', top: 3,
          left: checked ? 23 : 3,
          transition: 'left 0.15s',
        }} />
      </button>
    </div>
  )
}
