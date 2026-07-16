import { describe, it, expect } from 'vitest'
import { problemMessage } from './problem'

describe('problemMessage', () => {
  it('prefers the per-occurrence detail', () => {
    // The concrete case: POST /schedules/ 409s with a real reason. Without this
    // the user sees "Failed to create schedule" and has no idea a name collided.
    expect(
      problemMessage(
        {
          type: 'https://canopy-web.dimagi.com/problems/conflict',
          title: 'Conflict',
          status: 409,
          detail: "A schedule named 'Weekly report' already exists for this agent.",
        },
        'Failed to create schedule',
      ),
    ).toBe("A schedule named 'Weekly report' already exists for this agent.")
  })

  it('falls back to title when detail is absent', () => {
    // `detail` is optional in the Problem model; `title` never is.
    expect(problemMessage({ title: 'Not found', status: 404 }, 'Failed to load')).toBe(
      'Not found',
    )
  })

  it('ignores an empty or whitespace detail', () => {
    expect(
      problemMessage({ title: 'Conflict', detail: '   ' }, 'Failed to create schedule'),
    ).toBe('Conflict')
  })

  it('falls back to the generic message when neither field is a string', () => {
    expect(problemMessage({ detail: 42, title: null }, 'Failed to run schedule')).toBe(
      'Failed to run schedule',
    )
  })

  it('falls back for a non-problem body', () => {
    // A proxy's HTML 502 or an opaque network failure never parses to a
    // problem+json object — it must not produce "[object Object]".
    expect(problemMessage('<html>502</html>', 'Failed to load schedules')).toBe(
      'Failed to load schedules',
    )
    expect(problemMessage(undefined, 'Failed to load schedules')).toBe(
      'Failed to load schedules',
    )
    expect(problemMessage(null, 'Failed to load schedules')).toBe('Failed to load schedules')
  })
})
