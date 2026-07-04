import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useAreas, saveAreas, type WareArea } from '../hooks/useAreas'
import { FUNCTION_ROLES, type UserRole } from '../types/auth'
import { parseAreasFile, generateTemplateCSV, generateTemplateExcel, type ParseResult } from '../utils/parseAreasFile'
import { CONFIG } from '../config'
import { loadRobotAreas, saveRobotAreas, assignRobotToArea, unassignRobot } from '../hooks/useAreaAccess'

const EMPTY_AREA: WareArea = {
  id: '', name: '',
  fromStorageType: '', fromStorageSection: '', fromStorageBin: '',
  toStorageType: '', toStorageSection: '', toStorageBin: '',
  zoneX: 10, zoneY: 10, zoneW: 200, zoneH: 150, zoneColor: '#dbeafe',
}

const TABLE_COLS: { key: keyof WareArea; label: string; group?: string }[] = [
  { key: 'id', label: 'Warehouse Area ID', group: 'SAP' },
  { key: 'name', label: 'Warehouse Name', group: 'SAP' },
  { key: 'fromStorageType', label: 'From Storage Type', group: 'SAP' },
  { key: 'fromStorageSection', label: 'From Storage Section', group: 'SAP' },
  { key: 'fromStorageBin', label: 'From Storage Bin', group: 'SAP' },
  { key: 'toStorageType', label: 'To Storage Type', group: 'SAP' },
  { key: 'toStorageSection', label: 'To Storage Section', group: 'SAP' },
  { key: 'toStorageBin', label: 'To Storage Bin', group: 'SAP' },
  { key: 'zoneX', label: 'Zone X', group: 'Map' },
  { key: 'zoneY', label: 'Zone Y', group: 'Map' },
  { key: 'zoneW', label: 'Zone W', group: 'Map' },
  { key: 'zoneH', label: 'Zone H', group: 'Map' },
  { key: 'zoneColor', label: 'Zone Color', group: 'Map' },
]

export function AdminPanel() {
  const { users, updateUser, deleteUser, areaLabel, roleLabel } = useAuth()
  const { areas, setAreas, addArea, updateArea, deleteArea, resetDefaults } = useAreas()

  // ── User management state ──
  const [editingUser, setEditingUser] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  // ── Area management state ──
  const [showAddForm, setShowAddForm] = useState(false)
  const [newArea, setNewArea] = useState<WareArea>({ ...EMPTY_AREA })
  const [editingAreaId, setEditingAreaId] = useState<string | null>(null)
  const [editArea, setEditArea] = useState<WareArea>({ ...EMPTY_AREA })
  const [deleteAreaId, setDeleteAreaId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<ParseResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // ── Robot-Area assignment state ──
  const [robotAssignments, setRobotAssignments] = useState<Map<string, string>>(loadRobotAreas)
  const [apiRobotList, setApiRobotList] = useState<{ id: string; brand: string; state: string }[]>([])
  const [robotListLoading, setRobotListLoading] = useState(true)

  // Poll robot list for assignment UI
  useEffect(() => {
    let active = true
    async function fetchRobots() {
      try {
        const res = await fetch(`${CONFIG.apiBase}/v1/robots/status`, { cache: 'no-store' })
        if (!res.ok) return
        const data = await res.json()
        if (active && data.robots) {
          setApiRobotList(data.robots.map((r: any) => ({ id: r.id, brand: r.brand, state: r.state })))
        }
      } catch { /* ignore */ }
      finally { if (active) setRobotListLoading(false) }
    }
    fetchRobots()
    const id = setInterval(fetchRobots, 15000)
    return () => { active = false; clearInterval(id) }
  }, [])

  function showMsg(msg: string) {
    setMessage(msg)
    setTimeout(() => setMessage(null), 2500)
  }

  // ── Area handlers ──

  function handleAddArea() {
    if (!newArea.id.trim() || !newArea.name.trim()) {
      showMsg('Warehouse Area ID and Name are required')
      return
    }
    const ok = addArea({ ...newArea, id: newArea.id.trim(), name: newArea.name.trim() })
    if (ok) {
      setNewArea({ ...EMPTY_AREA })
      setShowAddForm(false)
      showMsg('Warehouse area added')
    } else {
      showMsg('Area ID already exists')
    }
  }

  function beginEdit(area: WareArea) {
    setEditingAreaId(area.id)
    setEditArea({ ...area })
  }

  function cancelEdit() {
    setEditingAreaId(null)
    setEditArea({ ...EMPTY_AREA })
  }

  function handleUpdate() {
    if (!editArea.id.trim() || !editArea.name.trim()) {
      showMsg('Warehouse Area ID and Name are required')
      return
    }
    updateArea(editingAreaId!, { ...editArea, id: editArea.id.trim(), name: editArea.name.trim() })
    setEditingAreaId(null)
    setEditArea({ ...EMPTY_AREA })
    showMsg('Area updated')
  }

  function handleDeleteArea(id: string) {
    deleteArea(id)
    setDeleteAreaId(null)
    showMsg('Area deleted')
  }

  // ── File upload ──

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const result = parseAreasFile(file.name, reader.result as ArrayBuffer)
      if (result.ok) {
        // Merge: update existing by ID, add new
        const map = new Map(areas.map(a => [a.id, a]))
        for (const a of result.areas) {
          map.set(a.id, a)
        }
        const merged = Array.from(map.values())
        saveAreas(merged)
        setAreas(merged)
      }
      setImportResult(result)
      setTimeout(() => setImportResult(null), 5000)
    }
    reader.readAsArrayBuffer(file)
    e.target.value = ''
  }

  function downloadTemplate(type: 'csv' | 'xlsx') {
    if (type === 'csv') {
      const blob = new Blob([generateTemplateCSV()], { type: 'text/csv' })
      downloadBlob(blob, 'warehouse_areas_template.csv')
    } else {
      const buf = generateTemplateExcel()
      const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      downloadBlob(blob, 'warehouse_areas_template.xlsx')
    }
  }

  function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  function handleExportJSON() {
    const blob = new Blob([JSON.stringify(areas, null, 2)], { type: 'application/json' })
    downloadBlob(blob, 'warehouse_areas.json')
  }

  // ── User handlers ──

  function handleSaveUser(userId: string) {
    setEditingUser(null)
    showMsg('User assignments saved')
  }

  function handleDeleteUser(userId: string) {
    deleteUser(userId)
    setConfirmDelete(null)
    showMsg('User deleted')
  }

  // ── Area input component (shared for add/edit) ──

  function AreaFields({ area, onChange }: { area: WareArea; onChange: (a: WareArea) => void }) {
    function set(k: keyof WareArea, v: string) {
      onChange({ ...area, [k]: v })
    }
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
        {TABLE_COLS.map(col => (
          <div key={col.key}>
            <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 2 }}>
              {col.label}{col.key === 'id' || col.key === 'name' ? ' *' : ''}
            </label>
            <input
              type="text"
              value={area[col.key]}
              onChange={e => set(col.key, e.target.value)}
              placeholder={col.label}
              style={{
                width: '100%', padding: '5px 8px', fontSize: 12,
                border: '1px solid #d1d5db', borderRadius: 4, outline: 'none',
                boxSizing: 'border-box',
              }}
              onFocus={e => { e.currentTarget.style.borderColor = '#3b82f6' }}
              onBlur={e => { e.currentTarget.style.borderColor = '#d1d5db' }}
            />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div>
      {/* Feedback banner */}
      {message && (
        <div style={{
          marginBottom: 12, padding: '6px 12px', borderRadius: 6,
          background: '#f0fdf4', border: '1px solid #bbf7d0',
          color: '#15803d', fontSize: 13, fontWeight: 600,
          display: 'inline-block',
        }}>
          ✓ {message}
        </div>
      )}

      {/* ═══════════════ Warehouse Area Management ═══════════════ */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexWrap: 'wrap', gap: 8, marginBottom: 8,
      }}>
        <div>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0, color: '#111827' }}>
            📦 Warehouse Area Definition
          </h3>
          <p style={{ fontSize: 12, color: '#9ca3af', margin: '2px 0 0' }}>
            Manage warehouse areas with storage type, section, and bin ranges
          </p>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Template downloads */}
          <button onClick={() => downloadTemplate('csv')}
            style={toolBtn}>
            📄 CSV Template
          </button>
          <button onClick={() => downloadTemplate('xlsx')}
            style={toolBtn}>
            📊 Excel Template
          </button>

          {/* Upload */}
          <button onClick={() => fileRef.current?.click()}
            style={toolBtn}>
            📁 Upload
          </button>
          <input ref={fileRef} type="file"
            accept=".xlsx,.xls,.csv,.tsv,.txt,.json"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />

          {/* Export */}
          <button onClick={handleExportJSON}
            style={toolBtn}>
            📥 Export
          </button>

          {/* Reset */}
          <button onClick={() => { resetDefaults(); showMsg('Areas reset to defaults') }}
            style={{ ...toolBtn, color: '#9ca3af' }}>
            ↺ Reset
          </button>

          {/* Add Warehouse Area — primary action on the right */}
          <button onClick={() => { setShowAddForm(true); setNewArea({ ...EMPTY_AREA }) }}
            style={{
              padding: '8px 18px', fontSize: 13, fontWeight: 600,
              background: '#3b82f6', color: '#fff', border: 'none',
              borderRadius: 6, cursor: 'pointer', whiteSpace: 'nowrap',
            }}>
            + Add Warehouse Area
          </button>
        </div>
      </div>

      {/* Import result */}
      {importResult && (
        <div style={{
          marginBottom: 12, padding: '6px 12px', borderRadius: 4, fontSize: 12,
          background: importResult.ok ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${importResult.ok ? '#bbf7d0' : '#fecaca'}`,
          color: importResult.ok ? '#15803d' : '#991b1b',
        }}>
          {importResult.ok
            ? `✓ Imported/updated ${importResult.areas.length} warehouse area(s)`
            : `✗ ${importResult.error}`}
        </div>
      )}

      {/* Add new area form */}
      {showAddForm && (
        <div style={{
          border: '2px solid #3b82f6', borderRadius: 8, background: '#f9fafb',
          padding: 14, marginBottom: 12,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>New Warehouse Area</span>
            <button onClick={() => setShowAddForm(false)}
              style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 16 }}>
              ✕
            </button>
          </div>
          <AreaFields area={newArea} onChange={setNewArea} />
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button onClick={handleAddArea}
              style={{
                padding: '7px 20px', fontSize: 13, fontWeight: 600,
                background: '#22c55e', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
              }}>
              ✓ Add Area
            </button>
            <button onClick={() => setShowAddForm(false)}
              style={{
                padding: '7px 16px', fontSize: 13, fontWeight: 500,
                background: '#fff', color: '#6b7280', border: '1px solid #d1d5db', borderRadius: 6, cursor: 'pointer',
              }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Areas table */}
      <div style={{
        border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff',
        overflow: 'auto', marginBottom: 24,
      }}>
        {areas.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
            No warehouse areas defined. Click "+ Add Warehouse Area" or upload a file.
          </div>
        ) : (
          <table style={{
            width: '100%', fontSize: 12, borderCollapse: 'collapse',
            minWidth: 900,
          }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                {TABLE_COLS.map(col => (
                  <th key={col.key} style={{
                    padding: '8px 10px', textAlign: 'left', fontSize: 11,
                    color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap',
                  }}>
                    {col.label}
                  </th>
                ))}
                <th style={{
                  padding: '8px 10px', textAlign: 'center', fontSize: 11,
                  color: '#6b7280', fontWeight: 600, width: 90,
                }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {areas.map(area => {
                const isEditing = editingAreaId === area.id
                const isDeleting = deleteAreaId === area.id

                if (isEditing) {
                  return (
                    <tr key={area.id} style={{ borderBottom: '1px solid #f3f4f6', background: '#f9fafb' }}>
                      {TABLE_COLS.map(col => (
                        <td key={col.key} style={{ padding: '6px 8px' }}>
                          <input
                            type="text"
                            value={editArea[col.key]}
                            onChange={e => setEditArea({ ...editArea, [col.key]: e.target.value })}
                            style={{
                              width: '100%', padding: '4px 6px', fontSize: 12,
                              border: '1px solid #3b82f6', borderRadius: 3, outline: 'none',
                              boxSizing: 'border-box',
                            }}
                          />
                        </td>
                      ))}
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                          <button onClick={handleUpdate} style={miniBtn('#22c55e')}>✓</button>
                          <button onClick={cancelEdit} style={miniBtn('#9ca3af')}>✕</button>
                        </div>
                      </td>
                    </tr>
                  )
                }

                return (
                  <tr key={area.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    {TABLE_COLS.map(col => (
                      <td key={col.key} style={{
                        padding: '8px 10px', whiteSpace: 'nowrap',
                        color: col.key === 'id' ? '#3b82f6' : col.key === 'name' ? '#374151' : '#6b7280',
                        fontWeight: col.key === 'id' || col.key === 'name' ? 600 : 400,
                      }}>
                        {area[col.key] || '—'}
                      </td>
                    ))}
                    <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                      {isDeleting ? (
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                          <button onClick={() => handleDeleteArea(area.id)} style={miniBtn('#dc2626')}>
                            Del
                          </button>
                          <button onClick={() => setDeleteAreaId(null)} style={miniBtn('#9ca3af')}>
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                          <button onClick={() => beginEdit(area)}
                            style={{ ...miniBtn('#6b7280'), fontSize: 14, width: 26 }}>
                            ✏️
                          </button>
                          <button onClick={() => setDeleteAreaId(area.id)}
                            style={{ ...miniBtn('#ef4444'), fontSize: 14, width: 26 }}>
                            🗑
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ fontSize: 11, color: '#9ca3af', marginTop: -18, marginBottom: 24 }}>
        {areas.length} area(s) · supports .xlsx, .xls, .csv, .tsv, .txt, .json uploads
      </div>

      {/* ═══════════════ Robot-Area Assignment ═══════════════ */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexWrap: 'wrap', gap: 8, marginBottom: 8,
      }}>
        <div>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0, color: '#111827' }}>
            🤖 Robot-Area Assignment
          </h3>
          <p style={{ fontSize: 12, color: '#9ca3af', margin: '2px 0 0' }}>
            Assign each robot to a warehouse area for RBAC filtering
          </p>
        </div>
      </div>

      {areas.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13,
          border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', marginBottom: 24,
        }}>
          Define warehouse areas above first before assigning robots
        </div>
      ) : robotListLoading ? (
        <div style={{
          textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13,
          border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', marginBottom: 24,
        }}>
          Loading robot list…
        </div>
      ) : apiRobotList.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13,
          border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', marginBottom: 24,
        }}>
          No robots connected. Robots will appear here once they connect.
        </div>
      ) : (
        <div style={{
          border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff',
          overflow: 'auto', marginBottom: 24,
        }}>
          <table style={{
            width: '100%', fontSize: 12, borderCollapse: 'collapse',
          }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                <th style={thStyle}>Robot ID</th>
                <th style={thStyle}>Brand</th>
                <th style={thStyle}>State</th>
                <th style={thStyle}>Assigned Area</th>
                <th style={{ ...thStyle, textAlign: 'center', width: 60 }}>Clear</th>
              </tr>
            </thead>
            <tbody>
              {apiRobotList.map(robot => {
                const currentArea = robotAssignments.get(robot.id) || ''
                return (
                  <tr key={robot.id} style={{
                    borderBottom: '1px solid #f3f4f6',
                    opacity: robot.state?.toUpperCase() === 'OFFLINE' ? 0.5 : 1,
                  }}>
                    <td style={tdStyle}>
                      <span style={{ fontWeight: 600, color: '#3b82f6' }}>{robot.id}</span>
                    </td>
                    <td style={{ ...tdStyle, color: '#6b7280' }}>{robot.brand}</td>
                    <td style={tdStyle}>
                      <span style={{
                        display: 'inline-block', padding: '1px 6px', borderRadius: 4,
                        fontSize: 11, fontWeight: 600,
                        background: robot.state?.toUpperCase() === 'ERROR' ? '#fef2f2'
                          : robot.state?.toUpperCase() === 'ONLINE' ? '#f0fdf4'
                          : '#f3f4f6',
                        color: robot.state?.toUpperCase() === 'ERROR' ? '#dc2626'
                          : robot.state?.toUpperCase() === 'ONLINE' ? '#15803d'
                          : '#6b7280',
                      }}>
                        {robot.state || 'UNKNOWN'}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <select
                        value={currentArea}
                        onChange={e => {
                          const newArea = e.target.value
                          if (newArea) {
                            assignRobotToArea(robot.id, newArea)
                          } else {
                            unassignRobot(robot.id)
                          }
                          setRobotAssignments(loadRobotAreas())
                          showMsg(`Robot ${robot.id} ${newArea ? `→ ${areaLabel(newArea)}` : 'unassigned'}`)
                        }}
                        style={{
                          padding: '4px 8px', fontSize: 12, border: '1px solid #d1d5db',
                          borderRadius: 4, outline: 'none', cursor: 'pointer',
                          background: currentArea ? '#eff6ff' : '#fff',
                          minWidth: 160,
                        }}>
                        <option value="">— Unassigned —</option>
                        {areas.map(area => (
                          <option key={area.id} value={area.id}>{area.name} ({area.id})</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ ...tdStyle, textAlign: 'center' }}>
                      {currentArea && (
                        <button onClick={() => {
                          unassignRobot(robot.id)
                          setRobotAssignments(loadRobotAreas())
                          showMsg(`Robot ${robot.id} unassigned`)
                        }}
                          style={{
                            padding: '2px 6px', fontSize: 11,
                            border: '1px solid #fecaca', borderRadius: 3,
                            background: '#fff', color: '#dc2626', cursor: 'pointer',
                          }}>
                          ✕
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontSize: 11, color: '#9ca3af', marginTop: -18, marginBottom: 24 }}>
        {Array.from(robotAssignments.values()).filter(Boolean).length} robot(s) assigned · unassigned robots visible only to admin
      </div>

      {/* ═══════════════ User Management ═══════════════ */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexWrap: 'wrap', gap: 8, marginBottom: 8,
      }}>
        <div>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0, color: '#111827' }}>
            👥 User Management
          </h3>
          <p style={{ fontSize: 12, color: '#9ca3af', margin: '2px 0 0' }}>
            {users.length} user(s) · assign areas and roles
          </p>
        </div>
      </div>

      {users.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 24, color: '#9ca3af', fontSize: 13 }}>
          No users registered
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {users.map(user => {
            const isEditing = editingUser === user.id
            const isSystemAdmin = user.role === 'admin'

            return (
              <div key={user.id} style={{
                border: `1px solid ${isEditing ? '#3b82f6' : '#e5e7eb'}`,
                borderRadius: 8, background: '#fff',
                transition: 'border-color 0.15s',
              }}>
                {/* User header row */}
                <div style={{
                  padding: '12px 14px', display: 'flex',
                  justifyContent: 'space-between', alignItems: 'center',
                  flexWrap: 'wrap', gap: 8,
                  borderBottom: isEditing ? '1px solid #f3f4f6' : 'none',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{user.username}</span>
                      <span style={{
                        padding: '1px 6px', borderRadius: 4, fontSize: 11, fontWeight: 700,
                        background: isSystemAdmin ? '#fef2f2' : '#eff6ff',
                        color: isSystemAdmin ? '#b91c1c' : '#1d4ed8',
                      }}>
                        {isSystemAdmin ? '🛡️ Admin' : '👤 User'}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                      {user.email}{user.phone ? ` · ${user.phone}` : ''}
                      {user.functionAreas.length > 0 && (
                        <span style={{ color: '#6b7280' }}>
                          {' · Areas: '}{user.functionAreas.map(areaLabel).join(', ')}
                        </span>
                      )}
                      {user.functionRoles.length > 0 && (
                        <span style={{ color: '#6b7280' }}>
                          {' · Roles: '}{user.functionRoles.map(roleLabel).join(', ')}
                        </span>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                    <button onClick={() => setEditingUser(isEditing ? null : user.id)}
                      style={{
                        padding: '4px 12px', fontSize: 12, fontWeight: 600,
                        border: '1px solid #d1d5db', borderRadius: 4,
                        background: isEditing ? '#3b82f6' : '#fff',
                        color: isEditing ? '#fff' : '#374151',
                        cursor: 'pointer',
                      }}>
                      {isEditing ? 'Cancel' : 'Edit'}
                    </button>
                    {!isSystemAdmin && confirmDelete !== user.id && (
                      <button onClick={() => setConfirmDelete(user.id)}
                        style={{
                          padding: '4px 12px', fontSize: 12, fontWeight: 600,
                          border: '1px solid #fecaca', borderRadius: 4,
                          background: '#fff', color: '#dc2626', cursor: 'pointer',
                        }}>
                        Delete
                      </button>
                    )}
                    {!isSystemAdmin && confirmDelete === user.id && (
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button onClick={() => handleDeleteUser(user.id)}
                          style={{
                            padding: '4px 8px', fontSize: 12, fontWeight: 600,
                            border: 'none', borderRadius: 4,
                            background: '#dc2626', color: '#fff', cursor: 'pointer',
                          }}>
                          Confirm
                        </button>
                        <button onClick={() => setConfirmDelete(null)}
                          style={{
                            padding: '4px 8px', fontSize: 12,
                            border: '1px solid #d1d5db', borderRadius: 4,
                            background: '#fff', color: '#6b7280', cursor: 'pointer',
                          }}>
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Warehouse Areas — always visible on every user card */}
                <div style={{
                  padding: '10px 14px', borderTop: '1px solid #f3f4f6',
                  background: '#fafafa',
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: '#6b7280', marginBottom: 6 }}>
                    🏭 Warehouse Areas
                  </div>
                  {areas.length === 0 ? (
                    <div style={{ fontSize: 12, color: '#9ca3af' }}>
                      No warehouse areas defined. Add areas in the section above first.
                    </div>
                  ) : (
                    <>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {areas.map(area => {
                          const checked = user.functionAreas.includes(area.id)
                          return (
                            <label key={area.id} style={{
                              display: 'flex', alignItems: 'center', gap: 4,
                              padding: '3px 8px', borderRadius: 4,
                              border: `1px solid ${checked ? '#3b82f6' : '#e5e7eb'}`,
                              background: checked ? '#eff6ff' : '#fff',
                              fontSize: 12, cursor: 'pointer', userSelect: 'none',
                            }}>
                              <input type="checkbox" checked={checked}
                                onChange={() => {
                                  const next = checked
                                    ? user.functionAreas.filter(k => k !== area.id)
                                    : [...user.functionAreas, area.id]
                                  updateUser(user.id, { functionAreas: next })
                                }}
                                style={{ accentColor: '#3b82f6' }}
                              />
                              <span title={area.id}>{area.name} ({area.id})</span>
                            </label>
                          )
                        })}
                      </div>
                      {user.functionAreas.length === 0 && (
                        <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 4 }}>
                          ⚠️ No areas assigned — this user won't see any robots or tasks
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Editing panel — roles & role assignment */}
                {isEditing && (
                  <div style={{ padding: '14px', borderTop: '1px solid #e5e7eb' }}>
                    <div style={{ marginBottom: 16 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                        Account Role
                      </label>
                      <select
                        value={user.role}
                        onChange={e => updateUser(user.id, { role: e.target.value as UserRole })}
                        style={{
                          padding: '6px 10px', fontSize: 13, border: '1px solid #d1d5db',
                          borderRadius: 4, outline: 'none', cursor: 'pointer',
                        }}>
                        <option value="user">👤 Normal User</option>
                        <option value="admin">🛡️ Admin</option>
                      </select>
                    </div>

                    {/* Function Roles */}
                    <div style={{ marginBottom: 16 }}>
                      <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 6 }}>
                        Function Roles
                      </label>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {FUNCTION_ROLES.map(fr => {
                          const checked = user.functionRoles.includes(fr.key)
                          return (
                            <label key={fr.key} style={{
                              display: 'flex', alignItems: 'center', gap: 4,
                              padding: '4px 10px', borderRadius: 4,
                              border: `1px solid ${checked ? '#22c55e' : '#e5e7eb'}`,
                              background: checked ? '#f0fdf4' : '#fff',
                              fontSize: 12, cursor: 'pointer', userSelect: 'none',
                            }} title={fr.description}>
                              <input type="checkbox" checked={checked}
                                onChange={() => {
                                  const next = checked
                                    ? user.functionRoles.filter(k => k !== fr.key)
                                    : [...user.functionRoles, fr.key]
                                  updateUser(user.id, { functionRoles: next })
                                }}
                                style={{ accentColor: '#22c55e' }}
                              />
                              {fr.label}
                            </label>
                          )
                        })}
                      </div>
                    </div>

                    <button onClick={() => handleSaveUser(user.id)}
                      style={{
                        padding: '8px 20px', fontSize: 13, fontWeight: 600,
                        background: '#3b82f6', color: '#fff', border: 'none',
                        borderRadius: 6, cursor: 'pointer',
                      }}>
                      Save Changes
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ── Style helpers ── */

const toolBtn: React.CSSProperties = {
  padding: '6px 12px', fontSize: 12, fontWeight: 600,
  background: '#fff', color: '#374151', border: '1px solid #d1d5db',
  borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap',
}

function miniBtn(color: string): React.CSSProperties {
  return {
    padding: '2px 6px', fontSize: 11, fontWeight: 600,
    border: `1px solid ${color}44`, borderRadius: 3,
    background: `${color}11`, color, cursor: 'pointer',
    width: 26, textAlign: 'center',
  }
}

const thStyle: React.CSSProperties = {
  padding: '8px 10px', textAlign: 'left', fontSize: 11,
  color: '#6b7280', fontWeight: 600, whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '8px 10px', whiteSpace: 'nowrap', fontSize: 12,
}
