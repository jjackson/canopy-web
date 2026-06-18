import { useCallback, useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { listAgentTasks, listPendingCommands, type AgentTaskOut } from '@/api/agents'
import type { AgentOutletContext } from '@/pages/AgentWorkspacePage'
import { TasksBoard } from '@/components/TasksBoard'
import { WorkbenchSubHeader, WorkbenchSkeleton } from '@canopy/workbench'

export function AgentTasksSection() {
  const { agent } = useOutletContext<AgentOutletContext>()
  const [tasks, setTasks] = useState<AgentTaskOut[] | null>(null)
  const [pendingCount, setPendingCount] = useState(0)

  // Refetch tasks + the pending-command count. Passed to the board as
  // `onChanged` so an Accept/Decline/Dispatch/Done refreshes the whole board.
  const reload = useCallback(() => {
    let cancelled = false
    listAgentTasks(agent.slug)
      .then((list) => !cancelled && setTasks(list))
      .catch(() => !cancelled && setTasks([]))
    listPendingCommands(agent.slug)
      .then((cmds) => !cancelled && setPendingCount(cmds.length))
      .catch(() => !cancelled && setPendingCount(0))
    return () => {
      cancelled = true
    }
  }, [agent.slug])

  useEffect(() => {
    setTasks(null)
    setPendingCount(0)
    const cleanup = reload()
    return cleanup
  }, [reload])

  return (
    <div className="max-w-4xl px-6 py-8">
      <WorkbenchSubHeader title="Task board" count={tasks?.length} />
      {tasks === null ? (
        <WorkbenchSkeleton />
      ) : (
        <TasksBoard tasks={tasks} onChanged={reload} pendingCount={pendingCount} />
      )}
    </div>
  )
}
