import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentTasks, listAgentCommands, type AgentCommandOut, type AgentTaskOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { TasksBoard } from '@/components/TasksBoard'
import { WorkbenchSubHeader, WorkbenchSkeleton } from '@marshellis/workbench'

export function AgentTasksSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [tasks, setTasks] = useState<AgentTaskOut[] | null>(null)
  const [commands, setCommands] = useState<AgentCommandOut[]>([])

  // Refetch tasks + the full command stream (queue + applied history). Passed to
  // the board as `onChanged` so an Accept/Decline/Dispatch/Done refreshes both
  // the cards and the activity surfaces.
  const reload = useCallback(() => {
    let cancelled = false
    listAgentTasks(agent.slug)
      .then((list) => !cancelled && setTasks(list))
      .catch(() => !cancelled && setTasks([]))
    listAgentCommands(agent.slug)
      .then((cmds) => !cancelled && setCommands(cmds))
      .catch(() => !cancelled && setCommands([]))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  useEffect(() => {
    setTasks(null)
    setCommands([])
    const cleanup = reload()
    return cleanup
  }, [reload])

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader title="Task board" count={tasks?.length} />
      {tasks === null ? (
        <WorkbenchSkeleton />
      ) : (
        <TasksBoard tasks={tasks} onChanged={reload} commands={commands} />
      )}
    </div>
  )
}
