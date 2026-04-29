import type { InsightCategory } from '@/api/insights'

export const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string; label: string }> = {
  ship_gap: { bg: 'bg-amber-400/5', border: 'border-amber-400/20', text: 'text-amber-400', label: 'Ship Gap' },
  hygiene: { bg: 'bg-orange-400/5', border: 'border-orange-400/20', text: 'text-orange-400', label: 'Hygiene' },
  pattern: { bg: 'bg-violet-400/5', border: 'border-violet-400/20', text: 'text-violet-400', label: 'Pattern' },
  stale: { bg: 'bg-stone-400/5', border: 'border-stone-400/20', text: 'text-stone-500', label: 'Stale' },
  opportunity: { bg: 'bg-emerald-400/5', border: 'border-emerald-400/20', text: 'text-emerald-400', label: 'Opportunity' },
}

export function CategoryBadge({ category }: { category: InsightCategory | null }) {
  if (!category) return null
  const style = CATEGORY_STYLES[category]
  if (!style) return null
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${style.bg} ${style.border} ${style.text}`}>
      {style.label}
    </span>
  )
}
