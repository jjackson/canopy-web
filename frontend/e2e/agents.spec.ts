import { test, expect, type Page } from '@playwright/test'

const cmd = (page: Page) =>
  page.waitForResponse((r) => r.url().includes('/commands') && r.request().method() === 'POST')

test('agents list shows the Echo agent', async ({ page }) => {
  await page.goto('/agents')
  await expect(page.getByText('Echo').first()).toBeVisible()
})

test('workspace rail exposes the sections', async ({ page }) => {
  await page.goto('/agents/echo')
  await expect(page.locator('a[href$="/agents/echo/tasks"]')).toBeVisible()
  await expect(page.locator('a[href$="/agents/echo/syncs"]')).toBeVisible()
  await expect(page.locator('a[href$="/agents/echo/skills"]')).toBeVisible()
})

test('overview shows the latest sync', async ({ page }) => {
  await page.goto('/agents/echo/overview')
  await expect(page.getByText('Manager sync 1')).toBeVisible()
})

test('syncs section lists the sync with its self-grades', async ({ page }) => {
  await page.goto('/agents/echo/syncs')
  await expect(page.getByText('Manager sync 1')).toBeVisible()
  await expect(page.getByText(/C\+/)).toBeVisible()
})

test('work products section lists the deliverable', async ({ page }) => {
  await page.goto('/agents/echo/work-products')
  await expect(page.getByText('Demo story RUWOYD')).toBeVisible()
})

test('skills section lists the catalog', async ({ page }) => {
  await page.goto('/agents/echo/skills')
  await expect(page.getByText('email-communicator')).toBeVisible()
})

test('task board groups by who has the ball, with context + queue badge', async ({ page }) => {
  await page.goto('/agents/echo/tasks')
  for (const label of ['Suggested', 'Waiting on a human', 'Echo working', 'Done']) {
    await expect(page.getByText(label, { exact: false }).first()).toBeVisible()
  }
  await expect(page.getByTestId('task-t1')).toHaveAttribute('data-status', 'suggested')
  await expect(page.getByTestId('task-t3')).toHaveAttribute('data-status', 'in_progress')
  await expect(page.getByText(/Strong near-miss/)).toBeVisible() // rationale on the card
  await expect(page.getByText(/queued for Echo/i)).toBeVisible() // the seeded pending command
})

test('accept flips a suggested task to in progress and clears its Accept button', async ({ page }) => {
  await page.goto('/agents/echo/tasks')
  const card = page.getByTestId('task-t2')
  await expect(card).toHaveAttribute('data-status', 'suggested')
  const [resp] = await Promise.all([cmd(page), card.getByRole('button', { name: /^Accept$/ }).click()])
  expect(resp.status()).toBe(201)
  await expect(page.getByTestId('task-t2')).toHaveAttribute('data-status', 'in_progress')
  await expect(page.getByTestId('task-t2').getByRole('button', { name: /^Accept$/ })).toHaveCount(0)
})

test('decline takes a reason and moves the task to declined', async ({ page }) => {
  await page.goto('/agents/echo/tasks')
  const card = page.getByTestId('task-t1')
  await card.getByRole('button', { name: /^Decline$/ }).click()
  await card.getByRole('textbox').fill('not a fit right now')
  const [resp] = await Promise.all([cmd(page), card.getByRole('button', { name: /Confirm/i }).click()])
  expect(resp.status()).toBe(201)
  await expect(page.getByTestId('task-t1')).toHaveAttribute('data-status', 'declined')
})

test('dispatch queues a "do it now" command for the agent', async ({ page }) => {
  await page.goto('/agents/echo/tasks')
  const card = page.getByTestId('task-t3') // waiting-on-a-human, in progress
  const [resp] = await Promise.all([cmd(page), card.getByRole('button', { name: /do this now/i }).click()])
  expect(resp.status()).toBe(201)
})

test('mark done moves an in-progress task to Done', async ({ page }) => {
  await page.goto('/agents/echo/tasks')
  const card = page.getByTestId('task-t4') // Echo working
  const [resp] = await Promise.all([cmd(page), card.getByRole('button', { name: /Mark done/i }).click()])
  expect(resp.status()).toBe(201)
  await expect(page.getByTestId('task-t4')).toHaveAttribute('data-status', 'done')
})
