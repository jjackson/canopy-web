# Portfolio Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cross-portfolio insights feed to canopy-web — an `/insights` page showing actionable AI observations across all projects, plus the API to power it and a canopy skill to generate insights.

**Architecture:** Insights are stored as `ProjectContext` entries with `context_type: "insight"` (model already exists). New cross-project API endpoint aggregates insights across all projects. New React page renders them as actionable cards with category badges, evidence, and project links. New canopy skill generates insights by reading workbench API + GitHub data per project.

**Tech Stack:** Django 5, DRF, React 19, Tailwind CSS 4, Framer Motion, TypeScript

---

## File Structure

**Backend (new files):**
- `apps/projects/views_insights.py` — Cross-project insights API endpoint (separate file to keep views.py focused)

**Backend (modified files):**
- `apps/projects/urls.py` — Add insights route
- `apps/projects/serializers.py` — Add InsightSerializer with project slug

**Frontend (new files):**
- `frontend/src/pages/InsightsPage.tsx` — Insights feed page
- `frontend/src/api/insights.ts` — API client for insights

**Frontend (modified files):**
- `frontend/src/router.tsx` — Add `/insights` route
- `frontend/src/components/AppLayout/AppLayout.tsx` — Add Insights to nav

**Canopy skill (new files):**
- `~/emdash-projects/canopy/plugins/canopy/skills/portfolio-review/SKILL.md` — The intelligence

**Tests (modified files):**
- `tests/test_projects.py` — Add insight API tests

**Docs (modified files):**
- `CLAUDE.md` — Add insights endpoint and route

---

### Task 1: Insights API Endpoint

**Files:**
- Create: `apps/projects/views_insights.py`
- Modify: `apps/projects/serializers.py`
- Modify: `apps/projects/urls.py`
- Modify: `tests/test_projects.py`

- [ ] **Step 1: Write the tests**

Append to `tests/test_projects.py`:

```python
class TestInsightsAPI:
    def test_list_insights_empty(self, client, db):
        response = client.get("/api/insights/")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_list_insights_returns_only_insights(self, client, project):
        ProjectContext.objects.create(
            project=project, context_type="insight",
            content="ace-web has 6 commits since last deploy",
            source="canopy:portfolio-review",
        )
        ProjectContext.objects.create(
            project=project, context_type="summary",
            content="This is a summary, not an insight",
            source="canopy:activity-summary",
        )
        response = client.get("/api/insights/")
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["context_type"] == "insight"
        assert body["data"][0]["project_slug"] == "canopy-web"

    def test_list_insights_across_projects(self, client, db):
        p1 = Project.objects.create(name="alpha", slug="alpha")
        p2 = Project.objects.create(name="beta", slug="beta")
        ProjectContext.objects.create(
            project=p1, context_type="insight",
            content="Insight for alpha", source="canopy:portfolio-review",
        )
        ProjectContext.objects.create(
            project=p2, context_type="insight",
            content="Insight for beta", source="canopy:portfolio-review",
        )
        response = client.get("/api/insights/")
        body = response.json()
        assert len(body["data"]) == 2
        slugs = {i["project_slug"] for i in body["data"]}
        assert slugs == {"alpha", "beta"}

    def test_list_insights_ordered_newest_first(self, client, project):
        ProjectContext.objects.create(
            project=project, context_type="insight",
            content="First", source="test",
        )
        ProjectContext.objects.create(
            project=project, context_type="insight",
            content="Second", source="test",
        )
        response = client.get("/api/insights/")
        body = response.json()
        assert body["data"][0]["content"] == "Second"

    def test_list_insights_filter_by_category(self, client, project):
        ProjectContext.objects.create(
            project=project, context_type="insight",
            content="[ship_gap] ace-web behind",
            source="canopy:portfolio-review",
        )
        ProjectContext.objects.create(
            project=project, context_type="insight",
            content="[hygiene] doc-regen overdue",
            source="canopy:portfolio-review",
        )
        response = client.get("/api/insights/?category=ship_gap")
        body = response.json()
        assert len(body["data"]) == 1
        assert "ship_gap" in body["data"][0]["content"]

    def test_list_insights_limit(self, client, project):
        for i in range(30):
            ProjectContext.objects.create(
                project=project, context_type="insight",
                content=f"Insight {i}", source="test",
            )
        response = client.get("/api/insights/")
        body = response.json()
        assert len(body["data"]) == 20  # default limit

    def test_dismiss_insight(self, client, project):
        ctx = ProjectContext.objects.create(
            project=project, context_type="insight",
            content="Dismissable", source="test",
        )
        response = client.delete(f"/api/insights/{ctx.id}/")
        assert response.status_code == 200
        assert ProjectContext.objects.filter(id=ctx.id).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_projects.py::TestInsightsAPI -v`
Expected: FAIL — 404 (no URL route)

- [ ] **Step 3: Add InsightSerializer**

Add to `apps/projects/serializers.py`:

```python
class InsightSerializer(serializers.ModelSerializer):
    project_slug = serializers.CharField(source="project.slug", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = ProjectContext
        fields = ["id", "project_slug", "project_name", "context_type", "content", "source", "created_at"]
```

- [ ] **Step 4: Create views_insights.py**

Create `apps/projects/views_insights.py`:

```python
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .models import ProjectContext
from .serializers import InsightSerializer


@api_view(["GET"])
def insights_list(request):
    """List all insights across all projects, newest first."""
    start_timing()

    insights = ProjectContext.objects.filter(
        context_type="insight"
    ).select_related("project").order_by("-created_at")

    category = request.query_params.get("category")
    if category:
        insights = insights.filter(content__startswith=f"[{category}]")

    limit = int(request.query_params.get("limit", 20))
    limit = min(limit, 100)

    serializer = InsightSerializer(insights[:limit], many=True)
    return Response(success_response(serializer.data))


@api_view(["DELETE"])
def insight_dismiss(request, pk):
    """Dismiss (delete) an insight."""
    start_timing()

    try:
        insight = ProjectContext.objects.get(pk=pk, context_type="insight")
    except ProjectContext.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Insight not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    insight.delete()
    return Response(success_response({"dismissed": pk}))
```

- [ ] **Step 5: Wire URLs**

Add to `apps/projects/urls.py`:

```python
from . import views_insights
```

And add these paths (BEFORE the slug-based routes):

```python
path("../insights/", views_insights.insights_list, name="insights-list"),
path("../insights/<int:pk>/", views_insights.insight_dismiss, name="insight-dismiss"),
```

Wait — insights are cross-project, so they should be at `/api/insights/`, not under `/api/projects/`. Add them directly to `config/urls.py` instead:

```python
from apps.projects import views_insights

# Add before the projects include:
path("api/insights/", views_insights.insights_list, name="insights-list"),
path("api/insights/<int:pk>/", views_insights.insight_dismiss, name="insight-dismiss"),
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_projects.py::TestInsightsAPI -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add apps/projects/views_insights.py apps/projects/serializers.py config/urls.py tests/test_projects.py
git commit -m "feat(insights): cross-project insights API endpoint"
```

---

### Task 2: Frontend Insights API Client

**Files:**
- Create: `frontend/src/api/insights.ts`

- [ ] **Step 1: Create API client**

Create `frontend/src/api/insights.ts`:

```typescript
const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  const data = await resp.json()
  if (!data.success) throw new Error(data.error?.message || 'Request failed')
  return data.data
}

export interface Insight {
  id: number
  project_slug: string
  project_name: string
  context_type: string
  content: string
  source: string
  created_at: string
}

export type InsightCategory = 'ship_gap' | 'hygiene' | 'pattern' | 'stale' | 'opportunity'

export function parseInsightCategory(content: string): InsightCategory | null {
  const match = content.match(/^\[(\w+)\]/)
  if (!match) return null
  return match[1] as InsightCategory
}

export function parseInsightBody(content: string): string {
  return content.replace(/^\[\w+\]\s*/, '')
}

export const insightsApi = {
  list: (category?: string, limit?: number) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (limit) params.set('limit', String(limit))
    const qs = params.toString()
    return request<Insight[]>(`/insights/${qs ? `?${qs}` : ''}`)
  },

  dismiss: (id: number) =>
    request<{ dismissed: number }>(`/insights/${id}/`, { method: 'DELETE' }),
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Compiles cleanly

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/insights.ts
git commit -m "feat(insights): frontend API client for insights"
```

---

### Task 3: Insights Page

**Files:**
- Create: `frontend/src/pages/InsightsPage.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/AppLayout/AppLayout.tsx`

- [ ] **Step 1: Create InsightsPage**

Create `frontend/src/pages/InsightsPage.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  type Insight,
  type InsightCategory,
  insightsApi,
  parseInsightBody,
  parseInsightCategory,
} from '@/api/insights'

const CATEGORIES: { key: InsightCategory | 'all'; label: string; color: string }[] = [
  { key: 'all', label: 'All', color: 'text-stone-400' },
  { key: 'ship_gap', label: 'Ship Gaps', color: 'text-amber-400' },
  { key: 'hygiene', label: 'Hygiene', color: 'text-orange-400' },
  { key: 'pattern', label: 'Patterns', color: 'text-violet-400' },
  { key: 'stale', label: 'Stale', color: 'text-stone-500' },
  { key: 'opportunity', label: 'Opportunities', color: 'text-emerald-400' },
]

const CATEGORY_STYLES: Record<string, { bg: string; border: string; text: string; label: string }> = {
  ship_gap: { bg: 'bg-amber-400/5', border: 'border-amber-400/20', text: 'text-amber-400', label: 'Ship Gap' },
  hygiene: { bg: 'bg-orange-400/5', border: 'border-orange-400/20', text: 'text-orange-400', label: 'Hygiene' },
  pattern: { bg: 'bg-violet-400/5', border: 'border-violet-400/20', text: 'text-violet-400', label: 'Pattern' },
  stale: { bg: 'bg-stone-400/5', border: 'border-stone-400/20', text: 'text-stone-500', label: 'Stale' },
  opportunity: { bg: 'bg-emerald-400/5', border: 'border-emerald-400/20', text: 'text-emerald-400', label: 'Opportunity' },
}

function InsightCard({ insight, onDismiss }: { insight: Insight; onDismiss: () => void }) {
  const category = parseInsightCategory(insight.content)
  const body = parseInsightBody(insight.content)
  const style = category ? CATEGORY_STYLES[category] : null
  const [dismissing, setDismissing] = useState(false)

  async function handleDismiss(e: React.MouseEvent) {
    e.stopPropagation()
    setDismissing(true)
    try {
      await insightsApi.dismiss(insight.id)
      onDismiss()
    } finally {
      setDismissing(false)
    }
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ type: 'spring', stiffness: 400, damping: 35 }}
      className={`bg-stone-900 border rounded-xl p-5 ${style ? style.border : 'border-stone-800'}`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <Link
          to="/"
          className="text-xs font-semibold text-stone-300 hover:text-orange-400 transition-colors"
        >
          {insight.project_name}
        </Link>
        {style && (
          <span className={`text-[9px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded ${style.bg} ${style.text}`}>
            {style.label}
          </span>
        )}
        <span className="text-[10px] text-stone-700 ml-auto">
          {new Date(insight.created_at).toLocaleDateString()}
        </span>
        <button
          onClick={handleDismiss}
          disabled={dismissing}
          className="text-stone-800 hover:text-stone-500 text-xs transition-colors ml-1"
          title="Dismiss"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="text-sm text-stone-300 leading-relaxed mb-3">
        {body}
      </div>

      {/* Source */}
      <div className="text-[10px] text-stone-700">
        {insight.source}
      </div>
    </motion.div>
  )
}

export function InsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<string>('all')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const category = filter === 'all' ? undefined : filter
        const data = await insightsApi.list(category, 50)
        if (!cancelled) setInsights(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load insights')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [filter, refreshKey])

  if (error) {
    return <div className="flex items-center justify-center h-64 text-red-400 text-sm">{error}</div>
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-stone-100">Insights</h1>
        <span className="text-xs text-stone-600 bg-stone-900 px-2.5 py-1 rounded">
          {loading ? '...' : `${insights.length} insights`}
        </span>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-6 bg-stone-900 rounded-lg p-1 overflow-x-auto">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setFilter(cat.key)}
            className={`text-xs px-3 py-1.5 rounded-md transition-colors whitespace-nowrap ${
              filter === cat.key
                ? 'bg-stone-800 text-stone-100 font-medium'
                : 'text-stone-500 hover:text-stone-300'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Feed */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-stone-900 border border-stone-800 rounded-xl p-5 animate-pulse">
              <div className="flex gap-3 mb-3">
                <div className="h-3 bg-stone-800 rounded w-24" />
                <div className="h-3 bg-stone-800 rounded w-16" />
              </div>
              <div className="space-y-2">
                <div className="h-3 bg-stone-800/70 rounded w-full" />
                <div className="h-3 bg-stone-800/70 rounded w-4/5" />
              </div>
            </div>
          ))}
        </div>
      ) : insights.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-stone-600 text-sm mb-2">No insights yet</div>
          <div className="text-stone-700 text-xs">
            Run <span className="font-mono text-stone-500">canopy:portfolio-review</span> to generate cross-project insights
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {insights.map((insight) => (
              <InsightCard
                key={insight.id}
                insight={insight}
                onDismiss={() => setRefreshKey((k) => k + 1)}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Update router**

In `frontend/src/router.tsx`:

Add import:
```typescript
import { InsightsPage } from './pages/InsightsPage'
```

Add route in children array (after `/` and before `/skills`):
```typescript
{ path: '/insights', element: <InsightsPage /> },
```

- [ ] **Step 3: Update nav**

In `frontend/src/components/AppLayout/AppLayout.tsx`, update `NAV_ITEMS`:

```typescript
const NAV_ITEMS = [
  { path: '/', label: 'Projects' },
  { path: '/insights', label: 'Insights' },
  { path: '/skills', label: 'Skills' },
  { path: '/leaderboard', label: 'Leaderboard' },
  { path: '/guide', label: 'Guide' },
  { path: '/settings', label: 'Settings' },
]
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Compiles cleanly

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/InsightsPage.tsx frontend/src/api/insights.ts frontend/src/router.tsx frontend/src/components/AppLayout/AppLayout.tsx
git commit -m "feat(insights): insights page with category filtering and dismiss"
```

---

### Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add to Key URLs**

Add after `/skills`:
```
- `/insights` — Cross-portfolio AI insights feed
```

- [ ] **Step 2: Add to API Endpoints**

Add a new subsection after Projects:

```markdown
### Insights
- `GET /api/insights/` — List all insights across projects (filter: ?category=ship_gap)
- `DELETE /api/insights/{id}/` — Dismiss an insight
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add insights route and API to CLAUDE.md"
```

---

### Task 5: Portfolio Review Canopy Skill

**Files:**
- Create: `~/emdash-projects/canopy/plugins/canopy/skills/portfolio-review/SKILL.md`

- [ ] **Step 1: Create the skill**

Create `~/emdash-projects/canopy/plugins/canopy/skills/portfolio-review/SKILL.md`:

````markdown
---
name: portfolio-review
description: Generate actionable insights across all projects in the canopy workbench. Reads project data, gathers GitHub context, and pushes categorized insights to the insights feed.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Portfolio Review

Generate actionable cross-project insights for the canopy workbench. This is the intelligence layer — it reads workbench data + GitHub context and produces specific, evidence-backed observations.

## When to Use

- Weekly review of all projects
- After a burst of activity across multiple projects
- When deciding what to work on next

## The Anti-Pattern: Generic Advice

**Never generate insights like:**
- "Consider deploying ace-web" (no evidence, no context)
- "canopy and ace share patterns" (vague, not actionable)
- "Project X hasn't been updated" (so what?)

**Every insight MUST contain:**
1. **Specific evidence** — commit counts, PR numbers, file paths, timestamps
2. **Why it matters** — what breaks, stalls, or improves if you act
3. **Concrete action** — exactly what to do, not "consider" or "review"

## Insight Format

Each insight is a text string prefixed with a category tag:

```
[ship_gap] ace-web has 6 unreleased commits since last deploy on Apr 8, including the AWS migration (#9) and OAuth flow. CI is green on main. Deploy to verify nginx sidecar in production.
```

Categories:
- `[ship_gap]` — Commits ahead of deploy, CI green but not shipped
- `[hygiene]` — Repeatable action overdue (code-review, doc-regen, etc.)
- `[pattern]` — Shared code/approach that diverged across repos
- `[stale]` — Project with open work that's gone quiet
- `[opportunity]` — Cross-project synergy or improvement idea

## Flow

### 1. Read the workbench

```bash
API_URL="${CANOPY_WEB_API_URL:-https://canopy-web-backend-hhhi4yut3q-uc.a.run.app}"
curl -s "$API_URL/api/projects/" | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']
for p in data:
    ctx = p.get('latest_context', {})
    actions = p.get('latest_actions', {})
    summary = ctx.get('summary', {}).get('content', 'none')
    print(f\"--- {p['slug']} ---\")
    print(f\"  repo: {p['repo_url']}\")
    print(f\"  deploy: {p['deploy_url']}\")
    print(f\"  summary: {summary[:100]}\")
    print(f\"  actions: {json.dumps(actions)}\")
    print(f\"  skills: {len(p.get('skills', []))}\")
"
```

### 2. For each active project with a repo URL, gather GitHub context

Select 3-5 projects that are most likely to have insights (recent activity, stale deploys, missing hygiene). For each:

```bash
# Recent PRs
gh pr list --repo jjackson/$SLUG --state merged --limit 5 --json number,title,mergedAt 2>/dev/null || echo "[]"

# Open PRs
gh pr list --repo jjackson/$SLUG --state open --json number,title 2>/dev/null || echo "[]"

# Recent commits on main
gh api repos/jjackson/$SLUG/commits?per_page=5 --jq '.[].commit.message' 2>/dev/null || echo ""

# CI status
gh run list --repo jjackson/$SLUG --limit 1 --json conclusion --jq '.[0].conclusion' 2>/dev/null || echo "unknown"
```

### 3. Analyze and generate insights

For each project, check:

**Ship gaps:**
- Count commits on main since last deploy (compare `latest_actions` deploy timestamp vs latest commit)
- If CI is green and commits > 0: generate `[ship_gap]` insight

**Hygiene:**
- Check `latest_actions` for each tracked skill
- If code-review hasn't run in 14+ days on a project with 3+ merged PRs: generate `[hygiene]` insight
- If doc-regen hasn't run in 30+ days: generate `[hygiene]` insight

**Patterns:**
- If two projects share the same skill name (e.g., both have `update` in their skills list), read both implementations via `gh api repos/.../contents/skills/update` and check if they've diverged
- Only generate `[pattern]` if you can cite specific differences

**Stale:**
- If a project had activity 2+ weeks ago but nothing since, and has open PRs or unfinished context: generate `[stale]` insight

**Opportunities:**
- If two projects use the same stack (both Django+React) and one has a feature the other doesn't: generate `[opportunity]`

### 4. Push insights

For each insight, push to the project it's most relevant to:

```bash
curl -s -X POST "$API_URL/api/projects/$SLUG/context/" \
  -H "Content-Type: application/json" \
  -d "{
    \"context_type\": \"insight\",
    \"content\": \"[category] Your specific insight text here with evidence\",
    \"source\": \"canopy:portfolio-review\"
  }"
```

### 5. Report to user

After pushing all insights, summarize:
- How many insights generated, by category
- Which projects were reviewed
- Link to the insights page

## Rules

- **Never fabricate evidence.** Only cite commits, PRs, and dates you actually read from the API.
- **Maximum 8 insights per run.** Quality over quantity. If you have more than 8, keep only the most actionable.
- **Each insight must reference a specific project.** No "in general" observations.
- **Don't repeat stale insights.** Read existing insights first (`GET /api/insights/`) and skip any that duplicate what's already posted.
- **Confidence threshold.** If you're not confident an insight is actionable, don't post it. "Might need attention" is not an insight.
- **Use `canopy:portfolio-review` as the source** so it's clear where the insight came from.
````

- [ ] **Step 2: Commit in canopy repo**

```bash
cd ~/emdash-projects/canopy
git add plugins/canopy/skills/portfolio-review/SKILL.md
git commit -m "feat(skills): add portfolio-review skill for cross-project insights"
```

---

### Task 6: Run Full Test Suite + Deploy

- [ ] **Step 1: Run backend tests**

Run: `uv run pytest -v`
Expected: All tests pass (existing + 7 new insight tests)

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Compiles cleanly

- [ ] **Step 3: Push, merge, deploy**

Push, create PR, merge, wait for CI deploy.

- [ ] **Step 4: Run migration**

Update migrate job image and execute:
```bash
NEW_SHA=$(gcloud run services describe canopy-web-backend --region=us-central1 --format="value(spec.template.spec.containers[0].image)")
gcloud run jobs update canopy-web-migrate --region=us-central1 --image="$NEW_SHA"
gcloud run jobs execute canopy-web-migrate --region=us-central1 --wait
```

(Note: this plan doesn't add new models, so migration may not be needed — but the insights API needs the deployed code.)

- [ ] **Step 5: Test the portfolio-review skill**

Run: `/canopy:portfolio-review`

Then verify insights appear at `https://canopy-web-frontend-hhhi4yut3q-uc.a.run.app/insights`
