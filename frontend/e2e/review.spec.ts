import { test, expect, type Page } from '@playwright/test'

// A run-child (product_findings) review belongs to no DDD narrative. It must render
// standalone — no DDD rail — and it must not conjure a narrative out of its run_id.
//
// The regression: /review/<id> rendered inside DddShell unconditionally, and the
// aggregate parsed a narrative slug out of ANY review's run_id. Ada's fleet audit
// therefore appeared in the DDD rail as a narrative that existed only because
// someone parsed its id — active, empty ("No versions yet"), and unnavigable.

const FLEET_AUDIT_RUN_ID = 'ada-fleet-audit-2026-07-14'

/** The seeded fleet-audit review's id (generated, so discover it via the API). */
async function fleetAuditReviewId(page: Page): Promise<string> {
  const rows = await (await page.request.get('/api/reviews/')).json()
  const row = rows.find((r: { run_id: string }) => r.run_id === FLEET_AUDIT_RUN_ID)
  expect(row, 'seed should provide a fleet-audit review').toBeTruthy()
  return row.id
}

test('a fleet-audit findings review renders without the DDD rail', async ({ page }) => {
  await page.goto(`/review/${await fleetAuditReviewId(page)}`)

  // The findings surface itself is present...
  await expect(page.getByText('hal: discard 81 junk/stale unread emails (of 82 total)')).toBeVisible()

  // ...and the page still names its own run, which is its only honest identity.
  await expect(page.getByText(FLEET_AUDIT_RUN_ID, { exact: true })).toBeVisible()

  // ...but none of the DDD narratives rail is.
  await expect(page.getByRole('link', { name: 'Narratives', exact: true })).toHaveCount(0)
  await expect(page.getByText('DDD runs, grouped by narrative')).toHaveCount(0)
  await expect(page.getByText('No versions yet')).toHaveCount(0)
})

test('a fleet-audit run_id conjures no narrative into the DDD rail', async ({ page }) => {
  const narratives = await (await page.request.get('/api/ddd/narratives/')).json()
  const slugs = narratives.map((n: { slug: string }) => n.slug)

  expect(slugs).not.toContain(FLEET_AUDIT_RUN_ID)
  expect(slugs).not.toContain('ada-fleet-audit')
})

test('a run-child review reports no narrative_slug', async ({ page }) => {
  const id = await fleetAuditReviewId(page)
  const detail = await (await page.request.get(`/api/reviews/${id}/`)).json()

  expect(detail.narrative_slug).toBeNull()
})
