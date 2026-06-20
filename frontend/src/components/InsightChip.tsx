import type { InsightCategory } from '@/api/insights'

export const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string; label: string }> = {
  ship_gap: { bg: 'bg-warning/5', border: 'border-warning/20', text: 'text-warning', label: 'Ship Gap' },
  hygiene: { bg: 'bg-primary/5', border: 'border-primary/20', text: 'text-primary', label: 'Hygiene' },
  pattern: { bg: 'bg-special/5', border: 'border-special/20', text: 'text-special', label: 'Pattern' },
  stale: { bg: 'bg-foreground-secondary/5', border: 'border-muted-foreground/20', text: 'text-muted-foreground', label: 'Stale' },
  opportunity: { bg: 'bg-success/5', border: 'border-success/20', text: 'text-success', label: 'Opportunity' },
  alignment: { bg: 'bg-info/5', border: 'border-info/20', text: 'text-info', label: 'Alignment' },
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
