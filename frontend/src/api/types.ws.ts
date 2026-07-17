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

export type SupervisorFrame =
  | SupervisorSnapshotFrame
  | SupervisorRunnerFrame
  | SupervisorWaitingFrame
