import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentTasks, type AgentTaskOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { TasksBoard } from '@/components/TasksBoard'
import { WorkbenchSubHeader, WorkbenchSkeleton } from '@canopy/workbench'

export function AgentTasksSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [tasks, setTasks] = useState<AgentTaskOut[] | null>(null)

  useEffect(() => {
    let cancelled = false
    setTasks(null)
    listAgentTasks(agent.slug)
      .then((list) => !cancelled && setTasks(list))
      .catch(() => !cancelled && setTasks([]))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader title="Task board" count={tasks?.length} />
      {tasks === null ? (
        <WorkbenchSkeleton />
      ) : tasks.length === 0 ? (
        <p className="text-[13px] text-stone-600">No tasks yet.</p>
      ) : (
        <TasksBoard tasks={tasks} />
      )}
    </div>
  )
}
