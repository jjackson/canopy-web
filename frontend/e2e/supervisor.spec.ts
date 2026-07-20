import { test, expect } from '@playwright/test'

// Reach a tab's content. Inbox is the default landing; Sessions/Agents need a click.
async function openTab(page: import('@playwright/test').Page, tab: 'inbox' | 'sessions' | 'agents') {
  if (tab !== 'inbox') await page.getByTestId(`tab-${tab}`).click()
}

test.describe('/supervisor', () => {
  test('renders without horizontal scroll on every tab', async ({ page }) => {
    await page.goto('/supervisor')
    await expect(page.getByTestId('supervisor-page')).toBeVisible()
    for (const tab of ['inbox', 'sessions', 'agents'] as const) {
      await openTab(page, tab)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow, `tab ${tab} overflows`).toBeLessThanOrEqual(0)
    }
  })

  test('defaults to Inbox and deep-links via ?tab=', async ({ page }) => {
    // Default landing (what push drops you into) is Inbox: the waiting queue is
    // visible and the other tabs' content is not.
    await page.goto('/supervisor')
    await expect(page.getByTestId('waiting-on-you').or(page.getByTestId('waiting-empty'))).toBeVisible()
    await expect(page.getByTestId('open-sessions').or(page.getByTestId('sessions-empty'))).toBeHidden()

    // Deep-link straight to Agents.
    await page.goto('/supervisor?tab=agents')
    await expect(page.getByTestId('runner-status').or(page.getByText('No runner paired'))).toBeVisible()
  })

  test('waiting-on-you is above the fold', async ({ page }) => {
    await page.goto('/supervisor')
    const inbox = page.getByTestId('waiting-on-you').or(page.getByTestId('waiting-empty'))
    await expect(inbox).toBeInViewport()
  })

  test('one failed call does not blank the page', async ({ page }) => {
    await page.route('**/api/agents/needs-you', (r) => r.abort())
    await page.goto('/supervisor')
    await expect(page.getByTestId('supervisor-page')).toBeVisible()
    // Runners (Agents tab) still render despite the Inbox fetch failing.
    await openTab(page, 'agents')
    await expect(page.getByTestId('runner-status').or(page.getByText('No runner paired'))).toBeVisible()
  })

  test('the composer dispatches a launchable command', async ({ page }) => {
    await page.goto('/supervisor')
    await openTab(page, 'sessions')
    const composer = page.getByTestId('composer')
    await expect(composer).toBeVisible()

    // Pick echo — the fleet has several agents and the default is whichever sorts
    // first; only echo carries a launchable skill in the seed.
    await page.getByTestId('composer-agent').selectOption('echo')

    // Only launchable skills appear — the seed's non-launchable email-communicator
    // must NOT be an option; story-ideation must.
    const skill = page.getByTestId('composer-skill')
    await expect(skill.locator('option', { hasText: 'story-ideation' })).toHaveCount(1)
    await expect(skill.locator('option', { hasText: 'email-communicator' })).toHaveCount(0)

    await skill.selectOption('story-ideation')
    // args_hint from the launchable skill drives the placeholder.
    await expect(page.getByTestId('composer-args')).toHaveAttribute('placeholder', 'topic (optional)')
    // The preview shows the exact command that will land in the session.
    await expect(page.getByTestId('composer-preview')).toHaveText('/echo:story-ideation')

    let posted: Record<string, unknown> | null = null
    await page.route('**/api/harness/turns/', async (route) => {
      posted = route.request().postDataJSON()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ id: 't-1', agent_slug: 'echo', project: '', target: 'echo', status: 'queued' }),
      })
    })

    await page.getByTestId('composer-args').fill('bednets')
    await page.getByTestId('composer-send').click()

    await expect(page.getByTestId('composer-sent')).toBeVisible()
    expect(posted).toMatchObject({ agent_slug: 'echo', prompt: '/echo:story-ideation bednets' })
  })

  test('a repo dispatch pins its workspace and routes to the tenant endpoint', async ({ page }) => {
    await page.goto('/supervisor')
    await openTab(page, 'sessions')
    await page.getByTestId('composer-mode-repo').click()

    // A repo turn's tenant is first-class and defaults to dimagi (the e2e
    // workspace), shown in the selector — not hidden server magic.
    await expect(page.getByTestId('composer-workspace')).toHaveValue('dimagi')
    await page.getByTestId('composer-project').fill('canopy-web')

    let url: string | null = null
    let posted: Record<string, unknown> | null = null
    let headers: Record<string, string> = {}
    // The proof the workspace is pinned: the request lands on the TENANT-scoped
    // path /api/w/dimagi/…, not the flat mount (which would 422 a multi-workspace
    // user). WORKSPACE_HEADER drove the client-side rewrite.
    await page.route('**/api/w/*/harness/turns/', async (route) => {
      url = route.request().url()
      posted = route.request().postDataJSON()
      headers = route.request().headers()
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({ id: 't-2', agent_slug: null, project: 'canopy-web', target: 'canopy-web', status: 'queued' }),
      })
    })

    await page.getByTestId('composer-args').fill('fix the header spacing')
    await page.getByTestId('composer-send').click()

    await expect(page.getByTestId('composer-sent')).toBeVisible()
    expect(url).toContain('/api/w/dimagi/harness/turns/')
    expect(posted).toMatchObject({ project: 'canopy-web', prompt: 'fix the header spacing' })
    // A stable per-(user,repo) thread_key so the NEXT dispatch continues this
    // session rather than forking a fresh emdash task — "drive the repo" is
    // iterative. The e2e user is e2e@dimagi.com.
    expect((posted as { origin_ref?: { thread_key?: string } }).origin_ref?.thread_key).toBe(
      'phone:e2e@dimagi.com:canopy-web',
    )
    // The pin header is consumed by the rewrite and must NOT reach the wire — it
    // is a client-side routing signal, not something the server should ever see.
    expect(headers['x-canopy-workspace']).toBeUndefined()
  })

  test('open sessions list and continue dispatches into that exact task', async ({ page }) => {
    await page.goto('/supervisor')
    await openTab(page, 'sessions')
    await expect(page.getByTestId('open-sessions')).toBeVisible()
    await expect(page.getByTestId('session-cloud-runner')).toBeVisible()

    let posted: Record<string, unknown> | null = null
    let url: string | null = null
    await page.route('**/api/w/*/harness/turns/', async (route) => {
      url = route.request().url()
      posted = route.request().postDataJSON()
      await route.fulfill({
        status: 201, contentType: 'application/json',
        body: JSON.stringify({ id: 't-9', agent_slug: null, project: 'canopy-web', target: 'canopy-web', status: 'queued' }),
      })
    })

    await page.getByTestId('session-input-cloud-runner').fill('rerun the failing test')
    await page.getByTestId('session-send-cloud-runner').click()

    await expect(page.getByTestId('session-sent-cloud-runner')).toBeVisible()
    expect(url).toContain('/api/w/dimagi/harness/turns/')  // tenant-pinned
    expect(posted).toMatchObject({ project: 'canopy-web', prompt: 'rerun the failing test' })
    expect((posted as { origin_ref?: { thread_key?: string } }).origin_ref?.thread_key).toBe('emdash:cloud-runner')
  })

  test('a runner shows not-ready and opens a detail view with the reason', async ({ page }) => {
    await page.goto('/supervisor?tab=agents')
    // the seeded runner is not-ready → the list shows the marker
    const notReady = page.locator('[data-testid^="runner-notready-"]').first()
    await expect(notReady).toBeVisible()
    // tap the runner row → detail view with the reason
    await page.locator('[data-testid^="runner-"]').filter({ hasText: /not ready/ }).first().click()
    await expect(page.getByTestId('runner-detail-back')).toBeVisible()
    await expect(page.getByTestId('runner-detail-ready')).toHaveText('not ready')
    await expect(page.getByTestId('runner-detail-why')).toContainText('emdash CDP unreachable')
  })
})
