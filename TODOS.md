# TODOS

## Canopy-Web Platform

### Proactive Conversation Detection

**What:** Monitor Slack channels and open claw sessions for conversations that contain reusable approaches. Surface as suggestions in the web UI.

**Why:** Transforms the product from "tool you visit" to "system that works for you." Solves the behavior change problem — non-technical users won't paste conversations, but they'll click a suggestion.

**Context:** Deferred from CEO review Expansion 1. Requires Slack API OAuth, background analysis job, notification system. This is the V2 flywheel that creates network effects. Should ship after V1 workspace is validated with real users (Neal test passes). False positive filtering is critical — annoying suggestions erode trust faster than missing suggestions.

**Effort:** M (human) → S with CC
**Priority:** P1
**Depends on:** V1 workspace validated with real users

### MCP Layer for AI Session Auto-Submit

**What:** Expose the canopy-web API as MCP tools so Claude Code, open claws, and canopy can interface programmatically.

**Why:** Closes the loop — successful AI sessions can automatically submit themselves for extraction without human intervention. Key tools: create_collection, suggest_skill, run_skill, run_eval, report_success.

**Context:** Deferred from CEO review. The API facade already exists; MCP is a thin adapter over it. Follow Scout's FastMCP standalone process pattern. This enables canopy's existing automation to feed the skill extraction system, creating a self-improving ecosystem.

**Effort:** S-M (human) → S with CC
**Priority:** P1
**Depends on:** V1 API being stable

### Prompt Injection Hardening

**What:** Add input sanitization and prompt separation for source content before LLM calls.

**Why:** Source content (Slack threads, transcripts) goes directly into LLM prompts. Currently trusted (internal tool), but must be hardened before any external use.

**Context:** Identified in CEO review Section 3 (Security). V1 accepts risk (single-tenant, trusted users). For V2 or external use: separate user-provided content from system instructions using Claude's message role separation, validate/sanitize inputs, add content length limits.

**Effort:** S (human) → S with CC
**Priority:** P2
**Depends on:** None — can do anytime before external exposure

### Slack API OAuth Integration

**What:** Auto-fetch Slack thread content by URL instead of requiring manual paste.

**Why:** Reduces friction for the most common source type. Currently V1 requires copy-pasting thread text.

**Context:** Deferred from V1 scope. Requires Slack workspace OAuth flow, thread content fetching, handling private channels/permissions. The existing Slack agents can already call the API — this is about the web UI being able to fetch threads directly.

**Effort:** S-M (human) → S with CC
**Priority:** P2
**Depends on:** V1 workspace validated

### Google Docs API Integration

**What:** Auto-fetch Google Doc content by URL instead of requiring manual paste.

**Why:** Google Docs are a common source type (e.g., Eva's CRISPR analysis document).

**Context:** Deferred from V1 scope. Requires Google OAuth flow or service account, Docs API content fetching, handling permissions.

**Effort:** S (human) → S with CC
**Priority:** P3
**Depends on:** V1 workspace validated

### Multi-Tenant Auth

**What:** Add user authentication and multi-tenant support to the platform.

**Why:** Required if the tool is shared beyond the immediate team or if multiple teams use it independently.

**Context:** V1 is single-tenant, no auth (internal tool). When adoption grows, need: user accounts, team/org scoping, skill visibility controls (private/team/org), audit logging of who created/modified skills.

**Effort:** M (human) → S with CC
**Priority:** P3
**Depends on:** V1 adoption growing beyond immediate team

### Cowork Runtime Adapter

**What:** Build a runtime adapter for the cowork environment.

**Why:** Extends skill portability to the cowork platform.

**Context:** Deferred pending cowork API spec/documentation. The skill schema already has a placeholder for cowork (type: task_sequence). Implementation depends on understanding cowork's execution model.

**Effort:** S (human) → S with CC
**Priority:** P3
**Depends on:** Cowork API documentation available

## Completed
