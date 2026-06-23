import { useEffect, useRef, useCallback, useState } from 'react'
import mqtt from 'mqtt'
import { CONFIG } from '../config'
import type { ConnectionMessage, StateMessage } from '../types/vda5050'

export interface RobotStream {
  connection: ConnectionMessage | null
  state: StateMessage | null
}

export type RobotMap = Map<string, RobotStream>

export interface MqttState {
  connected: boolean
  robots: RobotMap
  error: string | null
}

export function useMqtt() {
  const clientRef = useRef<mqtt.MqttClient | null>(null)
  const [state, setState] = useState<MqttState>({
    connected: false,
    robots: new Map(),
    error: null,
  })

  const updateRobot = useCallback((topic: string, payload: Buffer) => {
    const match = topic.match(new RegExp(
      `^${CONFIG.topicPrefix}/([^/]+)/([^/]+)/(connection|state)$`
    ))
    if (!match) return

    const [, manufacturer, serialNumber, type] = match
    const id = `${manufacturer}/${serialNumber}`

    try {
      if (type === 'connection') {
        const msg = JSON.parse(payload.toString()) as ConnectionMessage
        setState(prev => {
          const next = new Map(prev.robots)
          const existing = next.get(id) ?? { connection: null, state: null }
          next.set(id, { ...existing, connection: msg })
          return { ...prev, robots: next }
        })
      } else if (type === 'state') {
        const msg = JSON.parse(payload.toString()) as StateMessage
        setState(prev => {
          const next = new Map(prev.robots)
          const existing = next.get(id) ?? { connection: null, state: null }
          next.set(id, { ...existing, state: msg })
          return { ...prev, robots: next }
        })
      }
    } catch {
      // skip malformed messages
    }
  }, [])

  useEffect(() => {
    const client = mqtt.connect(CONFIG.mqttWsUrl, CONFIG.mqttOptions)
    clientRef.current = client

    client.on('connect', () => {
      setState(prev => ({ ...prev, connected: true, error: null }))
      // Subscribe to all robots' state + connection
      client.subscribe(`${CONFIG.topicPrefix}/+/+/connection`, { qos: 1 })
      client.subscribe(`${CONFIG.topicPrefix}/+/+/state`, { qos: 0 })
    })

    client.on('message', (topic, payload) => {
      updateRobot(topic, payload as Buffer)
    })

    client.on('error', (err) => {
      console.error('[MQTT]', err)
      setState(prev => ({ ...prev, error: err.message }))
    })

    client.on('close', () => {
      setState(prev => ({ ...prev, connected: false }))
    })

    return () => {
      client.end(true)
      clientRef.current = null
    }
  }, [updateRobot])

  return state
}
