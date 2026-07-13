# `@canopy/workbench` Shared Workbench Package — Implementation Plan

**Status: Shipped (PRs #123 / #124) — historical record, not current-state.**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract canopy-web's duplicated DDD/Agents workbench chrome into a published, ACE-seeded, semantic-token-only `@canopy/workbench` package, and migrate DDD + Agents onto it.

**Architecture:** A workspace package at `frontend/packages/workbench/` ships TypeScript source (no bundle) exporting presentational chrome primitives that emit only semantic shadcn class names (`bg-card`, `border-border`, `text-primary`, …) and carry no theme of their own. canopy's frontend consumes it via an npm workspace; Tailwind v4 scans it via `@source`. DDD and Agents compose the primitives; all domain components stay app-side. ace-web adopts the package in a later, out-of-scope pass.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS v4, Vitest (pure-logic tests only — no jsdom in this repo), clsx + tailwind-merge.

## Global Constraints

- **Semantic tokens only** inside the package — never raw `stone-*` / `orange-*` / `red-*`. Active nav style is `bg-primary/10 border border-primary/30 text-primary font-medium`; rest is `text-muted-foreground hover:bg-accent hover:text-foreground`.
- **Zero router / radix / lucide deps.** Router-agnostic via an internal `asChild` Slot. Peer deps: `react`, `react-dom`, `clsx`, `tailwind-merge`.
- **Package ships `.tsx` source**, no build artifact. Consumers transform it (it resolves to a real path under the project root) and Tailwind scans it via `@source`.
- **Tests are pure functions** (canopy vitest has no jsdom/@testing-library — do NOT add them). Testable logic is extracted into pure helpers; presentational components are gated on `tsc` + `vite build`.
- Canopy tsconfig: `module: ESNext`, `moduleResolution: bundler`, `jsx: react-jsx`, `target: ES2023`. The `@/*` alias maps to `frontend/src/*`.
- Each task ends green on `cd frontend && npm run build` (which is `tsc -b && vite build`).

---

### Task 1: Scaffold the package and wire the workspace

**Files:**
- Create: `frontend/packages/workbench/package.json`
- Create: `frontend/packages/workbench/tsconfig.json`
- Create: `frontend/packages/workbench/src/cn.ts`
- Create: `frontend/packages/workbench/src/index.ts`
- Test: `frontend/packages/workbench/src/cn.test.ts`
- Modify: `frontend/package.json` (add `workspaces` + dependency)
- Modify: `frontend/tsconfig.json` (add project reference)
- Modify: `frontend/src/index.css` (add `@source`)

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[]): string` from `@canopy/workbench`; the package resolves as `@canopy/workbench` in app code.

- [ ] **Step 1: Create the package manifest**

`frontend/packages/workbench/package.json`:
```json
{
  "name": "@canopy/workbench",
  "version": "0.1.0",
  "type": "module",
  "exports": {
    ".": "./src/index.ts"
  },
  "publishConfig": {
    "registry": "https://npm.pkg.github.com"
  },
  "peerDependencies": {
    "clsx": "^2.1.1",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "tailwind-merge": "^3.5.0"
  },
  "files": ["src"]
}
```

- [ ] **Step 2: Create the package tsconfig (composite, for project references)**

`frontend/packages/workbench/tsconfig.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "target": "ES2023",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "lib": ["ES2023", "DOM", "DOM.Iterable"]
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Write the failing test for `cn`**

`frontend/packages/workbench/src/cn.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('merges conditional classes', () => {
    expect(cn('a', false && 'b', 'c')).toBe('a c')
  })
  it('lets later tailwind classes win', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })
})
```

- [ ] **Step 4: Run the test, expect failure**

Run: `cd frontend && npx vitest run packages/workbench/src/cn.test.ts`
Expected: FAIL — cannot resolve `./cn`.

- [ ] **Step 5: Implement `cn`**

`frontend/packages/workbench/src/cn.ts`:
```ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 6: Create the barrel export**

`frontend/packages/workbench/src/index.ts`:
```ts
export { cn } from './cn'
```

- [ ] **Step 7: Wire the workspace into the frontend app**

In `frontend/package.json`, add a top-level `"workspaces"` key and the dependency. Add this key (sibling of `"dependencies"`):
```json
  "workspaces": ["packages/*"],
```
And inside `"dependencies"`, add:
```json
    "@canopy/workbench": "*",
```

- [ ] **Step 8: Add the project reference so `tsc -b` type-checks the package**

In `frontend/tsconfig.json`, add a `"references"` array (sibling of `"files"`/`"compilerOptions"`; create it if absent):
```json
  "references": [{ "path": "./packages/workbench" }]
```

- [ ] **Step 9: Add the Tailwind `@source` so classes in the package are scanned**

In `frontend/src/index.css`, immediately after the `@import` lines at the top, add:
```css
@source "../packages/workbench/src";
```

- [ ] **Step 10: Install and verify the workspace link + build**

Run: `cd frontend && npm install && npx vitest run packages/workbench/src/cn.test.ts && npm run build`
Expected: install creates `node_modules/@canopy/workbench` symlink; vitest PASSES; `npm run build` PASSES.

- [ ] **Step 11: Commit**

```bash
git add frontend/packages/workbench frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/src/index.css
git commit -m "feat(workbench): scaffold @canopy/workbench workspace package"
```

---

### Task 2: WorkbenchNavItem (pure-tested class helper + internal asChild)

**Files:**
- Create: `frontend/packages/workbench/src/WorkbenchNavItem.tsx`
- Test: `frontend/packages/workbench/src/WorkbenchNavItem.test.ts`
- Modify: `frontend/packages/workbench/src/index.ts`

**Interfaces:**
- Consumes: `cn` (Task 1).
- Produces:
  - `workbenchNavItemClass(opts: { active?: boolean }): string`
  - `WorkbenchNavItem(props: { active?: boolean; count?: number; asChild?: boolean; children: ReactNode }): JSX.Element`

**Design note:** Both canopy consumers wrap `WorkbenchNavItem` in their own router `Link`/`NavLink` and use the **default (non-`asChild`) form** — the component renders a presentational `<div>` (label + badge), and the surrounding link is the interactive element (`<a><div>…</div></a>` is valid flow content). `asChild` is also supported for callers who want the styling merged directly onto the interactive element (cleaner DOM, e.g. a future ace-web adoption): it clones the single child via React's `cloneElement`, merges the className, and wraps the child's own text as the label alongside the badge. No `@radix-ui/react-slot` dependency — the clone is inline. The only pure-testable unit is `workbenchNavItemClass`; the component itself is gated on type-check + build.

- [ ] **Step 1: Write the failing test for the nav-item class helper**

`frontend/packages/workbench/src/WorkbenchNavItem.test.ts`:
```ts
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
```

- [ ] **Step 2: Run the test, expect failure**

Run: `cd frontend && npx vitest run packages/workbench/src/WorkbenchNavItem.test.ts`
Expected: FAIL — `./WorkbenchNavItem` not found.

- [ ] **Step 3: Implement `WorkbenchNavItem`**

`frontend/packages/workbench/src/WorkbenchNavItem.tsx`:
```tsx
import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react'
import { cn } from './cn'

export function workbenchNavItemClass({ active }: { active?: boolean }): string {
  return cn(
    'flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors',
    active
      ? 'bg-primary/10 border-primary/30 text-primary font-medium'
      : 'border-transparent text-muted-foreground hover:bg-accent hover:text-foreground',
  )
}

interface WorkbenchNavItemProps {
  active?: boolean
  count?: number
  /** When true, merge styling onto the single child element (e.g. a router Link). */
  asChild?: boolean
  children: ReactNode
}

/**
 * One rail entry: label + optional right-aligned count badge + active state.
 *
 * Default form: renders a presentational <div>; the caller wraps it in their own
 * Link/NavLink. asChild form: clones the single child, merges styling onto it,
 * and uses the child's own text as the label (router-agnostic; no radix dep).
 */
export function WorkbenchNavItem({
  active,
  count,
  asChild,
  children,
}: WorkbenchNavItemProps): JSX.Element {
  const className = workbenchNavItemClass({ active })
  const badge =
    count !== undefined ? (
      <span className="shrink-0 text-[11px] text-muted-foreground">{count}</span>
    ) : null

  if (asChild && isValidElement(children)) {
    const el = children as ReactElement<{ className?: string; children?: ReactNode }>
    return cloneElement(
      el,
      { className: cn(className, el.props.className) },
      <>
        <span className="truncate">{el.props.children}</span>
        {badge}
      </>,
    )
  }

  return (
    <div className={className}>
      <span className="truncate">{children}</span>
      {badge}
    </div>
  )
}
```

- [ ] **Step 4: Run the test, expect pass**

Run: `cd frontend && npx vitest run packages/workbench/src/WorkbenchNavItem.test.ts`
Expected: PASS.

- [ ] **Step 5: Export from the barrel**

Append to `frontend/packages/workbench/src/index.ts`:
```ts
export { WorkbenchNavItem, workbenchNavItemClass } from './WorkbenchNavItem'
```

- [ ] **Step 6: Run all package tests + build**

Run: `cd frontend && npx vitest run packages/workbench && npm run build`
Expected: all PASS; build PASSES.

- [ ] **Step 7: Commit**

```bash
git add frontend/packages/workbench/src
git commit -m "feat(workbench): add WorkbenchNavItem (pure-tested class helper + asChild)"
```

---

### Task 3: Shell scaffolding — WorkbenchShell, WorkbenchMain, WorkbenchRail, WorkbenchPane

**Files:**
- Create: `frontend/packages/workbench/src/WorkbenchShell.tsx`
- Create: `frontend/packages/workbench/src/WorkbenchMain.tsx`
- Create: `frontend/packages/workbench/src/WorkbenchRail.tsx`
- Create: `frontend/packages/workbench/src/WorkbenchPane.tsx`
- Modify: `frontend/packages/workbench/src/index.ts`

**Interfaces:**
- Consumes: `cn` (Task 1).
- Produces:
  - `WorkbenchShell(props: { header?: ReactNode; children: ReactNode; className?: string }): JSX.Element`
  - `WorkbenchMain(props: ComponentPropsWithoutRef<'main'> & { children: ReactNode }): JSX.Element` (forwards ref)
  - `WorkbenchRail(props: { width?: string; header?: ReactNode; children: ReactNode; className?: string }): JSX.Element`
  - `WorkbenchPane(props: { width?: string; side?: 'left' | 'right'; children: ReactNode; className?: string }): JSX.Element`

These are presentational; they are gated on type-check + build (no jsdom available for render tests).

- [ ] **Step 1: Implement `WorkbenchShell`**

`frontend/packages/workbench/src/WorkbenchShell.tsx`:
```tsx
import type { ReactNode } from 'react'
import { cn } from './cn'

/**
 * Full-bleed outer scaffold: optional top header over a body row. The caller
 * composes the body (rail + main + optional side panes) as children, and may
 * wrap <WorkbenchShell> in its own provider (e.g. for scroll-spy).
 */
export function WorkbenchShell({
  header,
  children,
  className,
}: {
  header?: ReactNode
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <div className={cn('flex h-full flex-col bg-background text-foreground', className)}>
      {header}
      <div className="flex flex-1 overflow-hidden">{children}</div>
    </div>
  )
}
```

- [ ] **Step 2: Implement `WorkbenchMain`**

`frontend/packages/workbench/src/WorkbenchMain.tsx`:
```tsx
import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from 'react'
import { cn } from './cn'

/**
 * The scrolling main column. Forwards a ref and arbitrary <main> props so a
 * surface can mark it as a scroll-spy root (e.g. data-ddd-scroll).
 */
export const WorkbenchMain = forwardRef<
  HTMLElement,
  ComponentPropsWithoutRef<'main'> & { children: ReactNode }
>(function WorkbenchMain({ children, className, ...rest }, ref) {
  return (
    <main ref={ref} className={cn('flex-1 overflow-y-auto', className)} {...rest}>
      {children}
    </main>
  )
})
```

- [ ] **Step 3: Implement `WorkbenchRail`**

`frontend/packages/workbench/src/WorkbenchRail.tsx`:
```tsx
import type { ReactNode } from 'react'
import { cn } from './cn'

/**
 * The bordered left rail chrome. Header slot (identity / title / filters) over a
 * scrollable body that takes arbitrary children (a tree or a flat list).
 */
export function WorkbenchRail({
  width = 'w-64',
  header,
  children,
  className,
}: {
  width?: string
  header?: ReactNode
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <aside
      className={cn(
        'flex shrink-0 flex-col border-r border-border bg-background',
        width,
        className,
      )}
    >
      {header && <div className="border-b border-border">{header}</div>}
      <div className="flex-1 overflow-y-auto">{children}</div>
    </aside>
  )
}
```

- [ ] **Step 4: Implement `WorkbenchPane`**

`frontend/packages/workbench/src/WorkbenchPane.tsx`:
```tsx
import type { ReactNode } from 'react'
import { cn } from './cn'

/** A generic bordered side panel (e.g. a detail or chat column). */
export function WorkbenchPane({
  width,
  side = 'left',
  children,
  className,
}: {
  width?: string
  side?: 'left' | 'right'
  children: ReactNode
  className?: string
}): JSX.Element {
  return (
    <section
      className={cn(
        'shrink-0 bg-background',
        side === 'right' ? 'border-l border-border' : 'border-r border-border',
        width,
        className,
      )}
    >
      {children}
    </section>
  )
}
```

- [ ] **Step 5: Export from the barrel**

Append to `frontend/packages/workbench/src/index.ts`:
```ts
export { WorkbenchShell } from './WorkbenchShell'
export { WorkbenchMain } from './WorkbenchMain'
export { WorkbenchRail } from './WorkbenchRail'
export { WorkbenchPane } from './WorkbenchPane'
```

- [ ] **Step 6: Type-check + build**

Run: `cd frontend && npm run build`
Expected: PASSES.

- [ ] **Step 7: Commit**

```bash
git add frontend/packages/workbench/src
git commit -m "feat(workbench): add Shell/Main/Rail/Pane scaffolding primitives"
```

---

### Task 4: WorkbenchSubHeader + state primitives

**Files:**
- Create: `frontend/packages/workbench/src/WorkbenchSubHeader.tsx`
- Create: `frontend/packages/workbench/src/states.tsx`
- Modify: `frontend/packages/workbench/src/index.ts`

**Interfaces:**
- Produces:
  - `WorkbenchSubHeader(props: { title: string; count?: number; action?: ReactNode }): JSX.Element`
  - `LoadingSpinner(props: { label?: string }): JSX.Element`
  - `EmptyState(props: { title: string; description?: string; action?: ReactNode }): JSX.Element`
  - `ErrorState(props: { title?: string; message: string; onRetry?: () => void }): JSX.Element`
  - `WorkbenchSkeleton(props: { rows?: number }): JSX.Element`

- [ ] **Step 1: Implement `WorkbenchSubHeader`**

`frontend/packages/workbench/src/WorkbenchSubHeader.tsx`:
```tsx
import type { ReactNode } from 'react'

/** The per-section bar inside the main area: title + count + right action. */
export function WorkbenchSubHeader({
  title,
  count,
  action,
}: {
  title: string
  count?: number
  action?: ReactNode
}): JSX.Element {
  return (
    <div className="mb-6 flex items-center justify-between gap-3 border-b border-border pb-4">
      <div className="flex min-w-0 items-baseline gap-2">
        <h1 className="text-base font-semibold text-foreground">{title}</h1>
        {count !== undefined && (
          <span className="text-[12px] text-muted-foreground">{count}</span>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
```

- [ ] **Step 2: Implement the state primitives (semantic `ErrorState`)**

`frontend/packages/workbench/src/states.tsx`:
```tsx
import type { ReactNode } from 'react'

export function LoadingSpinner({ label = 'Loading…' }: { label?: string }): JSX.Element {
  return (
    <div className="flex items-center gap-3 p-6 text-muted-foreground">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
      <span>{label}</span>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center gap-2 p-12 text-center">
      <h3 className="text-lg font-semibold text-muted-foreground">{title}</h3>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string
  message: string
  onRetry?: () => void
}): JSX.Element {
  return (
    <div className="rounded border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
      <div className="font-semibold">{title}</div>
      <div className="mt-1">{message}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded bg-destructive px-3 py-1 text-destructive-foreground hover:bg-destructive/90"
        >
          Retry
        </button>
      )}
    </div>
  )
}

/** Pulsing card placeholders while a section lazy-loads its data. */
export function WorkbenchSkeleton({ rows = 3 }: { rows?: number }): JSX.Element {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-card p-5">
          <div className="mb-2 h-4 w-2/3 rounded bg-muted" />
          <div className="h-3 w-full rounded bg-muted/70" />
        </div>
      ))}
    </div>
  )
}
```

Note: `ErrorState` uses `text-destructive-foreground` on the retry button. Verify both repos define `--destructive-foreground`; canopy's `index.css` token block must include it. If absent, add `--destructive-foreground: oklch(0.985 0 0);` to canopy `:root` and `.dark`, and the `--color-destructive-foreground: var(--destructive-foreground);` line in the `@theme inline` block. (This is checked in Step 4.)

- [ ] **Step 3: Export from the barrel**

Append to `frontend/packages/workbench/src/index.ts`:
```ts
export { WorkbenchSubHeader } from './WorkbenchSubHeader'
export { LoadingSpinner, EmptyState, ErrorState, WorkbenchSkeleton } from './states'
```

- [ ] **Step 4: Verify the destructive-foreground token exists, then build**

Run: `cd frontend && grep -n "destructive-foreground" src/index.css || echo MISSING`
If `MISSING`: add `--destructive-foreground: oklch(0.985 0 0);` to both `:root` and `.dark` in `frontend/src/index.css`, and add `--color-destructive-foreground: var(--destructive-foreground);` to the `@theme inline` block.
Then run: `cd frontend && npm run build`
Expected: PASSES.

- [ ] **Step 5: Commit**

```bash
git add frontend/packages/workbench/src frontend/src/index.css
git commit -m "feat(workbench): add SubHeader + load/empty/error/skeleton state primitives"
```

---

### Task 5: Migrate Agents onto the package

**Files:**
- Modify: `frontend/src/pages/AgentWorkspacePage.tsx`
- Rewrite: `frontend/src/components/agents/AgentLeftNav.tsx`
- Delete: `frontend/src/components/agents/SectionSubHeader.tsx`
- Modify (imports): `frontend/src/pages/agents/AgentOverviewSection.tsx`, `AgentTasksSection.tsx`, `AgentSyncsSection.tsx`, `AgentWorkProductsSection.tsx`, `AgentSkillsSection.tsx`

**Interfaces:**
- Consumes: `WorkbenchShell`, `WorkbenchMain`, `WorkbenchRail`, `WorkbenchNavItem`, `WorkbenchSubHeader`, `WorkbenchSkeleton` from `@canopy/workbench`.

- [ ] **Step 1: Rewrite `AgentLeftNav` on `WorkbenchRail` + `WorkbenchNavItem`**

Replace the entire body of `frontend/src/components/agents/AgentLeftNav.tsx`:
```tsx
import { Link, NavLink } from 'react-router-dom'
import { WorkbenchRail, WorkbenchNavItem } from '@canopy/workbench'
import type { AgentDetailOut } from '@/api/agents'

type NavItem = { to: string; label: string; count?: number }

export function AgentLeftNav({ agent }: { agent: AgentDetailOut }) {
  const items: NavItem[] = [
    { to: 'overview', label: 'Overview' },
    { to: 'tasks', label: 'Tasks', count: agent.task_count },
    { to: 'syncs', label: 'Syncs', count: agent.sync_count },
    { to: 'work-products', label: 'Work products', count: agent.work_product_count },
    { to: 'skills', label: 'Skills', count: agent.skill_count },
  ]

  const header = (
    <div className="px-4 py-4">
      <Link to="/agents" className="text-[12px] text-muted-foreground hover:text-primary transition-colors">
        ← Agents
      </Link>
      <div className="mt-3 flex items-start gap-3">
        {agent.avatar_url ? (
          <img
            src={agent.avatar_url}
            alt=""
            className="h-10 w-10 shrink-0 rounded-full border border-border object-cover"
          />
        ) : (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
            {(agent.name || agent.slug).slice(0, 1).toUpperCase()}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold leading-snug text-foreground">{agent.name}</h2>
          {agent.email && (
            <a
              href={`mailto:${agent.email}`}
              className="block truncate text-[11px] text-muted-foreground hover:text-primary transition-colors"
            >
              {agent.email}
            </a>
          )}
        </div>
      </div>
    </div>
  )

  return (
    <WorkbenchRail header={header}>
      <nav className="px-2 py-3">
        <div className="flex flex-col gap-0.5">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === 'overview'}>
              {({ isActive }) => (
                <WorkbenchNavItem active={isActive} count={item.count}>
                  {item.label}
                </WorkbenchNavItem>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </WorkbenchRail>
  )
}
```
Note: here `NavLink`'s render-prop child supplies `isActive`, and `WorkbenchNavItem` is used WITHOUT `asChild` (the `NavLink` is the interactive wrapper). This avoids nested interactive elements while keeping the count badge.

- [ ] **Step 2: Migrate `AgentWorkspacePage` to the shell**

In `frontend/src/pages/AgentWorkspacePage.tsx`:
- Add import: `import { WorkbenchShell, WorkbenchMain } from '@canopy/workbench'`
- Replace the success `return (...)` block (the `<div className="flex h-full">…</div>`) with:
```tsx
  return (
    <WorkbenchShell>
      <AgentLeftNav agent={agent} />
      <WorkbenchMain>
        <Outlet context={{ agent } satisfies AgentOutletContext} />
      </WorkbenchMain>
    </WorkbenchShell>
  )
```
- Replace the loading `return (...)` block's outer `<div className="flex h-full">…</div>` with `<WorkbenchShell>…</WorkbenchShell>` wrapping the existing skeleton aside + `<WorkbenchMain className="px-6 py-8">…</WorkbenchMain>` (keep the existing skeleton markup inside).

- [ ] **Step 3: Repoint the five section files to the package**

In EACH of `AgentOverviewSection.tsx`, `AgentTasksSection.tsx`, `AgentSyncsSection.tsx`, `AgentWorkProductsSection.tsx`, `AgentSkillsSection.tsx`:
- Replace `import { SectionSubHeader, SectionSkeleton } from '@/components/agents/SectionSubHeader'`
  with `import { WorkbenchSubHeader, WorkbenchSkeleton } from '@canopy/workbench'`
- Replace each `<SectionSubHeader ` with `<WorkbenchSubHeader ` and each `<SectionSkeleton` with `<WorkbenchSkeleton`.

Run to find every site: `cd frontend && grep -rn "SectionSubHeader\|SectionSkeleton" src/pages/agents`

- [ ] **Step 4: Delete the now-unused component file**

```bash
git rm frontend/src/components/agents/SectionSubHeader.tsx
```

- [ ] **Step 5: Build + verify no dangling references**

Run: `cd frontend && grep -rn "SectionSubHeader\|SectionSkeleton\|components/agents/SectionSubHeader" src && npm run build`
Expected: grep returns NOTHING; `npm run build` PASSES.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages frontend/src/components/agents
git commit -m "refactor(agents): migrate Agent workbench onto @canopy/workbench"
```

---

### Task 6: Migrate DDD onto the package

**Files:**
- Rewrite: `frontend/src/components/ddd/DddShell.tsx`
- Modify: `frontend/src/components/ddd/DddLeftNav.tsx`

**Interfaces:**
- Consumes: `WorkbenchShell`, `WorkbenchMain`, `WorkbenchRail`, `WorkbenchNavItem` from `@canopy/workbench`. Keeps app-side `RunSectionNavProvider` (`./runSectionNav`) and `data-ddd-scroll`.

- [ ] **Step 1: Rewrite `DddShell` on the shell primitives (keep provider + scroll-spy root)**

Replace the entire body of `frontend/src/components/ddd/DddShell.tsx`:
```tsx
import type { ReactNode } from 'react'
import { WorkbenchShell, WorkbenchMain } from '@canopy/workbench'
import { DddLeftNav } from './DddLeftNav'
import { RunSectionNavProvider } from './runSectionNav'

/**
 * DDD section chrome: the narratives→versions→runs rail + a wide scrolling main.
 * Wrapped in RunSectionNavProvider; the main carries data-ddd-scroll so the run
 * package observes its sections against the right scroll container.
 */
export function DddShell({
  activeSlug,
  activeRunId,
  children,
}: {
  activeSlug?: string
  activeRunId?: string
  children: ReactNode
}) {
  return (
    <RunSectionNavProvider>
      <WorkbenchShell>
        <DddLeftNav activeSlug={activeSlug} activeRunId={activeRunId} />
        <WorkbenchMain data-ddd-scroll>{children}</WorkbenchMain>
      </WorkbenchShell>
    </RunSectionNavProvider>
  )
}
```

- [ ] **Step 2: Rebuild `DddLeftNav`'s outer `<aside>` on `WorkbenchRail` (width `w-72`)**

In `frontend/src/components/ddd/DddLeftNav.tsx`:
- Add import: `import { WorkbenchRail } from '@canopy/workbench'`
- Replace the outer `return ( <aside className="flex w-72 …"> … </aside> )` so the two top blocks (the "Narratives" title block and the filter `select`/checkbox block) become the rail `header`, and the `<nav>` becomes the rail children:
```tsx
  const header = (
    <>
      <div className="px-4 py-3">
        <Link to="/ddd" className="text-sm font-semibold text-foreground hover:text-foreground/80">
          Narratives
        </Link>
        <p className="text-[11px] text-muted-foreground">DDD runs, grouped by narrative</p>
      </div>
      <div className="flex flex-col gap-2 border-t border-border px-3 py-2">
        <select
          value={project}
          onChange={(e) => setProject(e.target.value)}
          className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground"
        >
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          Mine only
        </label>
      </div>
    </>
  )

  return (
    <WorkbenchRail width="w-72" header={header}>
      <nav className="px-2 py-2">
        {error && <div className="px-3 py-2 text-xs text-destructive">{error}</div>}
        {!narratives && !error && (
          <div className="px-3 py-2 text-xs text-muted-foreground">Loading…</div>
        )}
        {narratives && narratives.length === 0 && (
          <div className="px-3 py-2 text-xs text-muted-foreground">No narratives yet</div>
        )}
        <div className="flex flex-col gap-1">
          {(narratives ?? []).map((n) => {
            const isActive = n.slug === activeSlug
            return (
              <div key={n.slug}>
                <Link to={`/ddd/${encodeURIComponent(n.slug)}`}>
                  <WorkbenchNavItem active={isActive} count={n.run_count}>
                    {n.slug}
                  </WorkbenchNavItem>
                </Link>
                {isActive && <NarrativeRuns slug={n.slug} activeRunId={activeRunId} />}
              </div>
            )
          })}
        </div>
      </nav>
    </WorkbenchRail>
  )
```
- Add `WorkbenchNavItem` to the `@canopy/workbench` import.
- The nested `NarrativeRuns`, `RunSectionList`, and `FindingsReviewEntry` helpers KEEP their existing markup and scroll-spy logic unchanged (they are DDD's own tree body), BUT swap their raw color classes to semantic tokens in the next step.

- [ ] **Step 3: Token-sweep the DDD tree helpers to semantic tokens**

Within `DddLeftNav.tsx`, in `FindingsReviewEntry`, `RunSectionList`, and `NarrativeRuns`, replace raw classes with semantic equivalents (behavior unchanged):
- `text-stone-500` / `text-stone-600` → `text-muted-foreground`
- `text-stone-400`/`text-stone-300`/`text-stone-200`/`text-stone-100` → `text-foreground` (for the brighter ones) or `text-muted-foreground` (dimmer); keep relative hierarchy by using `text-foreground` for active/labels and `text-muted-foreground` for secondary.
- `text-orange-300` → `text-primary`; `bg-orange-400`/`bg-orange-500/10`/`border-orange-500/30` → `bg-primary`/`bg-primary/10`/`border-primary/30`
- `bg-stone-800/60`/`bg-stone-800/70` → `bg-accent`; `border-stone-800`/`border-stone-800/70` → `border-border`
- `bg-stone-700` (dots) → `bg-muted-foreground`; amber states (`text-amber-300/90`, `bg-amber-400`) MAY stay raw (semantic has no amber) — leave amber as-is.
- `font-mono` and layout classes stay.

Run after editing: `cd frontend && grep -nE "stone-|orange-" src/components/ddd/DddLeftNav.tsx` and confirm only intentional amber (if any) remains.

- [ ] **Step 4: Build + verify**

Run: `cd frontend && npm run build`
Expected: PASSES.

- [ ] **Step 5: Manual scroll-spy + filter check**

Run the dev server (`cd frontend && npm run dev`), open `/ddd/<a narrative>/<a run>`, and confirm: the rail tree renders, the project filter + "Mine only" work, clicking a run section scrolls the package and highlights the active section (scroll-spy), and the active narrative/run rows show the orange-tinted active style.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ddd
git commit -m "refactor(ddd): migrate DDD workbench onto @canopy/workbench (semantic tokens)"
```

---

### Task 7: Publish workflow (deferrable until ace-web adopts)

**Files:**
- Create: `frontend/.npmrc`
- Create: `.github/workflows/publish-workbench.yml`

**Interfaces:** none (CI + registry config). This task may be skipped now and done when ace-web is ready; it does not block Tasks 1–6.

- [ ] **Step 1: Add the registry config**

`frontend/.npmrc`:
```
@canopy:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=${NODE_AUTH_TOKEN}
```

- [ ] **Step 2: Add the publish workflow**

`.github/workflows/publish-workbench.yml`:
```yaml
name: Publish @canopy/workbench
on:
  push:
    tags: ['workbench-v*']
  workflow_dispatch:
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://npm.pkg.github.com'
          scope: '@canopy'
      - run: npm publish
        working-directory: frontend/packages/workbench
        env:
          NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 3: Verify the package contents with a dry run**

Run: `cd frontend/packages/workbench && npm publish --dry-run`
Expected: lists `src/**` files (the `.tsx`/`.ts` sources) and `package.json`; no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/.npmrc .github/workflows/publish-workbench.yml
git commit -m "ci(workbench): add GitHub Packages publish workflow for @canopy/workbench"
```

---

## Self-Review

**Spec coverage:**
- Package at `frontend/packages/workbench/`, `@canopy/workbench`, ships source, `@source`, workspace → Task 1. ✓
- Semantic-token-only, no theme → enforced in every component (Tasks 2–4) + global constraint. ✓
- Zero router/radix/lucide; peers react+clsx+tailwind-merge → Task 1 manifest; asChild via inline `cloneElement` (no radix) in Task 2. ✓
- All 7 primitives (Shell, Main, Rail, NavItem, SubHeader, Pane, state bits) → Tasks 2–4. ✓
- Canopy migration: Agents (Task 5) + DDD (Task 6), incl. delete duplicated chrome, keep scroll-spy/filters/badges, token sweep. ✓
- ace-web deferred → not in any task (non-goal). ✓
- Publish to GitHub Packages on `workbench-v*` → Task 7 (flagged deferrable). ✓
- Acceptance: `npm run build` green per task; pure tests for NavItem/Slot; publish dry-run. ✓

**Placeholder scan:** No TBD/TODO. `WorkbenchNavItem` has a single, complete implementation (Task 2 Step 3). The destructive-foreground token is conditionally added with exact values (Task 4 Step 4 / Task 2 note covers only the destructive note in Task 4). ✓

**Type consistency:** `cn`, `workbenchNavItemClass`/`WorkbenchNavItem`, `WorkbenchShell`/`WorkbenchMain`/`WorkbenchRail`/`WorkbenchPane`, `WorkbenchSubHeader`, `LoadingSpinner`/`EmptyState`/`ErrorState`/`WorkbenchSkeleton` — names match between definitions (Tasks 1–4) and consumers (Tasks 5–6). `WorkbenchMain` forwards `data-ddd-scroll` via `ComponentPropsWithoutRef<'main'>` (used in Task 6). ✓

**Note on `WorkbenchNavItem` usage:** Tasks 5–6 wrap it in a router `Link`/`NavLink` and use the default (non-`asChild`) form (the link is the interactive element). The `asChild` path is shipped/tested-by-build for future callers (e.g. ace-web) but is not on the canopy migration's critical path.
