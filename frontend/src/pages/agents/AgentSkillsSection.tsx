import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentSkills, type AgentSkillOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { SkillCard } from '@/components/agents/cards'
import { SectionSubHeader, SectionSkeleton } from '@/components/agents/SectionSubHeader'

export function AgentSkillsSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [skills, setSkills] = useState<AgentSkillOut[] | null>(null)

  useEffect(() => {
    let cancelled = false
    setSkills(null)
    listAgentSkills(agent.slug)
      .then((list) => !cancelled && setSkills(list))
      .catch(() => !cancelled && setSkills([]))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  return (
    <div className="max-w-4xl px-6 py-8">
      <SectionSubHeader title="Skills" count={skills?.length} />
      {skills === null ? (
        <SectionSkeleton />
      ) : skills.length === 0 ? (
        <p className="text-[13px] text-stone-600">No skills yet.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {skills.map((sk) => (
            <SkillCard key={sk.id} skill={sk} />
          ))}
        </div>
      )}
    </div>
  )
}
