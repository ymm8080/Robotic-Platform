/**
 * Parse uploaded warehouse area files.
 * Supports: .xlsx, .xls, .csv, .tsv, .txt (tab/comma delimited), .json
 */
import * as XLSX from 'xlsx'
import type { WareArea } from '../hooks/useAreas'

export interface ParseResult {
  ok: boolean
  areas: WareArea[]
  error?: string
}

/** Column header mappings for warehouse area data */
const HEADERS: Record<string, keyof WareArea> = {
  'id': 'id',
  'warehouse area id': 'id',
  'area id': 'id',
  'areaid': 'id',
  'warehouseid': 'id',
  'wh id': 'id',
  'name': 'name',
  'warehouse name': 'name',
  'warehouse': 'name',
  'area name': 'name',
  'wh name': 'name',
  'from storage type': 'fromStorageType',
  'from_storage_type': 'fromStorageType',
  'fromstoragetype': 'fromStorageType',
  'from type': 'fromStorageType',
  'from storage section': 'fromStorageSection',
  'from_storage_section': 'fromStorageSection',
  'fromstoragesection': 'fromStorageSection',
  'from section': 'fromStorageSection',
  'from storage bin': 'fromStorageBin',
  'from_storage_bin': 'fromStorageBin',
  'fromstoragebin': 'fromStorageBin',
  'from bin': 'fromStorageBin',
  'to storage type': 'toStorageType',
  'to_storage_type': 'toStorageType',
  'tostoragetype': 'toStorageType',
  'to type': 'toStorageType',
  'to storage section': 'toStorageSection',
  'to_storage_section': 'toStorageSection',
  'tostoragesection': 'toStorageSection',
  'to section': 'toStorageSection',
  'to storage bin': 'toStorageBin',
  'to_storage_bin': 'toStorageBin',
  'tostoragebin': 'toStorageBin',
  'to bin': 'toStorageBin',
  'zonex': 'zoneX',
  'zone x': 'zoneX',
  'zoney': 'zoneY',
  'zone y': 'zoneY',
  'zonew': 'zoneW',
  'zone w': 'zoneW',
  'width': 'zoneW',
  'zoneh': 'zoneH',
  'zone h': 'zoneH',
  'height': 'zoneH',
  'zonecolor': 'zoneColor',
  'zone color': 'zoneColor',
  'color': 'zoneColor',
}

function mapHeaders(row: Record<string, unknown>): Record<string, string> {
  const mapped: Record<string, string> = {}
  for (const [key, value] of Object.entries(row)) {
    const lower = key.trim().toLowerCase()
    const field = HEADERS[lower]
    if (field && typeof value !== 'undefined' && value !== null) {
      mapped[field] = String(value).trim()
    }
  }
  return mapped
}

function rowToArea(row: Record<string, unknown>): WareArea | null {
  const m = mapHeaders(row)
  if (!m.id || !m.name) return null // id and name are required
  return {
    id: m.id,
    name: m.name,
    fromStorageType: m.fromStorageType ?? '',
    fromStorageSection: m.fromStorageSection ?? '',
    fromStorageBin: m.fromStorageBin ?? '',
    toStorageType: m.toStorageType ?? '',
    toStorageSection: m.toStorageSection ?? '',
    toStorageBin: m.toStorageBin ?? '',
    zoneX: typeof row.zoneX === 'number' ? row.zoneX : 10,
    zoneY: typeof row.zoneY === 'number' ? row.zoneY : 10,
    zoneW: typeof row.zoneW === 'number' ? row.zoneW : 200,
    zoneH: typeof row.zoneH === 'number' ? row.zoneH : 150,
    zoneColor: (row.zoneColor as string) ?? '#dbeafe',
  }
}

/** Parse a delimited text buffer (CSV/TSV/TXT) */
function parseDelimited(raw: string, delimiter: string): WareArea[] {
  const lines = raw.split(/\r?\n/).filter(line => line.trim())
  if (lines.length < 2) return []

  const headers = lines[0].split(delimiter).map(h => h.trim().toLowerCase())
  const result: WareArea[] = []

  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(delimiter)
    const row: Record<string, unknown> = {}
    for (let j = 0; j < headers.length; j++) {
      row[headers[j]] = (values[j] ?? '').trim()
    }
    const area = rowToArea(row)
    if (area) result.push(area)
  }

  return result
}

/** Parse Excel buffer (.xlsx/.xls) */
function parseExcel(buffer: ArrayBuffer): WareArea[] {
  const workbook = XLSX.read(buffer, { type: 'array' })
  const sheetName = workbook.SheetNames[0]
  if (!sheetName) return []
  const sheet = workbook.Sheets[sheetName]
  const data = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' })
  return data.map(rowToArea).filter((a): a is WareArea => a !== null)
}

/** Parse CSV text */
function parseCSV(raw: string): WareArea[] {
  return parseDelimited(raw, ',')
}

/** Parse TSV/TXT text (tab delimited) */
function parseTSV(raw: string): WareArea[] {
  return parseDelimited(raw, '\t')
}

/** Parse JSON text */
function parseJSON(raw: string): WareArea[] {
  const parsed = JSON.parse(raw)
  if (!Array.isArray(parsed)) throw new Error('JSON must be an array of objects')
  return parsed.map(rowToArea).filter((a): a is WareArea => a !== null)
}

/** Auto-detect delimiter for TXT files */
function autoParseText(raw: string): WareArea[] {
  const firstLine = raw.split(/\r?\n/)[0] ?? ''
  const tabs = (firstLine.match(/\t/g) || []).length
  const commas = (firstLine.match(/,/g) || []).length
  if (tabs >= commas && tabs > 0) return parseTSV(raw)
  if (commas > 0) return parseCSV(raw)
  return parseTSV(raw) // fallback to TSV
}

/**
 * Main entry: parse an uploaded file by name + buffer content.
 */
export function parseAreasFile(fileName: string, buffer: ArrayBuffer): ParseResult {
  try {
    const ext = fileName.split('.').pop()?.toLowerCase() ?? ''
    let areas: WareArea[]

    if (ext === 'xlsx' || ext === 'xls') {
      areas = parseExcel(buffer)
    } else if (ext === 'csv') {
      areas = parseCSV(new TextDecoder().decode(buffer))
    } else if (ext === 'tsv') {
      areas = parseTSV(new TextDecoder().decode(buffer))
    } else if (ext === 'txt') {
      areas = autoParseText(new TextDecoder().decode(buffer))
    } else if (ext === 'json') {
      areas = parseJSON(new TextDecoder().decode(buffer))
    } else {
      return { ok: false, areas: [], error: `Unsupported file type: .${ext}. Supported: .xlsx, .xls, .csv, .tsv, .txt, .json` }
    }

    if (areas.length === 0) {
      return { ok: false, areas: [], error: 'No valid warehouse area records found. Required columns: ID, Name.' }
    }

    return { ok: true, areas }
  } catch (e) {
    return { ok: false, areas: [], error: (e as Error).message }
  }
}

/** Generate a CSV template string for download */
const TEMPLATE_HEADERS = ['Warehouse Area ID', 'Warehouse Name', 'From Storage Type', 'From Storage Section', 'From Storage Bin', 'To Storage Type', 'To Storage Section', 'To Storage Bin', 'ZoneX', 'ZoneY', 'ZoneW', 'ZoneH', 'ZoneColor']
const TEMPLATE_SAMPLE = ['WH-C', 'Warehouse C', 'A03', '02', '001', 'B03', '02', '999', '10', '10', '200', '150', '#dbeafe']

export function generateTemplateCSV(): string {
  return TEMPLATE_HEADERS.join(',') + '\n' + TEMPLATE_SAMPLE.join(',') + '\n'
}

/** Generate Excel template for download */
export function generateTemplateExcel(): ArrayBuffer {
  const ws = XLSX.utils.aoa_to_sheet([TEMPLATE_HEADERS, TEMPLATE_SAMPLE])
  ws['!cols'] = TEMPLATE_HEADERS.map(() => ({ wch: 18 }))
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Warehouse Areas')
  return XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
}
