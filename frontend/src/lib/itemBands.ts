/**
 * The inbox bands' identity — rank order, label, and dot colour — keyed by an
 * Item's `kind`. `review` is a decision you owe; `question` is one the agent is
 * blocked on. This is the single source of that identity, shared by the two
 * surfaces that render the inbox (the /supervisor fleet queue and the per-agent
 * rail) so their band order and colours can never drift apart.
 */

/** The two inbox kinds, in rank order. Matches the server's ranking
 *  (apps/harness/items_api.py::list_fleet_items). */
export type ItemKind = 'review' | 'question'

export const ITEM_KIND_RANK: ItemKind[] = ['review', 'question']

export const ITEM_BAND: Record<ItemKind, { label: string; blurb: string; dot: string }> = {
  review: {
    label: 'Review',
    blurb: 'A decision to make — implement, skip, or defer',
    dot: 'bg-muted-foreground',
  },
  question: {
    label: 'Question',
    blurb: 'The agent is blocked and needs your answer',
    dot: 'bg-warning',
  },
}
