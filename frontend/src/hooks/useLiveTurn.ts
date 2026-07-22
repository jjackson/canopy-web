import { useEffect, useRef, useState } from 'react'

import type { TurnEventFrame } from '@/api/types.ws'
import { wsUrl } from '@/lib/wsUrl'

// Pure merge: append only unseen seqs, keep the list ordered by seq. Idempotent,
// so replay-then-live-tail and reconnect races never double-insert. Exported so
// it unit-tests without a socket (this repo's "no live DOM" test convention).
export function mergeEvents(prev: TurnEventFrame[], incoming: TurnEventFrame[]): TurnEventFrame[] {
  const seen = new Set(prev.map((e) => e.seq))
  const merged = prev.slice()
  for (const ev of incoming) {
    if (!seen.has(ev.seq)) {
      seen.add(ev.seq)
      merged.push(ev)
    }
  }
  merged.sort((a, b) => a.seq - b.seq)
  return merged
}

const BACKOFFS_MS = [1000, 2000, 5000, 10000]

export interface LiveTurn {
  events: TurnEventFrame[]
  connected: boolean
  lastError: string | null
}

// Live-tail one turn's TurnEvent ledger over the realtime WS. Reconnects with
// backoff and resumes from the highest seq seen (?after=cursor), so a drop never
// re-fetches the whole ledger. The turn view / SP2 chat consume this.
export function useLiveTurn(turnId: string | null): LiveTurn {
  const [events, setEvents] = useState<TurnEventFrame[]>([])
  const [connected, setConnected] = useState(false)
  const [lastError, setLastError] = useState<string | null>(null)
  const cursorRef = useRef(0)
  const attemptRef = useRef(0)

  useEffect(() => {
    if (!turnId) return
    // Reset per-turn state.
    setEvents([])
    cursorRef.current = 0
    attemptRef.current = 0

    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let closed = false

    const connect = () => {
      if (closed) return
      ws = new WebSocket(wsUrl(`ws/turns/${turnId}/?after=${cursorRef.current}`))

      ws.onopen = () => {
        attemptRef.current = 0
        setConnected(true)
        setLastError(null)
      }
      ws.onmessage = (msg) => {
        try {
          const frame = JSON.parse(msg.data) as { event?: TurnEventFrame }
          if (frame.event) {
            const ev = frame.event
            cursorRef.current = Math.max(cursorRef.current, ev.seq)
            setEvents((prev) => mergeEvents(prev, [ev]))
          }
        } catch {
          setLastError('bad frame')
        }
      }
      ws.onerror = () => setLastError('connection error')
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
  }, [turnId])

  return { events, connected, lastError }
}
