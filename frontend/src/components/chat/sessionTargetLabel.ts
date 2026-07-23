// The subtitle for a chat session row: who/what it targets. An agent session
// reads "with <Agent>"; a project session reads the repo name; an agentless,
// projectless session reads "no agent". Kept pure so it is unit-testable.
export function sessionTargetLabel(agentName: string | null, project: string): string {
  if (agentName) return `with ${agentName}`
  if (project) return project
  return 'no agent'
}
