import type { NeedsYouType } from '@/api/agents'

/**
 * The three bands' identity — rank order, label, and dot colour.
 *
 * Two surfaces render this inbox and they are deliberately NOT one component:
 * `/supervisor`'s WaitingOnYou is a read-only ranked queue flattened across the
 * fleet (a phone, one thumb), while the agent rail's NeedsYouSection renders the
 * actionable board card so you accept/decline in place. Unifying them would take
 * ~6 props to serve 2 callers.
 *
 * What they DO share is what a band *is*, and that is what drifted: the Review
 * dot rendered `bg-info` on one and `bg-muted-foreground` on the other until a
 * review caught it. So this module is the band's identity and nothing else —
 * per-band copy that only one surface shows (the rail's blurbs) stays there.
 */

/** Rank order, matching the server's own (apps/agents/services.py::needs_you). */
export const NEEDS_YOU_RANK: NeedsYouType[] = ['review', 'question']

export const NEEDS_YOU_BAND: Record<NeedsYouType, { label: string; dot: string }> = {
  review: { label: 'Review', dot: 'bg-muted-foreground' },
  question: { label: 'Question', dot: 'bg-warning' },
}
