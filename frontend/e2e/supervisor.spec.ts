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
})
