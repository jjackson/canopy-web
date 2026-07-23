import { describe, expect, it } from 'vitest'

import { applyFrame, EMPTY_SUPERVISOR_STATE } from './useLiveSupervisor'
import type { SupervisorRunnerLive } from '@/api/types.ws'

const runner = (id: string, status = 'online'): SupervisorRunnerLive => ({
  id,
  name: `r-${id}`,
  kind: 'cloud',
  status,
  last_heartbeat_at: null,
})

describe('applyFrame', () => {
  it('seeds state from a snapshot', () => {
    const s = applyFrame(EMPTY_SUPERVISOR_STATE, {
      type: 'supervisor.snapshot',
      runners: [runner('a')],
      waiting: { echo: 2 },
      total_waiting: 2,
    })
    expect(Object.keys(s.runners)).toEqual(['a'])
    expect(s.waiting).toEqual({ echo: 2 })
    expect(s.totalWaiting).toBe(2)
  })

  it('upserts a runner by id on a runner delta', () => {
    const seeded = applyFrame(EMPTY_SUPERVISOR_STATE, {
      type: 'supervisor.snapshot',
      runners: [runner('a', 'online')],
      waiting: {},
      total_waiting: 0,
    })
    const next = applyFrame(seeded, { type: 'supervisor.runner', runner: runner('a', 'stale') })
    expect(next.runners['a'].status).toBe('stale')
  })

  it('updates a waiting count and recomputes the total', () => {
    const seeded = applyFrame(EMPTY_SUPERVISOR_STATE, {
      type: 'supervisor.snapshot',
      runners: [],
      waiting: { echo: 1, ada: 1 },
      total_waiting: 2,
    })
    const next = applyFrame(seeded, { type: 'supervisor.waiting', agent: 'echo', waiting_count: 4 })
    expect(next.waiting).toEqual({ echo: 4, ada: 1 })
    expect(next.totalWaiting).toBe(5)
  })

  it('sets sessions from a sessions push and preserves them across a snapshot', () => {
    const withSessions = applyFrame(EMPTY_SUPERVISOR_STATE, {
      type: 'supervisor.sessions',
      sessions: [{ emdash_task: 'echo-1', project: 'echo' }],
    })
    expect(withSessions.sessions).toHaveLength(1)
    // a later snapshot (runners/waiting) must not clobber the live sessions list
    const afterSnap = applyFrame(withSessions, {
      type: 'supervisor.snapshot',
      runners: [],
      waiting: {},
      total_waiting: 0,
    })
    expect(afterSnap.sessions).toHaveLength(1)
  })

})
