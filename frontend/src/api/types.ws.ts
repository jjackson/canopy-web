// WebSocket protocol frames for the realtime transport (apps/realtime).
// Hand-written — the OpenAPI generator covers REST, not the WS protocol.

export interface TurnEventFrame {
  seq: number
  kind: string
  payload: unknown
  ts: string
}

export interface SupervisorRunnerLive {
  id: string
  name: string
  kind: string
  status: string
  last_heartbeat_at: string | null
}

export interface SupervisorSnapshotFrame {
  type: 'supervisor.snapshot'
  runners: SupervisorRunnerLive[]
  waiting: Record<string, number>
  total_waiting: number
}

export interface SupervisorRunnerFrame {
  type: 'supervisor.runner'
  runner: SupervisorRunnerLive
}

export interface SupervisorWaitingFrame {
  type: 'supervisor.waiting'
  agent: string
  waiting_count: number
}

export interface SupervisorSessionsFrame {
  type: 'supervisor.sessions'
  // The server still fans out a live sessions push (apps/realtime), but no
  // frontend consumer reads it today — useLiveSupervisor ignores this frame
  // type via applyFrame's default case. Kept loose (no EmdashSessionOut import)
  // since nothing here needs the shape.
  sessions: Record<string, unknown>[]
}

export type SupervisorFrame =
  | SupervisorSnapshotFrame
  | SupervisorRunnerFrame
  | SupervisorWaitingFrame
  | SupervisorSessionsFrame
