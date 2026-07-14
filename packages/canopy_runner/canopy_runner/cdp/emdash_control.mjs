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
    const { project, prompt, taskName } = args;
    const taskNames = () => page.evaluate(() =>
      [...document.querySelectorAll('button')].map(b => b.getAttribute('aria-label') || '')
        .filter(t => t.startsWith('Open task ')).map(t => t.slice('Open task '.length)));
    // The project sidebar VIRTUALIZES rows — a project scrolled out of view isn't in
    // the DOM at all. Scan the sidebar scroller (.overflow-y-auto) top→bottom, letting
    // rows render, until the target project's "New task for X" button appears.
    const sidebarScrollTop = (v) => page.evaluate((val) => {
      const sc = [...document.querySelectorAll('.overflow-y-auto')].sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
      if (!sc) return 0;
      if (val === 'top') sc.scrollTop = 0; else sc.scrollTop += val;
      return sc.scrollTop;
    });
    let haveBtn = false;
    await sidebarScrollTop('top');
    await page.waitForTimeout(200);
    let lastTop = -1;
    for (let i = 0; i < 40 && !haveBtn; i++) {
      haveBtn = await page.evaluate((p) => {
        const btn = [...document.querySelectorAll('button')].find(x => x.getAttribute('aria-label') === `New task for ${p}`);
        if (btn) { btn.scrollIntoView({ block: 'center' }); return true; }
        return false;
      }, project);
      if (haveBtn) break;
      const top = await sidebarScrollTop(280);   // step down
      await page.waitForTimeout(160);
      if (top === lastTop) break;                 // reached the bottom
      lastTop = top;
    }
    if (!haveBtn) fail(`no "New task for ${project}" control — project "${project}" not found in the emdash sidebar`);
    await page.evaluate((p) => {
      [...document.querySelectorAll('button')].find(x => x.getAttribute('aria-label') === `New task for ${p}`)?.click();
    }, project);
    await page.waitForTimeout(1000);
    // Set a deterministic task NAME so we don't have to detect it afterward (the
    // list-diff is unreliable under sidebar virtualization). The name input is the
    // dialog's first text input (its placeholder is emdash's auto-generated name).
    let finalName = taskName || "";
    if (taskName) {
      const named = await page.evaluate((name) => {
        const dlg = document.querySelector('[role=dialog],[class*=Dialog],[class*=modal]');
        if (!dlg) return false;
        const input = [...dlg.querySelectorAll('input')].find(i => (i.type === 'text' || !i.type) && i.value !== 'claude' && i.value !== 'on');
        if (!input) return false;
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, name);                                   // React-friendly value set
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }, taskName);
      if (!named) finalName = "";   // fell back — will diff below
    }
    const before = await taskNames();
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
    if (!finalName) {
      // Fallback: diff (best-effort; may be imprecise under virtualization).
      const after = await taskNames();
      const beforeSet = new Set(before);
      finalName = (after.filter(n => !beforeSet.has(n)))[0] || "";
    }
    out({ ok: true, action: 'created', task: finalName });

  } else if (command === 'open-send') {
    // REUSE: open an EXISTING task and send text into its live terminal. Fails if the
    // task isn't present (e.g. it belongs to another macOS account's emdash) so the
    // caller can fall back to create+rehydrate.
    const { task, text } = args;
    const opened = await page.evaluate((t) => {
      const b = [...document.querySelectorAll('button')].find(x => x.getAttribute('aria-label') === `Open task ${t}`);
      if (!b) return false; b.click(); return true;
    }, task);
    // TASK_NOT_FOUND is the ONLY condition under which the caller should create a
    // fresh session — a genuinely-absent task (archived, or another macOS account's).
    // Any later failure means the task EXISTS but the interaction glitched: the caller
    // must NOT create a duplicate.
    if (!opened) fail(`TASK_NOT_FOUND: no task "${task}" in this emdash (archived, or another macOS account)`);
    await page.waitForTimeout(1200);
    // Focus the ACTIVE terminal's input, then type. xterm's real input is an
    // off-screen `.xterm-helper-textarea`, so a Playwright .click() fails its
    // viewport check — we focus it via JS (viewport-agnostic) instead, picking the
    // visible xterm (the active task's pane) when several are mounted.
    const focused = await page.evaluate(() => {
      const terms = [...document.querySelectorAll('.xterm')]
        .filter(t => t.offsetParent !== null && t.getBoundingClientRect().width > 0);
      const term = terms[0];
      const ta = (term && term.querySelector('.xterm-helper-textarea'))
        || document.querySelector('textarea[aria-label="Terminal input"]');
      if (!ta) return false;
      ta.focus();
      return true;
    });
    if (!focused) fail(`could not focus the terminal input for task "${task}"`);
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
