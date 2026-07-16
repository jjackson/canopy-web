// The command a composer dispatch actually sends. A launchable skill fires the
// agent's namespaced `/{slug}:{name} {args}`; an empty skill name is a free
// prompt sent verbatim. Kept pure (no React) so the exact string — which is what
// lands in the agent's session — is unit-testable; the component only wires it.

export function buildDispatchPrompt(slug: string, skillName: string, args: string): string {
  const trimmed = args.trim()
  if (!skillName) return trimmed // free prompt
  return trimmed ? `/${slug}:${skillName} ${trimmed}` : `/${slug}:${skillName}`
}

export function canDispatch(slug: string, prompt: string): boolean {
  return slug.trim() !== '' && prompt.trim() !== ''
}
