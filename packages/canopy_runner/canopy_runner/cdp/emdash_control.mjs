// emdash CDP control sidecar — drives the RUNNING emdash app over the Chrome
// DevTools Protocol (emdash is Electron; launch it with --remote-debugging-port).
// This is the sanctioned path (no DB injection, no app patching): tasks created
// here flow through emdash's own UI, so they appear live in the sidebar and run
// interactive `claude` on the subscription. Commands (arg = JSON on argv[3]):
//   list                              -> {ok, tasks:[names], projects:[names]}
//   create {project, prompt}          -> {ok, action:"created"}    (new session)
//   open-send {task, text}            -> {ok, action:"sent", task} (REUSE existing)
// All output is a single JSON line on stdout. Occlusion-proof: uses JS-dispatched
// clicks so it works while emdash is backgrounded (no foreground focus needed).
import { chromium } from 'playwright-core';

const command = process.argv[2];
const args = JSON.parse(process.argv[3] || '{}');
const port = args.port || 9222;

function out(o) { process.stdout.write(JSON.stringify(o)); }
function fail(msg) { out({ ok: false, error: msg }); process.exit(1); }

let browser;
try {
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
} catch {
  fail(`cannot connect to emdash CDP on 127.0.0.1:${port} — launch emdash with --remote-debugging-port=${port}`);
}
const page = browser.contexts()[0]?.pages()[0];
if (!page) fail('no emdash renderer page found over CDP');

try {
  if (command === 'list') {
    const data = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('button')].map(b => b.getAttribute('aria-label') || '');
      return {
        tasks: labels.filter(t => t.startsWith('Open task ')).map(t => t.slice('Open task '.length)),
        projects: labels.filter(t => t.startsWith('New task for ')).map(t => t.slice('New task for '.length)),
      };
    });
    out({ ok: true, ...data });

  } else if (command === 'create') {
    const { project, prompt } = args;
    const taskNames = () => page.evaluate(() =>
      [...document.querySelectorAll('button')].map(b => b.getAttribute('aria-label') || '')
        .filter(t => t.startsWith('Open task ')).map(t => t.slice('Open task '.length)));
    const before = await taskNames();
    const opened = await page.evaluate((p) => {
      const b = [...document.querySelectorAll('button')].find(x => x.getAttribute('aria-label') === `New task for ${p}`);
      if (!b) return false; b.click(); return true;
    }, project);
    if (!opened) fail(`no "New task for ${project}" control — is project "${project}" loaded in emdash?`);
    await page.waitForTimeout(1000);
    // Initial-conversation prompt is a contenteditable in the Create Task dialog.
    const ce = page.locator('[role=dialog] [contenteditable="true"], [class*=Dialog] [contenteditable="true"]').first();
    await ce.click();
    await page.keyboard.type(prompt);
    const created = await page.evaluate(() => {
      const dlg = document.querySelector('[role=dialog],[class*=Dialog],[class*=modal]');
      if (!dlg) return false;
      const btn = [...dlg.querySelectorAll('button')].find(b => /create/i.test(b.textContent || '') && !/close|cancel/i.test(b.textContent || ''));
      if (!btn) return false; btn.click(); return true;
    });
    if (!created) fail('could not find the Create button in the New Task dialog');
    await page.waitForTimeout(3000);
    // Identify the new task by diffing the task list (name is auto-generated).
    const after = await taskNames();
    const beforeSet = new Set(before);
    const fresh = after.filter(n => !beforeSet.has(n));
    out({ ok: true, action: 'created', task: fresh[0] || '', all_new: fresh });

  } else if (command === 'open-send') {
    // REUSE: open an EXISTING task and send text into its live terminal. Fails if the
    // task isn't present (e.g. it belongs to another macOS account's emdash) so the
    // caller can fall back to create+rehydrate.
    const { task, text } = args;
    const opened = await page.evaluate((t) => {
      const b = [...document.querySelectorAll('button')].find(x => x.getAttribute('aria-label') === `Open task ${t}`);
      if (!b) return false; b.click(); return true;
    }, task);
    if (!opened) fail(`no existing task "${task}" in this emdash (it may belong to another macOS account)`);
    await page.waitForTimeout(1200);
    // Send into the VISIBLE terminal input — the active task's, even when several
    // xterm instances are mounted in the DOM.
    const input = page.locator('textarea[aria-label="Terminal input"]:visible').first();
    await input.click();
    await page.keyboard.type(text);
    await page.keyboard.press('Enter');
    out({ ok: true, action: 'sent', task });

  } else {
    fail(`unknown command: ${command}`);
  }
} catch (e) {
  fail(String((e && e.message) || e));
} finally {
  await browser.close();
}
