import { useState, useCallback } from 'react'

export interface WareArea {
  id: string
  name: string
  fromStorageType: string
  fromStorageSection: string
  fromStorageBin: string
  toStorageType: string
  toStorageSection: string
  toStorageBin: string
  /** Map zone position — X offset on canvas */
  zoneX: number
  /** Map zone position — Y offset on canvas */
  zoneY: number
  /** Map zone — width */
  zoneW: number
  /** Map zone — height */
  zoneH: number
  /** Map zone — background color (hex) */
  zoneColor: string
}

const STORAGE_KEY = 'robot_dashboard_warehouse_areas'

export const DEFAULT_AREAS: WareArea[] = [
  { id: 'WH-A', name: 'Warehouse A', fromStorageType: 'A01', fromStorageSection: '01', fromStorageBin: '001', toStorageType: 'B01', toStorageSection: '01', toStorageBin: '999', zoneX: 10, zoneY: 10, zoneW: 410, zoneH: 280, zoneColor: '#dbeafe' },
  { id: 'WH-B', name: 'Warehouse B', fromStorageType: 'A02', fromStorageSection: '01', fromStorageBin: '001', toStorageType: 'B02', toStorageSection: '01', toStorageBin: '999', zoneX: 430, zoneY: 10, zoneW: 410, zoneH: 280, zoneColor: '#fce7f3' },
]

export function loadAreas(): WareArea[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      saveAreas(DEFAULT_AREAS)
      return [...DEFAULT_AREAS]
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return [...DEFAULT_AREAS]
    // Normalize old-format areas (key/label) to new format
    const COLORS = ['#dbeafe', '#fce7f3', '#d1fae5', '#fef3c7', '#e0e7ff', '#f3e8ff', '#ffe4e6', '#ecfdf5']
    return parsed.map((a: Record<string, unknown>, idx: number) => {
      // Stagger zone positions so areas don't overlap: 2 columns, auto-row layout
      const col = idx % 2
      const row = Math.floor(idx / 2)
      const defaultX = col === 0 ? 10 : 440
      const defaultY = 10 + row * 160
      const defaultW = 410
      const defaultH = 140
      return {
        id: (a.id as string) ?? (a.key as string) ?? '',
        name: (a.name as string) ?? (a.label as string) ?? (a.id as string) ?? '',
        fromStorageType: (a.fromStorageType as string) ?? '',
        fromStorageSection: (a.fromStorageSection as string) ?? '',
        fromStorageBin: (a.fromStorageBin as string) ?? '',
        toStorageType: (a.toStorageType as string) ?? '',
        toStorageSection: (a.toStorageSection as string) ?? '',
        toStorageBin: (a.toStorageBin as string) ?? '',
        zoneX: typeof a.zoneX === 'number' ? a.zoneX : defaultX,
        zoneY: typeof a.zoneY === 'number' ? a.zoneY : defaultY,
        zoneW: typeof a.zoneW === 'number' ? a.zoneW : defaultW,
        zoneH: typeof a.zoneH === 'number' ? a.zoneH : defaultH,
        zoneColor: (a.zoneColor as string) ?? COLORS[idx % COLORS.length],
      }
    })
  } catch {
    return [...DEFAULT_AREAS]
  }
}

export function saveAreas(areas: WareArea[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(areas))
}

export function areaLabel(id: string): string {
  const areas = loadAreas()
  return areas.find(a => a.id === id)?.name ?? id
}

export function useAreas() {
  const [areas, setAreas] = useState<WareArea[]>(loadAreas)

  const addArea = useCallback((area: WareArea) => {
    const all = loadAreas()
    if (all.find(a => a.id === area.id)) return false
    all.push(area)
    saveAreas(all)
    setAreas(all)
    return true
  }, [])

  const updateArea = useCallback((oldId: string, area: WareArea) => {
    const all = loadAreas()
    const idx = all.findIndex(a => a.id === oldId)
    if (idx === -1) return
    all[idx] = area
    saveAreas(all)
    setAreas(all)
  }, [])

  const deleteArea = useCallback((id: string) => {
    const all = loadAreas().filter(a => a.id !== id)
    saveAreas(all)
    setAreas(all)
    // Clean up user assignments referencing this area
    const USERS_KEY = 'robot_dashboard_users'
    try {
      const raw = localStorage.getItem(USERS_KEY)
      if (raw) {
        const users = JSON.parse(raw)
        let changed = false
        for (const u of users) {
          if (Array.isArray(u.functionAreas)) {
            const before = u.functionAreas.length
            u.functionAreas = u.functionAreas.filter((k: string) => k !== id)
            if (u.functionAreas.length !== before) changed = true
          }
        }
        if (changed) localStorage.setItem(USERS_KEY, JSON.stringify(users))
      }
    } catch { /* ignore */ }
  }, [])

  const resetDefaults = useCallback(() => {
    saveAreas(DEFAULT_AREAS)
    setAreas([...DEFAULT_AREAS])
  }, [])

  return { areas, setAreas, addArea, updateArea, deleteArea, resetDefaults }
}
