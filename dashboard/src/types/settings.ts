/** User alert threshold settings */

export interface UserSettings {
  batteryThreshold: number
  cpuThreshold: number
  memoryThreshold: number
  errorRateThresholdPct: number
  offlineAlertEnabled: boolean
  robotErrorAlertEnabled: boolean
}

export const DEFAULT_SETTINGS: UserSettings = {
  batteryThreshold: 20,
  cpuThreshold: 80,
  memoryThreshold: 85,
  errorRateThresholdPct: 5,
  offlineAlertEnabled: true,
  robotErrorAlertEnabled: true,
}

export interface SettingsField {
  key: keyof UserSettings
  label: string
  description: string
  min: number
  max: number
  step: number
  unit: string
  /** If true, render as a toggle instead of a slider */
  isToggle?: boolean
}

export const SETTINGS_FIELDS: SettingsField[] = [
  {
    key: 'batteryThreshold',
    label: 'Battery Alert Threshold',
    description: 'Alert when any robot battery drops below this percentage',
    min: 0,
    max: 100,
    step: 5,
    unit: '%',
  },
  {
    key: 'cpuThreshold',
    label: 'CPU Alert Threshold',
    description: 'Alert when any service CPU usage exceeds this percentage',
    min: 0,
    max: 100,
    step: 5,
    unit: '%',
  },
  {
    key: 'memoryThreshold',
    label: 'Memory Alert Threshold',
    description: 'Alert when any service memory usage exceeds this percentage',
    min: 0,
    max: 100,
    step: 5,
    unit: '%',
  },
  {
    key: 'errorRateThresholdPct',
    label: 'Error Rate Threshold',
    description: 'Alert when system error rate exceeds this percentage',
    min: 0,
    max: 100,
    step: 1,
    unit: '%',
  },
]
