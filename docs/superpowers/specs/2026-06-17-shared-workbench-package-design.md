# `@canopy/workbench` — a shared two-pane Workbench primitive set

**Date:** 2026-06-17
**Status:** Shipped (PRs #123 / #124) — historical record, not current-state
**Supersedes scope of:** GitHub #122 (extract a shared Workbench shell; migrate DDD + Agents onto it) — this design folds #122 into a cross-repo package rather than an in-repo `components/workbench/` directory.

## Context

Two canopy-web surfaces already share a full-bleed two-column "workbench" layout
(fixed left rail + independently-scrolling main):

- **DDD** — `components/ddd/DddShell.tsx` + `DddLeftNav.tsx` (rail = hierarchical
  narratives → versions → runs, with filters + scroll-spy).
- **Agents** — `pages/AgentWorkspacePage.tsx` + `components/agents/AgentLeftNav.tsx`
  (rail = flat section nav with count badges), added in #119 / #121.

The Agents shell was built by **mirroring** the DDD shell, so the chrome is
duplicated within canopy-web. Separately, **ace-web** has its own, more developed
workbench (`pages/OppWorkbenchPage.tsx` + `components/opps/WorkbenchHeader.tsx`,
`OppSidebar.tsx`, plus a step-detail pane and an embedded chat pane) — a top header
bar over a four-pane body.

Both repos are the same stack (Vite + React 19 + Tailwind v4 + shadcn) and — crucially
— **both already define the identical semantic shadcn token contract** (`@theme inline`
+ `:root` with `--background`, `--card`, `--border`, `--primary`, `--muted-foreground`,
`--destructive`, `--ring`, …). They differ only in values: canopy maps them to
stone/orange, ace-web to neutral grays. The "design-token unification" that #122 flagged
as a prerequisite is therefore already ~done at the token-definition layer. The only gap
is that canopy's *components* still hardcode raw `stone-*`/`orange-*` utility classes
instead of the semantic ones; ace-web's components already use semantic tokens.

## Goal

A single source-of-truth package — **`@canopy/workbench`** — that owns the generic
workbench *chrome* (shell scaffold, header bar, rail, nav item, sub-header, side pane,
and load/empty/error/skeleton states). The package emits **semantic class names only**
and ships **no theme of its own**, so it renders correctly in whatever palette the
consuming app defines. canopy-web consumes it now (migrating DDD + Agents onto it);
ace-web adopts it in a later pass.

### Non-goals

- **No ace-web migration in this unit of work.** The package is published and ready;
  ace-web swaps its three shell files (`OppWorkbenchPage`, `WorkbenchHeader`,
  `OppSidebar`) onto it later. (Decision: user is still iterating on ace-web.)
- **No domain components in the package.** ACE's `ChatPanel`, `StepDetailPane`,
  `SkillList`/`SkillRow`, `RunSelector`, and dialogs are coupled to sessions/runs/judge
  types and stay in ace-web. DDD's narrative tree + scroll-spy + filters and Agents'
  section list stay in canopy-web. They *compose* the package primitives; they don't
  enter it. (Decision: "chrome-only" boundary.)
- **No monorepo.** The two repos stay separate; sharing is via a published package.

## Distribution & build

- **Location:** `frontend/packages/workbench/` inside the canopy-web repo, with its own
  `package.json` (`"name": "@canopy/workbench"`). Placing it under `frontend/` (rather
  than repo root) keeps the existing `./deploy.sh` / CI flow — which `cd`s into
  `frontend/` — working unchanged.
- **Workspace wiring:** add `"workspaces": ["packages/*"]` to `frontend/package.json`;
  the canopy frontend app adds `"@canopy/workbench": "*"` as a dependency. npm resolves
  it to the local workspace, so edits to the package are live during `npm run dev` with
  no rebuild/republish step.
- **Ships TypeScript source, not a bundled build.** Both consumers are Tailwind v4 +
  the same shadcn config. The package exports `.tsx` from `src/`; each consumer adds
  `@source "../packages/workbench/src"` (canopy) / `@source ".../@canopy/workbench/src"`
  (ace-web) to its CSS entry so Tailwind scans the package source for class names. This
  is what lets the package stay theme-free: the class names resolve against whichever
  app's token values are in scope. No `tsup`/`vite build` library step, no CSS artifact.
- **Publishing:** GitHub Packages under the `@canopy` scope. A CI workflow publishes on
  a version tag (`workbench-v*`). `package.json` carries `"publishConfig": { "registry":
  "https://npm.pkg.github.com" }`; both repos get an `.npmrc` pointing `@canopy:registry`
  at GitHub Packages with a `GITHUB_TOKEN`/PAT. ace-web installs the published version
  (it can't use the workspace).
- **Peer dependencies:** `react`, `react-dom`, `clsx`, `tailwind-merge`. **No**
  `react-router-dom` (canopy is on v7, ACE differs — the package stays router-agnostic;
  see `WorkbenchNavItem`). **No** `lucide-react` (chrome needs no icons; icons live in
  app-supplied action slots). **No** `@radix-ui/react-slot` (neither repo has it — the
  package ships its own ~10-line `Slot`).
- The package ships its own `cn()` (clsx + tailwind-merge), mirroring each repo's
  `lib/utils.ts`, so consumers don't have to wire one in.

## Public API

All components are presentational and composable. Exported from the package root.

### `WorkbenchShell`
The full-bleed outer scaffold.
```ts
interface WorkbenchShellProps {
  header?: ReactNode      // optional top bar (ace-web uses it; canopy doesn't yet)
  children: ReactNode     // the body row: rail + main + optional side panes
  className?: string
}
```
Renders:
```tsx
<div className={cn("flex h-full flex-col bg-background text-foreground", className)}>
  {header}
  <div className="flex flex-1 overflow-hidden">{children}</div>
</div>
```
The caller composes the body (`<WorkbenchRail/>`, `<WorkbenchMain/>`, `<WorkbenchPane/>`).
To support DDD's scroll-spy, the caller is free to wrap `<WorkbenchShell>` in its own
provider (e.g. `RunSectionNavProvider`) — the provider never enters the package.

### `WorkbenchMain`
The scrolling main column. Forwards a ref and arbitrary props so DDD can mark it as the
scroll-spy root (`data-ddd-scroll`).
```ts
interface WorkbenchMainProps extends ComponentPropsWithoutRef<"main"> {
  children: ReactNode
}
// <main ref className="flex-1 overflow-y-auto" {...rest}>{children}</main>
```

### `WorkbenchRail`
The bordered `<aside>` chrome. Takes **arbitrary children** as its scrollable body, so
DDD renders its tree and Agents its flat list.
```ts
interface WorkbenchRailProps {
  width?: string          // tailwind width class; default "w-64" (Agents); DDD passes "w-72"
  header?: ReactNode      // identity / title / back-link / filters block
  children: ReactNode     // scrollable body
  className?: string
}
```
Renders a `flex shrink-0 flex-col border-r border-border bg-background` aside; `header`
sits in a `border-b border-border` wrapper above a `flex-1 overflow-y-auto` body. Inner
padding is the caller's (passed inside `header`/`children`) so each surface keeps its
own spacing.

### `WorkbenchNavItem`
A single rail entry: label + optional right-aligned count badge + active state. The
shared active style is the orange-tinted treatment from canopy's `GuidePage`/`AgentLeftNav`
expressed semantically (`bg-primary/10 border-primary/30 text-primary` active;
`text-muted-foreground hover:bg-accent hover:text-foreground` rest).

Router-agnostic via an internal `asChild` Slot (the consumer supplies its own
`Link`/`NavLink`/`button`):
```ts
interface WorkbenchNavItemProps {
  active?: boolean
  count?: number
  asChild?: boolean       // when true, merges styling onto the single child element
  children: ReactNode
}
```
Usage:
```tsx
<WorkbenchNavItem asChild active={isActive} count={agent.task_count}>
  <NavLink to="tasks">Tasks</NavLink>
</WorkbenchNavItem>
```
The Slot is a ~10-line `cloneElement` that merges the computed `className` onto the child
(prepending, then `cn()`-merged). Without `asChild`, it renders a styled `<div>`.

### `WorkbenchSubHeader`
The per-section bar inside the main area: title + optional count + optional right-aligned
action. Seeded from canopy's `SectionSubHeader`, semantic tokens.
```ts
interface WorkbenchSubHeaderProps {
  title: string
  count?: number
  action?: ReactNode
}
```

### `WorkbenchPane`
A generic bordered side panel wrapper (ace-web's step-detail / chat `<section>`s).
```ts
interface WorkbenchPaneProps {
  width?: string          // e.g. "w-[320px]"
  side?: "left" | "right" // border-l (default) vs border-r
  children: ReactNode
  className?: string
}
```

### State primitives
Merged from ace-web's `LoadingStates` + canopy's `SectionSkeleton`, semantic tokens
(notably `ErrorState` moves off raw `red-*` onto `border-destructive/30
bg-destructive/10 text-destructive`):
```ts
function LoadingSpinner(props: { label?: string }): JSX.Element
function EmptyState(props: { title: string; description?: string; action?: ReactNode }): JSX.Element
function ErrorState(props: { title?: string; message: string; onRetry?: () => void }): JSX.Element
function WorkbenchSkeleton(props: { rows?: number }): JSX.Element   // card-placeholder rows
```

## canopy-web migration (this unit of work)

1. **Scaffold the package** at `frontend/packages/workbench/` with the API above, seeded
   from ace-web's implementations (its more-developed chrome) generalized to slots +
   semantic tokens. Add workspace wiring, `.npmrc`, and `@source`.
2. **Agents** →
   - `AgentWorkspacePage` composes `WorkbenchShell` + `WorkbenchRail` + `WorkbenchMain`
     (keeps its `getAgent` load + `<Outlet/>`).
   - `AgentLeftNav` rebuilt on `WorkbenchRail` + `WorkbenchNavItem` (identity header +
     the five section links with count badges).
   - `components/agents/SectionSubHeader.tsx` → `WorkbenchSubHeader`; `SectionSkeleton`
     → `WorkbenchSkeleton`. Update the five `pages/agents/*Section.tsx` imports.
3. **DDD** →
   - `DddShell` composes `WorkbenchShell` + `WorkbenchMain` (still wrapped in
     `RunSectionNavProvider`; `WorkbenchMain` carries `data-ddd-scroll`).
   - `DddLeftNav` rebuilt on `WorkbenchRail` (its filter/header block in the rail
     `header` slot; its narrative tree as rail children) + `WorkbenchNavItem` for the
     narrative/version/run rows, preserving hierarchy, filters, and scroll-spy.
4. **Token sweep:** the touched canopy components flip raw `stone-*`/`orange-*` to
   semantic tokens where they now live behind the package; remaining app-side markup may
   stay raw (out of scope to convert wholesale).
5. **Delete** the duplicated shell markup so nothing remains shared between
   `components/ddd/` and `components/agents/`.

## Testing & acceptance

- `cd frontend && npm run build` passes (tsc + vite) with the workspace package resolved.
- DDD keeps its tree, filters, and scroll-spy; Agents keeps its sections + count badges
  (verified in the browser).
- No duplicated shell markup remains between `components/ddd/` and `components/agents/`.
- The package builds/type-checks standalone (`tsc --noEmit` in `packages/workbench`).
- Vitest unit tests for `WorkbenchNavItem` (active/inactive class, count badge,
  `asChild` className merge) and the `Slot` (merges className onto the child element).
- A publish dry-run (`npm publish --dry-run`) confirms the package contents.

## Risks & mitigations

- **Tailwind v4 `@source` on a workspace path.** Class names only emit if Tailwind scans
  the package source. Mitigation: explicit `@source` directive in canopy's CSS entry,
  verified by a visual check that semantic classes render (not just type-check).
- **GitHub Packages auth.** ace-web (later) and CI need an `.npmrc` with a token scoped to
  `read:packages`/`write:packages`. Mitigation: document in both repos' READMEs; CI uses
  `GITHUB_TOKEN`.
- **Slight visual drift in DDD/Agents rail tint** (raw `stone-950/40` → semantic
  `bg-background`). Acceptable per #122 ("DDD … refactor it freely"); Agents is new.
- **Version skew once ace-web consumes it.** Mitigation: semver + a CHANGELOG in the
  package; ace-web pins a version and bumps deliberately.

## Open questions

None blocking. (`@canopy` scope name, `workbench-v*` tag convention, and the
`frontend/packages/` location are all chosen above and can be revised in implementation
if a constraint surfaces.)
