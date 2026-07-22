import type { AgentOut } from '@/api/agents'

export interface RankedAgent {
  agent: AgentOut
  /** 1-based position of the runner kind in the agent's runner_preference. */
  rank: number
}

export interface KindPriority {
  /** Agents whose preference includes the kind, sorted by rank ascending. */
  ranked: RankedAgent[]
  /** Agents with an empty/absent preference — implicitly accept every kind. */
  acceptsAll: AgentOut[]
}

// Which agents route work to a runner of `kind`, and how strongly.
// runner_preference is an ordered list of runner KINDS; empty/absent means
// "any eligible runner, first-poll-wins" (implicitly accepts every kind).
export function agentsForKind(agents: AgentOut[], kind: string): KindPriority {
  const ranked: RankedAgent[] = []
  const acceptsAll: AgentOut[] = []
  for (const agent of agents) {
    const pref = agent.runner_preference ?? []
    if (pref.length === 0) {
      acceptsAll.push(agent)
      continue
    }
    const idx = pref.indexOf(kind)
    if (idx >= 0) ranked.push({ agent, rank: idx + 1 })
    // A non-empty preference that omits `kind` never claims it — excluded.
  }
  ranked.sort((a, b) => a.rank - b.rank) // Array.sort is stable (ES2019+)
  return { ranked, acceptsAll }
}

// Count of agents that rank `kind` as their #1 choice — the runner's true
// prioritizers, shown as the list-view chip.
export function firstChoiceCount(agents: AgentOut[], kind: string): number {
  return agents.filter((a) => (a.runner_preference ?? [])[0] === kind).length
}

// 1 -> "1st", 2 -> "2nd", 3 -> "3rd", 11 -> "11th", 21 -> "21st".
export function ordinal(n: number): string {
  const rem100 = n % 100
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`
  switch (n % 10) {
    case 1:
      return `${n}st`
    case 2:
      return `${n}nd`
    case 3:
      return `${n}rd`
    default:
      return `${n}th`
  }
}
