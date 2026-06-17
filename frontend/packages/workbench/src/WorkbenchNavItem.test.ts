import { describe, expect, it } from 'vitest'
import { workbenchNavItemClass } from './WorkbenchNavItem'

describe('workbenchNavItemClass', () => {
  it('uses the orange-tinted active treatment when active', () => {
    const c = workbenchNavItemClass({ active: true })
    expect(c).toContain('bg-primary/10')
    expect(c).toContain('border-primary/30')
    expect(c).toContain('text-primary')
  })
  it('uses the muted resting treatment when inactive', () => {
    const c = workbenchNavItemClass({ active: false })
    expect(c).toContain('text-muted-foreground')
    expect(c).toContain('hover:bg-accent')
    expect(c).not.toContain('bg-primary/10')
  })
})
