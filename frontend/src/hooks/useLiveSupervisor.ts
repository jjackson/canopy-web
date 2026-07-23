import { useEffect, useRef, useState } from 'react'

import type { EmdashSessionOut } from '@/api/harness'
import type { SupervisorFrame, SupervisorRunnerLive } from '@/api/types.ws'
import { wsUrl } from '@/lib/wsUrl'

export interface SupervisorState {
  runners: Record<string, SupervisorRunnerLive>
  waiting: Record<string, number>
  totalWaiting: number
  // null until the first sessions push arrives — the OpenSessions view uses this
  // (live, one broadcast to every device) and falls back to its own fetch otherwise.
  sessions: EmdashSessionOut[] | null
}

export const EMPTY_SUPERVISOR_STATE: SupervisorState = {
  runners: {},
  waiting: {},
  totalWaiting: 0,
  sessions: null,
}

// Pure reducer: a snapshot seeds state; runner/waiting deltas patch it. Exported
// so it unit-tests without a socket.
export function applyFrame(state: SupervisorState, frame: SupervisorFrame): SupervisorState {
  switch (frame.type) {
    case 'supervisor.snapshot': {
      const runners: Record<string, SupervisorRunnerLive> = {}
      for (const r of frame.runners) runners[r.id] = r
      // The snapshot seeds runners/waiting; sessions arrive via their own push, so
      // preserve whatever we already have (don't clobber a live list on reconnect).
      return {
        runners,
        waiting: { ...frame.waiting },
        totalWaiting: frame.total_waiting,
        sessions: state.sessions,
      }
    }
    case 'supervisor.runner':
      return { ...state, runners: { ...state.runners, [frame.runner.id]: frame.runner } }
    case 'supervisor.waiting': {
      const waiting = { ...state.waiting, [frame.agent]: frame.waiting_count }
      const totalWaiting = Object.values(waiting).reduce((a, b) => a + b, 0)
      return { ...state, waiting, totalWaiting }
    }
    case 'supervisor.sessions':
      return { ...state, sessions: frame.sessions as unknown as EmdashSessionOut[] }
    default:
      return state
  }
}

const BACKOFFS_MS = [1000, 2000, 5000, 10000]

export interface LiveSupervisor {
  runners: SupervisorRunnerLive[]
  waiting: Record<string, number>
  sessions: EmdashSessionOut[] | null
  connected: boolean
  hasSnapshot: boolean
}

// Live /supervisor: snapshot on connect, then runner/waiting deltas, over one WS
// with backoff reconnect. SupervisorPage layers this over its mount fetch.
export function useLiveSupervisor(): LiveSupervisor {
  const [state, setState] = useState<SupervisorState>(EMPTY_SUPERVISOR_STATE)
  const [connected, setConnected] = useState(false)
  const [hasSnapshot, setHasSnapshot] = useState(false)
  const attemptRef = useRef(0)

  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let closed = false

    const connect = () => {
      if (closed) return
      ws = new WebSocket(wsUrl('ws/supervisor/'))
      ws.onopen = () => {
        attemptRef.current = 0
        setConnected(true)
      }
      ws.onmessage = (msg) => {
        try {
          const frame = JSON.parse(msg.data) as SupervisorFrame
          if (frame.type === 'supervisor.snapshot') setHasSnapshot(true)
          setState((prev) => applyFrame(prev, frame))
        } catch {
          /* ignore malformed frame */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (closed) return
        const delay = BACKOFFS_MS[Math.min(attemptRef.current, BACKOFFS_MS.length - 1)]
        attemptRef.current += 1
        reconnectTimer = setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      closed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) ws.close()
    }
  }, [])

  return {
    runners: Object.values(state.runners),
    waiting: state.waiting,
    sessions: state.sessions,
    connected,
    hasSnapshot,
  }
}
