# canopy-web architecture — the framework/product boundary

> Wave 0 of the framework harvest (`docs/superpowers/specs/2026-06-24-canopy-framework-harvest-design.md`).
> This doc makes the one boundary the whole framework thesis depends on **legible**;
> `tests/test_architecture_boundary.py` makes it **enforced**.

## The one invariant

> **The dependency arrow is one-way: FRAMEWORK code never imports PRODUCT code.
> PRODUCT freely imports FRAMEWORK.**

- **FRAMEWORK** = the generic, *agent-agnostic* substrate any agent could reuse:
  identity, board, command queue, transcripts, auth, timeline, MCP server, API
  plumbing. It knows nothing about what a particular agent *does*.
- **PRODUCT** = canopy's *own* domain features — the self-improvement / DDD /
  skill-authoring / portfolio surface. Another agent would not reuse these; they
  *are* canopy.

The payoff: the blend stays **cuttable**. We never physically split the repo, but
because framework never depends on product, the framework apps could be lifted out
onto a standalone host (or another agent) without dragging canopy's product along.
This is a **direction, not a wall** — we do not move apps into `framework/` vs
`product/` folders (that's the decomposition the design doc forbids); we just hold
the arrow's direction and enforce it in CI.

## The tiers

| App | Tier | What it is |
|---|---|---|
| `agents` | **framework** | Agent workspace: board, command-drain queue, work-products, tasks, *needs-you* inbox. Agent-agnostic. |
| `agent_runs` | **framework** | Unified agent run-lifecycle: run → step → artifact → verdict/QA → decision → gate → fork, as a storage-agnostic read model behind a `RunStore` Protocol (DB adapter persists rows; Drive adapter reads ACE's YAML). FK's `agents.Agent`; imports no product app. |
| `workspaces` | **framework** | Multi-tenancy: `Workspace` + members (owner/editor/viewer) + email invites (ported from ace-web, domain-agnostic — no Drive coupling). The tenant that owns agents + runs. Distinct from the retired co-authoring app that used to be `apps/workspace` (singular). |
| `api` | **framework** (composition root) | The single NinjaAPI that wires every app's router. The one seam allowed to import all apps. |
| `common` | **framework** | Shared infra: anthropic client, auth flow, middleware, auth-domains. |
| `timeline` | **framework** | Generic activity-log aggregation; reads other apps' events via a string registry (no hard product imports). |
| `tokens` | **framework** | Personal Access Token management + bearer auth. |
| `sessions` | **framework** | Session/transcript storage + sharing. |
| `issues` | **framework** | GitHub issue provenance / evidence capture. |
| `mcp` | **framework** | MCP server infra + audit + rate-limit. (Individual *tools* may be product — see carve-outs.) |
| `system` | **framework** | System metadata / AI-backend status. |
| `projects` | **product** | Canopy's portfolio/insights feature: repos + which canopy skills ran (`skills[]`, `skill_name`, hygiene-skill frontend). Not a generic registry today — promote to framework only when a real second consumer needs one. |
| `collections` | **product** | DDD source collections. |
| `skills` | **product** | Canopy skill registry. |
| `evals` | **product** | Eval suites tied to skills. |
| `walkthroughs` | **product** | DDD walkthrough artifacts (HTML/video demos). |
| `reviews` | **product** | DDD narrative review surface. |
| `shareouts` | **product** | Team shareout briefings. |
| `runs` | **product** | DDD run aggregation/versioning. |

## Accepted seams (carve-outs)

The boundary holds everywhere except these documented, intentional places:

1. **`apps/api` — the composition root.** One NinjaAPI imports every router; a
   framework needs exactly one such wiring seam. Exempt by design.
2. **`apps/mcp/tools/insights.py` — a product MCP tool on the framework server.**
   `apps/mcp/server.py` registers tools by importing `apps.mcp.tools` as a side
   effect; the `insights` tool exposes the `projects` (portfolio) product. Same
   composition-root shape as the api hub. **Candidate for inversion** later
   (let `projects` register its own tool via `AppConfig.ready`), which would
   remove this carve-out.

`seed_demo` (demo-data seeder) used to live in framework `apps/common` and import
product models — it now lives in `apps/workspace` (product), so the import is
product→product. The command name is unchanged (`manage.py seed_demo`).

## Enforcement

`tests/test_architecture_boundary.py` (pure stdlib `ast`, runs in the normal
`uv run pytest` CI job) parses every framework app and fails if any non-test file
imports a product app, except the carve-outs above. It also fails if a **new** app
isn't classified into a tier here — so the boundary can't silently rot.

Adding a new app? Put it in `FRAMEWORK` or `PRODUCT` in both this doc and that
test. Need framework code to touch product? Don't — move the code to a product
app, or (rarely) add a justified carve-out here and in the test.
