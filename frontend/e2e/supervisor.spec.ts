import { test, expect } from '@playwright/test'

test.describe('/supervisor', () => {
  test('renders the fleet at phone width without horizontal scroll', async ({ page }) => {
    await page.goto('/supervisor')
    await expect(page.getByTestId('supervisor-page')).toBeVisible()
    await expect(page.getByTestId('runner-status').or(page.getByText('No runner paired'))).toBeVisible()
    await expect(page.getByTestId('waiting-on-you').or(page.getByTestId('waiting-empty'))).toBeVisible()

    // The body must never scroll sideways. Wide content scrolls in its OWN
    // container; a page-level overflow means a component broke the contract.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('waiting-on-you is above the fold', async ({ page }) => {
    await page.goto('/supervisor')
    const inbox = page.getByTestId('waiting-on-you').or(page.getByTestId('waiting-empty'))
    await expect(inbox).toBeInViewport()
  })

  test('one failed call does not blank the page', async ({ page }) => {
    // The whole point of allSettled: on cellular a single flaky call is common,
    // and Promise.all would take the other two bands down with it.
    await page.route('**/api/agents/needs-you', (r) => r.abort())
    await page.goto('/supervisor')
    await expect(page.getByTestId('supervisor-page')).toBeVisible()
    // Runners still rendered despite needs-you failing.
    await expect(page.getByTestId('runner-status').or(page.getByText('No runner paired'))).toBeVisible()
  })

  test('the composer dispatches a launchable command', async ({ page }) => {
    await page.goto('/supervisor')
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
})
