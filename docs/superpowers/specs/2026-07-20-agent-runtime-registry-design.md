# Agent Runtime Registry — declarative agent environments

**Status:** Draft for review · **Date:** 2026-07-20 · **Author:** Jonathan + Claude

> A system that defines **what an agent needs to run in a running environment** —
> declaratively — so *any* environment (a laptop, a cloud runner, a fresh box) can
> provision the correct runtime for whichever agent's turn it's executing, and know
> whether it's already ready. It generalizes SP4 (ace-web on the cloud runner) into
> the fleet-wide problem: every agent has runtime prerequisites, and today those are
> a pile of imperative, laptop-only setup scripts.

## The problem
Every agent has a runtime dependency set: the **canopy** framework plugin (all), the
**ace** plugin (many), its **own** plugin (echo/ada/hal/eva are each a
`.claude-plugin`), plus secrets (1Password AI-Agents vault), MCP servers, tools, and
interactive OAuth (`claude setup-token`, `gog login`). Today this is defined
**imperatively and laptop-only** — a bespoke `bin/<agent>_setup.py` per agent that
pulls secrets and wires clients, ending in a `_preflight.py` check. To run agents in
a cloud running environment (the cloud runner), that has to become **declarative**.

## Architecture: a registry + a reconciler
Two concepts, plus a clean split of *where each kind of data lives*.

- **The runtime spec** declares an agent's *desired* runtime: plugins, secrets (by
  reference), MCP servers, tools, engine support/preference, env/capabilities, and
  the preflight that defines "ready."
- **The reconciler** (one canopy-owned tool) does **not** assume cold start. It
  **scans the current environment, diffs it against the spec, applies only the
  gaps, then runs the preflight.** Idempotent. A warm box (or your laptop with
  emdash) reconciles to a near-no-op → "ready" → straight into the turn. A cold box
  gets fully provisioned. Persistence is a property of the **box**, not the model.
- **Readiness gate:** before a turn, the runner reconciles against the target
  agent's spec; a gap it can't self-satisfy (interactive OAuth) surfaces as a
  first-class **"needs bootstrap"** state rather than a half-provisioned run.

### Two axes (both read from the agent's spec)
1. **Runtime** — the agent's deps (mostly engine-agnostic).
2. **Execution engine** — *how* the turn is driven: **emdash/CDP** (laptop,
   interactive, watchable) vs. **cloud-p / `claude -p`** (headless, autonomous).
   `canopy_runner.config.executor` already treats this as a variable. Engine
   **preference is per-agent** (in the agent's spec); the reconciler must bring the
   box to readiness for whichever engine is selected.

## Where each thing lives (by the *nature* of the data)
- **In the agent's repo** (versioned, non-secret — the agent's *self-declaration*):
  the runtime spec — `runtime.yaml` (or an extension of `.claude-plugin`/`.canopy/`).
  "I depend on canopy + ace + my own plugin, these MCP servers, these tools, I run
  on cloud-p, here's my preflight." Reviewed in the agent's own PRs, like a
  `package.json`/`Dockerfile`. **Never contains secret values.**
- **In canopy-web** (the registry/hub — the *entry point + what can't be in the
  repo*): the `Agent` record gains a **repo pointer** (URL + ref), **secret
  references** (names, never values), tenancy (already there), and any genuinely
  deployment-level preference. A runner asks canopy-web "how do I run agent X?" and
  gets: its repo, which secrets to resolve, its tenant.
- **In the secret store** (never repo, never canopy-web as plaintext): the actual
  values, resolved by the reconciler *from the reference*. **1Password is the
  single source of truth for laptop AND cloud** — see "Secret architecture" below.
  The one bootstrap secret on a cloud box is the 1Password **service-account
  token**, which lives in AWS Secrets Manager; everything else flows from 1Password
  (no per-secret copying — the friction that stranded the first cloud runner).

### Reconciler flow
```
canopy-web  ── GET /api/agents/{slug}/runtime ──▶  repo pointer + secret refs + tenant + engine
   │
   ▼  clone/read the repo's runtime.yaml (the declarative WHAT)
   ▼  resolve secret refs from the env's store (1Password | Secrets Manager)
   ▼  scan the box → diff vs. spec → apply only the gaps
   ▼  run the preflight
   └▶ ready → run the turn on the selected engine     |     gap needs a human → "needs bootstrap"
```

## Secret architecture (decided — RS2)
1Password is the **single source of truth**, resolved identically on a laptop and a
cloud box. This is 1Password's own recommended pattern for AI agents (service
account + SDK + per-task vault, GA as of 2026; their roadmap "Unified Access Pro"
runtime-issuance is *not* GA and we deliberately don't build on it yet).

**Two-tier vault topology** (matches "dedicated vault per task, least privilege"):
- `Canopy-Shared` — secrets every canopy agent needs.
- `Agent-<Slug>` — one per agent: its own identity + integration secrets
  (`canopy-pat`, `claude-oauth-token`, `gog-token`, …).

**Resolution:** `runtime.yaml` carries only reference *names* (`secrets: [canopy-pat,
gog-token]`). The reconciler resolves each against `[Agent-<Slug>, Canopy-Shared]`
in order (agent vault shadows shared), via the 1Password SDK
(`secrets.resolve("op://<vault>/<item>/<field>")`). The repo never names a vault —
the topology is convention, not config.

**Access + portability:**
- Laptop and cloud both authenticate a **service account** (`OP_SERVICE_ACCOUNT_TOKEN`)
  and resolve the *same* `op://Agent-<Slug>/…` refs — one mechanism, no laptop-only
  branch. Validating it on the laptop validates the production path.
- On a cloud box the token is the **single** value in AWS Secrets Manager
  (`canopy/cloud-runner/op-service-account-token`; the EC2 role already reads
  `canopy/cloud-runner/*`). A box's token is scoped to exactly the vaults for the
  agents it may run — the runner's `RUNNER_AGENTS` caps *become* vault grants.
- **The reconciler holds the token, never the model** — it resolves secrets into the
  engine's process env/files *before* the turn, matching 1Password's "don't expose
  raw credentials to the model."

**Write-back (cold-box zero-touch):** the SDK does full item CRUD, so the reconciler
persists a freshly-minted `claude setup-token` back into `Agent-<Slug>` (the agent
vault grant is `read_items,write_items`). A cold box thus provisions itself from the
vault instead of prompting; only a *never-yet-minted* interactive cred surfaces as
"needs bootstrap". (1Password *Environments* are read-only, so they cover the read
set but not this write path — hence the SDK, not `op run`, is the resolution engine.)

**Bootstrap:** `deploy/secrets/bootstrap_1password.sh <slug…>` idempotently creates
the vaults + placeholder items and prints the owner-only `op service-account create`
command (grants) + the `aws secretsmanager put-secret-value` follow-up. The operator
runs it so the token never transits the assistant unless they choose.

**Caution:** service accounts carry API rate limits (fine for a small fleet resolving
a few secrets/turn); a self-hosted 1Password **Connect** server is the caching escape
hatch if the fleet ever outgrows them. Service accounts require a Business plan.

## Runner execution model (decided — RS3)
Three credential tiers, by *who owns the credential*:

- **Runner-owned — the AI/Claude "cloud login".** One login per runner
  environment, owned by and accountable to the **runner**, shared across every
  agent and every user who fires a turn on it. The runner daemon injects
  `CLAUDE_CODE_OAUTH_TOKEN` when it launches `claude`; the agent brings its
  identity, never its AI subscription. Use a **long-lived `setup-token`** (not a
  rotating blob) so concurrent agents share it with no refresh/write-back
  machinery. On the cloud box it lives in the runner's secret store (AWS Secrets
  Manager); the daemon reads it once and injects per-launch.
- **Agent-owned — identity secrets** (`Agent-<Slug>`): gmail, gog, canopy-pat.
  Resolved by the reconciler into the agent's provisioned HOME.
- **User-owned — per-operator secrets** (e.g. chrome-sales Salesforce creds, which
  act on behalf of the logged-in human). NOT in the agent vault; resolved from the
  dispatching user's context. (Resolution path is future work.)

**This supersedes the ace-web per-user CLI-credential port.** ace-web uploaded a
*different user's* Claude blob per chat and ran it server-side with a staged HOME +
single-use-refresh write-back. With one runner-owned login for everyone, that whole
machinery (`UserCredential`, blob upload, staged HOME, `_persist_refreshed_blob`) is
unnecessary. canopy-web keeps the **chat infrastructure** already ported (SP1–3:
realtime tail + sessions/messages/participants/presence); only the stubbed executor
becomes real over the runner.

**Isolation on a shared runner: one EC2, one Unix user per agent.** The runner
daemon (privileged) claims a turn → ensures the agent's Unix user exists → runs the
reconciler **as that user** (provisioning `/home/<agent>` from `Agent-<Slug>`,
warm-aware) → launches `claude -p` **as that user** with `HOME=/home/<agent>` and the
runner's `CLAUDE_CODE_OAUTH_TOKEN` injected → streams the transcript into the chat
session. Per-agent Unix users (not just per-HOME dirs) so one agent's gog/plugin/
identity files can't collide with or be read by another's, with clean attribution.
One EC2 hosts the whole fleet; scale to a second instance only on concurrent load,
never for isolation. Heavier container-per-agent is deferred until an agent runs
untrusted code.

## Decomposition (each its own spec → plan → build)
```
RS1  Runtime-spec model + discovery API (canopy-web)  the Agent gains repo pointer + secret refs +
                                                      engine pref; GET …/runtime serves it. Define the
                                                      runtime.yaml schema (a canopy schema module + an
                                                      example agent runtime.yaml). FOUNDATION.
RS2  The reconciler (canopy-owned lib)                scan → diff → apply → preflight; warm-aware;
                                                      "needs bootstrap" gaps; OnePasswordStore
                                                      (resolve + persist) — see "Secret architecture".
RS3  Cloud runner consumes it                         the EC2 cloud runner fetches the agent spec +
                                                      reconciles before running (replaces today's
                                                      hardcoded RUNNER_PROJECTS/caps + the manual token).
RS4  Engine axis                                      runners declare engine(s); routing honors the
                                                      agent's engine preference (emdash vs cloud-p).
RS5  Migrate laptop setup onto it                     bin/<agent>_setup.py become thin reconciler
                                                      callers — the "one source of truth" payoff.
SP4  ace-web as first consumer                        ACE's runtime.yaml → a cloud runner reconciles
                                                      ACE's runtime → runs ACE turns; ace-web enqueues.
```
**Sequencing:** RS1 → RS2+RS3 → RS4 → RS5 → SP4.

## RS1 — the foundation (this slice)
canopy-web becomes the registry entry point.

- **`agents.Agent` gains:** `repo_url` (str), `repo_ref` (str, default `main`),
  `runtime_engine` (`emdash` | `cloud_p` | `any`, default `any`), `runtime_secrets`
  (JSON list of secret-reference names, never values). Migration; all nullable/empty
  so existing agents are unaffected.
- **Discovery endpoint:** `GET /api/agents/{slug}/runtime` → `AgentRuntimeOut`
  (`repo_url`, `repo_ref`, `engine`, `secret_refs`, `workspace`). Session/PAT authed
  (runners use a PAT), tenant-gated exactly like the other agent reads.
- **The `runtime.yaml` schema** — a Pydantic model in a small `canopy_runtime`
  library (Django-free, installable, so the reconciler can import it without Django),
  validating: `plugins[]` (name + source), `mcp[]`, `tools[]`, `engine`,
  `secrets[]` (references), `preflight[]` (check descriptors). Plus an example
  `runtime.yaml` documenting the shape. canopy-web does **not** parse it (the runner
  reads it from the repo); RS1 just *defines and validates* it.

Out of scope for RS1: the reconciler itself (RS2), any runner change (RS3), engine
routing (RS4), laptop migration (RS5).

## Non-goals / YAGNI
- Not a general package manager — it declares a fixed, small set (plugins, mcp,
  tools, secrets, engine, preflight) that covers the fleet, not arbitrary provisioning.
- Not moving agent *code* into canopy-web — the agent's brain stays in its repo; the
  registry only knows *where/who* + serves the non-repo, non-secret bits.
- The framework/product boundary holds: `agents` is framework; the registry data +
  API + `canopy_runtime` schema are all agent-agnostic substrate.
