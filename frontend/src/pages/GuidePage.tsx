import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'

const SECTIONS = [
  { id: 'try-it', label: 'Try It Now' },
  { id: 'overview', label: 'How It Works' },
  { id: 'workspace', label: 'Review & Edit' },
  { id: 'eval', label: 'Test with Evals' },
  { id: 'deploy', label: 'Deploy' },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

// ---------------------------------------------------------------------------
// Sample content — internal conversations about discovery call process
// ---------------------------------------------------------------------------

const SAMPLE_COLLECTION_NAME = 'Discovery Call Debrief'
const SAMPLE_COLLECTION_DESC =
  'Capture how the partnerships team runs discovery call debriefs — what to extract, how to qualify, and what a good write-up looks like.'

const SAMPLE_SOURCE_1 = `#partnerships — February 22, 2026

Priya: Hey Beth, I just had my first solo discovery call (with that health network in Kenya). I took notes but I'm not sure I captured the right things. What does your debrief process look like? I want to make sure I'm not missing anything before I send the write-up to Neal.

Beth: Great question — I'll walk you through how I do it. After every call I write up a structured debrief that covers these areas:

1. **Organization snapshot** — who they are, size, geography, what program we're talking about. This is the stuff you'd put at the top of a CRM entry.

2. **Pain points** — the actual problems they described, in their words. Not our interpretation of what they need, but what THEY said is broken. Direct quotes are gold here. If they mentioned a specific incident ("we almost lost our USAID grant because...") always capture that — it tells you urgency.

3. **Current state** — what tools/systems they're using today, who built them, what's working and what isn't. This is critical for solutions engineering later.

4. **Requirements** — what they explicitly said they need. Separate "must have" from "nice to have." If they said something is "non-negotiable" write that down verbatim.

5. **Decision landscape** — who are the decision makers, who has budget authority, who's the champion vs who might block. Also note if they mentioned evaluating competitors and what happened with those.

6. **Budget & timeline** — any numbers they gave you, grant deadlines, go-live dates. Be specific — "$400K from USAID grant" not "they have budget."

7. **Next steps** — what you committed to, what they committed to, and dates for everything. This is the part people skip and then wonder why deals stall.

8. **Deal qualification** — this is your honest read. Is this real? Is it urgent? Do we have a champion? Can they actually pay? I use a simple strong/medium/weak for each.

Priya: This is super helpful. How long does yours usually take to write?

Beth: 15-20 minutes if I took good notes during the call. The key is doing it same-day while it's fresh. I've had deals go sideways because I waited a week and forgot a critical detail.

Neal: +1 to everything Beth said. I'd add one thing — always note the "aha moment" from the call. The one thing they said that tells you this is a real opportunity, not a tire-kicker. For example, "we almost missed our grant deadline" = real urgency. "We're exploring options for next year" = they're just shopping.

Beth: Great point. The aha moment is usually the thing I lead with when I brief Matt or the solutions team. It's the sentence that makes people lean in.

Priya: Got it. So the aha moment for my call was probably when they said "our field supervisors are spending 2 full days a week just re-entering data from paper forms." That's a lot of wasted time.

Beth: That's perfect. Lead with that. It's concrete, it's quantifiable, and it immediately tells anyone reading the debrief why this matters to them.

Neal: Priya — also don't forget to capture what they're NOT telling you. If they dodge budget questions or won't name the decision maker, that's a signal too. Note it in the qualification section.

Priya: Makes sense. I'll write this up now and share it in the thread for feedback before I put it in Salesforce. Thanks both!`

const SAMPLE_SOURCE_2 = `#partnerships — March 3, 2026

Neal: Team — I reviewed the last 5 debriefs we've submitted and I want to share some patterns on what's working and what's not. This affects how quickly we can move deals forward.

Neal: What the GOOD debriefs have in common:
- Specific pain points with quotes or numbers ("losing 30% of data", "almost missed USAID deadline")
- Clear decision maker map — not just names but roles and what each person cares about
- Honest qualification — saying "weak on budget authority, we don't know who approves" is more useful than being optimistic
- Concrete next steps with DATES, not "we'll follow up soon"
- Competitive context — who else they've talked to and why those didn't work out

Neal: What the WEAK debriefs are missing:
- They summarize instead of extracting. "It was a good call, they seem interested" tells me nothing. I need specifics.
- No timeline pressure. If there's no deadline driving them, the deal will stall. We need to uncover or create urgency.
- Vague budget info. "They have funding" vs "They have $400K allocated from a USAID grant that must be spent by September" — one of those I can work with, the other I can't.
- Missing the champion. Every deal needs someone inside who's pushing for us. If we don't know who that is after the discovery call, we have a problem.

Beth: This is a good list. One thing I'd add — the debrief should be useful to someone who WASN'T on the call. If our solutions engineer picks it up cold, they should be able to write a scoping proposal from it without coming back to ask basic questions. That's the bar.

Matt: Agreed. The debrief is the handoff document. If it's incomplete, every downstream step takes longer — scoping, pricing, legal. I've seen 2-week delays just because the debrief didn't capture the integration requirements and solutions had to schedule another call.

Neal: Exactly. Think of it this way — the discovery call is 30 minutes of your time. The debrief is 15 minutes. But a bad debrief costs the org hours of back-and-forth downstream. The ROI on writing a thorough one is massive.

Beth: I'm going to create a template based on this thread and the process I shared with Priya last week. That way new folks have a starting point.

Neal: Love it. Share it when it's ready and we'll make it the standard.`

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------

function SectionNav({
  active,
  onSelect,
}: {
  active: SectionId
  onSelect: (id: SectionId) => void
}) {
  return (
    <nav className="flex flex-col gap-0.5">
      {SECTIONS.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onSelect(s.id)}
          className={`rounded-md px-3 py-1.5 text-left text-sm transition-colors ${
            active === s.id
              ? 'bg-orange-400/10 border border-orange-400/30 text-orange-400 font-medium'
              : 'border border-transparent text-stone-500 hover:text-stone-200 hover:bg-stone-900'
          }`}
        >
          {s.label}
        </button>
      ))}
    </nav>
  )
}

function CopyBlock({
  children,
  title,
  label,
}: {
  children: string
  title?: string
  label?: string
}) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    void navigator.clipboard.writeText(children).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="rounded-lg border border-stone-800 bg-stone-950 overflow-hidden">
      <div className="flex items-center justify-between border-b border-stone-800 bg-stone-900 px-3 py-1.5">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-stone-500">{title}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-xs text-orange-400/70 hover:text-orange-400 font-medium transition-colors"
        >
          {copied ? 'Copied' : label || 'Copy'}
        </button>
      </div>
      <pre className="p-3 text-xs text-stone-300 font-mono overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto leading-relaxed">
        {children}
      </pre>
    </div>
  )
}

function CodeBlock({ children, title }: { children: string; title?: string }) {
  return (
    <div className="rounded-lg border border-stone-800 bg-stone-950 overflow-hidden">
      {title && (
        <div className="border-b border-stone-800 bg-stone-900 px-3 py-1.5 text-[10px] uppercase tracking-wider font-semibold text-stone-500">
          {title}
        </div>
      )}
      <pre className="p-3 text-xs text-stone-300 font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed">
        {children}
      </pre>
    </div>
  )
}

function StepBox({
  number,
  title,
  children,
}: {
  number: number
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="flex gap-4">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-orange-400/10 border border-orange-400/30 text-xs font-bold text-orange-400">
        {number}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <h4 className="text-sm font-semibold text-stone-100">{title}</h4>
        <div className="text-sm text-stone-400 space-y-2 leading-relaxed">{children}</div>
      </div>
    </div>
  )
}

function DeployTarget({
  title,
  badges,
  children,
}: {
  title: string
  badges?: string[]
  children: React.ReactNode
}) {
  return (
    <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-3 hover:border-stone-700 transition-colors">
      <div className="flex items-center gap-2 flex-wrap">
        <h4 className="text-sm font-semibold text-stone-100">{title}</h4>
        {badges?.map((b) => (
          <Badge key={b} variant="outline" className="text-[10px]">
            {b}
          </Badge>
        ))}
      </div>
      <div className="text-sm text-stone-400 space-y-2 leading-relaxed">{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section content
// ---------------------------------------------------------------------------

function TryItSection() {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-stone-100">Build Your First Skill</h2>
        <p className="mt-1 text-sm text-stone-500">
          Walk through the full flow using real internal conversations. The AI
          will extract the team's process into a reusable skill. Takes about 3
          minutes.
        </p>
      </div>

      <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-2">
        <h3 className="text-sm font-semibold text-stone-100">The scenario</h3>
        <p className="text-sm text-stone-400">
          Beth recently walked Priya through how she writes discovery call
          debriefs. Neal followed up with a review of what makes debriefs good vs
          weak. This tribal knowledge lives in two Slack threads — exactly the
          kind of thing that should be a reusable skill instead of buried in
          chat history.
        </p>
      </div>

      <div className="space-y-8">
        <StepBox number={1} title="Start a new skill">
          <p>
            Click{' '}
            <Link to="/new" className="text-orange-400 hover:text-orange-300 underline font-medium">
              New
            </Link>{' '}
            to open the skill builder. Use these values:
          </p>
          <div className="grid grid-cols-[100px_1fr] gap-x-3 gap-y-1 mt-2 text-xs">
            <span className="font-medium text-stone-200">Name</span>
            <CopyBlock title="Collection name" label="Copy name">
              {SAMPLE_COLLECTION_NAME}
            </CopyBlock>
            <span className="font-medium text-stone-200">Description</span>
            <CopyBlock title="Description" label="Copy description">
              {SAMPLE_COLLECTION_DESC}
            </CopyBlock>
          </div>
          <p className="text-xs text-stone-500 mt-2">Click <strong>Next</strong> to create the collection.</p>
        </StepBox>

        <StepBox number={2} title="Add Beth's walkthrough">
          <p>
            This is a Slack conversation where Beth explains her full debrief
            process to Priya — the 8 sections she covers, what to capture,
            and why same-day write-ups matter. Neal adds the concept of the
            "aha moment."
          </p>
          <div className="space-y-2 mt-2">
            <div className="grid grid-cols-[80px_1fr] gap-2 text-xs items-center">
              <span className="font-medium text-stone-200">Type</span>
              <span className="text-stone-400">Slack</span>
              <span className="font-medium text-stone-200">Title</span>
              <span className="text-stone-400">Beth walks Priya through debrief process</span>
            </div>
            <CopyBlock title="Source content — paste this into the Content field" label="Copy conversation">
              {SAMPLE_SOURCE_1}
            </CopyBlock>
          </div>
          <p className="text-xs text-stone-500 mt-1">Click <strong>Add</strong>, then add the second source below.</p>
        </StepBox>

        <StepBox number={3} title="Add Neal's quality review">
          <p>
            Neal reviewed recent debriefs and shared what separates the strong
            ones from the weak ones. Beth and Matt add context on why thoroughness
            matters downstream. This gives the AI a quality bar to build into
            the skill.
          </p>
          <div className="space-y-2 mt-2">
            <div className="grid grid-cols-[80px_1fr] gap-2 text-xs items-center">
              <span className="font-medium text-stone-200">Type</span>
              <span className="text-stone-400">Slack</span>
              <span className="font-medium text-stone-200">Title</span>
              <span className="text-stone-400">Neal's debrief quality review</span>
            </div>
            <CopyBlock title="Source content — paste this into the Content field" label="Copy conversation">
              {SAMPLE_SOURCE_2}
            </CopyBlock>
          </div>
          <p className="text-xs text-stone-500 mt-1">Click <strong>Add</strong> to add this source.</p>
        </StepBox>

        <StepBox number={4} title="Run the analysis">
          <p>
            Click <strong>Start Analysis</strong>. The AI reads both Slack
            threads and extracts the debrief process — Beth's 8 sections, Neal's
            quality criteria, the "aha moment" concept — into a structured skill
            definition with eval cases.
          </p>
          <p>This takes 30-60 seconds. You'll see the analysis stream in real time.</p>
        </StepBox>

        <StepBox number={5} title="Review what the AI proposes">
          <p>
            The workspace shows the proposed skill on the right and your source
            conversations on the left. Look for:
          </p>
          <ul className="space-y-1 text-xs text-stone-400 mt-1">
            <li>-- Did it capture Beth's 8 debrief sections as structured steps?</li>
            <li>-- Does it include Neal's quality criteria (specificity, quotes, honest qualification)?</li>
            <li>-- Is the "aha moment" concept reflected in the skill?</li>
            <li>-- Do the eval cases test for the things Neal flagged as missing in weak debriefs?</li>
          </ul>
          <p className="mt-2">
            Edit anything that doesn't look right, then click <strong>Publish</strong>.
          </p>
        </StepBox>

        <StepBox number={6} title="Test it">
          <p>
            On the published skill page, click <strong>Run Eval</strong> to see
            if the skill produces good output against the test cases. Green means
            it's working. If something fails, click <strong>Revise</strong> to
            improve the skill and run evals again.
          </p>
        </StepBox>
      </div>

      <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/5 p-4 space-y-2">
        <h3 className="text-sm font-semibold text-emerald-400">What you just built</h3>
        <p className="text-sm text-stone-300 leading-relaxed">
          Beth's debrief process and Neal's quality bar — captured from two Slack
          threads and turned into a reusable skill. Now any team member can
          produce a debrief that meets the standard Beth and Neal established,
          without having to find those old conversations or ask someone to walk
          them through it again.
        </p>
        <p className="text-sm text-stone-300 leading-relaxed">
          That's the core idea: tribal knowledge that lives in conversations
          becomes a tested, deployable skill that works everywhere the team
          works.
        </p>
      </div>
    </section>
  )
}

function OverviewSection() {
  return (
    <section className="space-y-4">
      <h2 className="text-base font-semibold text-stone-100">How It Works</h2>
      <p className="text-sm text-stone-400 leading-relaxed">
        Canopy turns conversations, transcripts, and documents into
        <strong className="text-stone-200"> reusable AI skills</strong> — structured instructions that any AI
        agent can follow consistently. Instead of repeating yourself across
        conversations, capture the pattern once and deploy it everywhere.
      </p>

      <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-stone-100">The flow</h3>
        <ol className="space-y-2 text-sm text-stone-400">
          <li className="flex gap-2">
            <span className="shrink-0 font-mono text-stone-600">1.</span>
            <span><strong>Paste sources</strong> — conversations, docs, Slack threads, transcripts</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 font-mono text-stone-600">2.</span>
            <span><strong>AI analyzes</strong> — extracts the repeatable pattern and proposes a skill with eval cases</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 font-mono text-stone-600">3.</span>
            <span><strong>Review & edit</strong> — refine the steps, adjust eval criteria</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 font-mono text-stone-600">4.</span>
            <span><strong>Test</strong> — run evals to verify quality</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 font-mono text-stone-600">5.</span>
            <span><strong>Deploy</strong> — export to Claude Code, Desktop, GitHub, or OpenClaw</span>
          </li>
        </ol>
      </div>

      <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-stone-100">What makes a good source?</h3>
        <p className="text-sm text-stone-400">
          Any conversation or document where someone did something well that others
          should be able to repeat:
        </p>
        <div className="grid grid-cols-2 gap-2 mt-1">
          <div className="rounded-lg border border-stone-800 bg-stone-950 px-3 py-2">
            <div className="text-xs font-medium text-stone-200">Transcript</div>
            <div className="text-xs text-stone-500">Call recordings, meeting notes</div>
          </div>
          <div className="rounded-lg border border-stone-800 bg-stone-950 px-3 py-2">
            <div className="text-xs font-medium text-stone-200">Slack</div>
            <div className="text-xs text-stone-500">Channel threads, DM conversations</div>
          </div>
          <div className="rounded-lg border border-stone-800 bg-stone-950 px-3 py-2">
            <div className="text-xs font-medium text-stone-200">Document</div>
            <div className="text-xs text-stone-500">Runbooks, SOPs, wiki pages</div>
          </div>
          <div className="rounded-lg border border-stone-800 bg-stone-950 px-3 py-2">
            <div className="text-xs font-medium text-stone-200">Text</div>
            <div className="text-xs text-stone-500">Notes, freeform instructions</div>
          </div>
        </div>
        <p className="text-xs text-stone-500 mt-1">
          Tip: Multiple sources work better — the AI cross-references them to
          find the consistent pattern.
        </p>
      </div>
    </section>
  )
}

function WorkspaceSection() {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-stone-100">Review & Edit</h2>
        <p className="mt-1 text-sm text-stone-500">
          The workspace is where you co-author the skill with the AI.
        </p>
      </div>

      <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-stone-100">Workspace layout</h3>
        <div className="text-sm text-stone-400 space-y-2">
          <p>
            <strong>Left panel — Sources.</strong> Your original source material
            for reference while editing.
          </p>
          <p>
            <strong>Right panel — Skill definition.</strong> The AI's proposed
            approach: skill name, description, and ordered steps. Each step
            includes a name, description, and optional tools.
          </p>
          <p>
            <strong>Bottom — Eval cases.</strong> Test scenarios the AI generated
            to verify the skill works. You can add, remove, or adjust expected terms.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-stone-100">What to look for</h3>
        <ul className="space-y-2 text-sm text-stone-400">
          <li className="flex gap-2">
            <span className="shrink-0 text-stone-600">--</span>
            <span>Are the steps in the right order? Do they cover the full workflow?</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 text-stone-600">--</span>
            <span>Is each step description clear enough for an AI to follow without ambiguity?</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 text-stone-600">--</span>
            <span>Are the eval cases testing the right things? Add cases for edge cases you care about.</span>
          </li>
          <li className="flex gap-2">
            <span className="shrink-0 text-stone-600">--</span>
            <span>Does the skill name clearly describe what it does? Good names help discovery.</span>
          </li>
        </ul>
      </div>

      <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-2">
        <h3 className="text-sm font-semibold text-stone-100">Publishing</h3>
        <p className="text-sm text-stone-400">
          When you're satisfied, click <strong>Publish</strong>. The skill
          appears on the{' '}
          <Link to="/" className="underline font-medium text-stone-200">
            Skills
          </Link>{' '}
          page and is ready to deploy. You can always <strong>Revise</strong> a
          published skill later — it increments the version and preserves history.
        </p>
      </div>
    </section>
  )
}

function EvalSection() {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-stone-100">Test with Evals</h2>
        <p className="mt-1 text-sm text-stone-500">
          Evals verify your skill produces the right output. Run them before
          deploying and after every revision.
        </p>
      </div>

      <div className="space-y-4">
        <StepBox number={1} title="Review eval cases">
          <p>
            On the skill detail page, expand the <strong>Eval Suite</strong>{' '}
            section. Each case has an input scenario and expected output terms
            (keywords that should appear in the result). Add or remove terms to
            match your quality bar.
          </p>
        </StepBox>

        <StepBox number={2} title="Run evals">
          <p>
            Click <strong>Run Eval</strong>. The AI executes the skill against
            each test case and checks for expected terms. Results show PASS/FAIL
            per case with reasons.
          </p>
        </StepBox>

        <StepBox number={3} title="Iterate">
          <p>
            If cases fail, revise the skill definition (click <strong>Revise</strong>)
            and run evals again. The score history badges show your trend over time
            — aim for green (70%+) before deploying.
          </p>
        </StepBox>
      </div>

      <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">
        <strong>Tip:</strong> Add eval cases for edge cases and failure modes, not
        just the happy path. A skill that handles "I don't have enough information"
        gracefully is more valuable than one that only works on perfect inputs.
      </div>
    </section>
  )
}

function DeploySection() {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-stone-100">Deploy Your Skill</h2>
        <p className="mt-1 text-sm text-stone-500">
          Once published and tested, deploy your skill to any of these targets.
          On the skill detail page, use the <strong>Runtime Adapters</strong>{' '}
          section to generate the right format.
        </p>
      </div>

      <div className="space-y-4">
        <DeployTarget
          title="Claude Code (CLI)"
          badges={['claude_code_skill', 'Recommended']}
        >
          <p>
            Deploy as a slash-command skill in Claude Code. Generated as a
            markdown file that Claude Code loads automatically.
          </p>
          <ol className="space-y-1 text-xs text-stone-400">
            <li>1. On the skill detail page, click <strong>Claude Code Skill</strong></li>
            <li>2. Copy the generated output</li>
            <li>3. Save it to your project's skill directory:</li>
          </ol>
          <CodeBlock title="Save the skill file">
{`# Create the skills directory if it doesn't exist
mkdir -p .claude/skills

# Save the generated output (replace skill-name)
# Paste the output into this file:
.claude/skills/your-skill-name.md`}
          </CodeBlock>
          <p className="text-xs text-stone-500">
            The skill is now available as a slash command in Claude Code.
            Type <code className="rounded bg-stone-800 border border-stone-700 px-1 py-0.5 text-stone-300">/your-skill-name</code> in
            any Claude Code session to use it.
          </p>
        </DeployTarget>

        <DeployTarget
          title="Claude Desktop App"
          badges={['claude_code_skill']}
        >
          <p>
            Use the same Claude Code Skill adapter output. Claude Desktop
            supports project-level skills when Claude Code is installed.
          </p>
          <ol className="space-y-1 text-xs text-stone-400">
            <li>1. Generate the <strong>Claude Code Skill</strong> adapter</li>
            <li>2. In your project folder, save it to <code className="rounded bg-stone-800 border border-stone-700 px-1 py-0.5 text-stone-300">.claude/skills/your-skill-name.md</code></li>
            <li>3. Open the project folder in Claude Desktop</li>
            <li>4. The skill appears as a slash command in the chat</li>
          </ol>
          <div className="rounded-lg border border-orange-400/30 bg-orange-400/10 p-2 text-xs text-orange-300">
            Claude Desktop reads the same <code>.claude/skills/</code> directory
            as the CLI. One skill file works in both.
          </div>
        </DeployTarget>

        <DeployTarget
          title="GitHub Repository"
          badges={['Version control', 'Team sharing']}
        >
          <p>
            Commit your skill files to a repository so the whole team gets them
            automatically.
          </p>
          <CodeBlock title="Add skills to your repo">
{`# Generate the Claude Code Skill adapter, save to file
# Then commit alongside your code:
git add .claude/skills/your-skill-name.md
git commit -m "Add your-skill-name skill from Canopy"
git push

# Team members get the skill on next pull
# Works with Claude Code CLI + Desktop App automatically`}
          </CodeBlock>
          <p className="text-xs text-stone-500">
            Skills committed to a repo are available to anyone who clones it
            and uses Claude Code. No extra setup required.
          </p>
        </DeployTarget>

        <DeployTarget
          title="OpenClaw (Autonomous Agents)"
          badges={['open_claw_prompt']}
        >
          <p>
            Deploy as an autonomous agent prompt for OpenClaw. The adapter
            generates a system prompt with ordered steps that an autonomous
            agent executes without human intervention.
          </p>
          <ol className="space-y-1 text-xs text-stone-400">
            <li>1. On the skill detail page, click <strong>Open Claw Prompt</strong></li>
            <li>2. Copy the generated system prompt</li>
            <li>3. Use it in your OpenClaw configuration:</li>
          </ol>
          <CodeBlock title="OpenClaw agent config">
{`# In your OpenClaw project, use the generated prompt
# as the system prompt for an autonomous agent:

# Option A: Direct CLI usage
claude --system-prompt "$(cat skill-prompt.txt)" --allowedTools "..." \\
  "Execute the skill on this input: ..."

# Option B: As a CLAUDE.md instruction
# Paste the prompt into your project's CLAUDE.md
# The agent picks it up automatically on start`}
          </CodeBlock>
        </DeployTarget>

        <DeployTarget
          title="Web Workflow"
          badges={['web_workflow', 'API integration']}
        >
          <p>
            Deploy as a structured workflow for web applications. The adapter
            generates a JSON definition with UI steps, inputs, and outputs
            that can drive a guided workflow UI.
          </p>
          <ol className="space-y-1 text-xs text-stone-400">
            <li>1. On the skill detail page, click <strong>Web Workflow</strong></li>
            <li>2. Copy the JSON output</li>
            <li>3. Integrate it into your web application's workflow engine</li>
          </ol>
          <p className="text-xs text-stone-500">
            Best for teams building custom AI-powered tools that need structured,
            step-by-step interactions.
          </p>
        </DeployTarget>
      </div>

      <div className="rounded-xl border border-stone-800 bg-stone-900 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-stone-100">Quick reference: which adapter to use</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-800 text-left">
                <th className="py-2 pr-4 font-medium text-stone-200">I want to...</th>
                <th className="py-2 pr-4 font-medium text-stone-200">Use this adapter</th>
                <th className="py-2 font-medium text-stone-200">Output</th>
              </tr>
            </thead>
            <tbody className="text-stone-400">
              <tr className="border-b border-stone-800">
                <td className="py-2 pr-4">Use in Claude Code terminal</td>
                <td className="py-2 pr-4">Claude Code Skill</td>
                <td className="py-2">Markdown file</td>
              </tr>
              <tr className="border-b border-stone-800">
                <td className="py-2 pr-4">Use in Claude Desktop app</td>
                <td className="py-2 pr-4">Claude Code Skill</td>
                <td className="py-2">Markdown file</td>
              </tr>
              <tr className="border-b border-stone-800">
                <td className="py-2 pr-4">Share via GitHub repo</td>
                <td className="py-2 pr-4">Claude Code Skill</td>
                <td className="py-2">Markdown file (commit to repo)</td>
              </tr>
              <tr className="border-b border-stone-800">
                <td className="py-2 pr-4">Run autonomously (OpenClaw)</td>
                <td className="py-2 pr-4">Open Claw Prompt</td>
                <td className="py-2">System prompt text</td>
              </tr>
              <tr>
                <td className="py-2 pr-4">Embed in a web app</td>
                <td className="py-2 pr-4">Web Workflow</td>
                <td className="py-2">JSON definition</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function GuidePage() {
  const [activeSection, setActiveSection] = useState<SectionId>('try-it')

  const sectionComponents: Record<SectionId, React.ReactNode> = {
    'try-it': <TryItSection />,
    overview: <OverviewSection />,
    workspace: <WorkspaceSection />,
    eval: <EvalSection />,
    deploy: <DeploySection />,
  }

  return (
    <div className="flex gap-8">
      {/* Sidebar nav */}
      <div className="w-44 shrink-0">
        <div className="sticky top-24">
          <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-stone-500">
            Guide
          </h3>
          <SectionNav active={activeSection} onSelect={setActiveSection} />
        </div>
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1 max-w-3xl">
        {sectionComponents[activeSection]}
      </div>
    </div>
  )
}
