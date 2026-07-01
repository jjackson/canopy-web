// Workspace (tenant) context. The active workspace is driven by the URL's
// :workspace segment (source of truth); this provider fetches the caller's
// memberships so the header switcher can render and so a bare/legacy route can
// redirect to a sensible default.
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { listWorkspaces, type WorkspaceOut } from '../api/workspaces'
import { resolveActiveWorkspace } from './resolveActiveWorkspace'

interface WorkspaceCtx {
  workspaces: WorkspaceOut[]
  active: string | null
  loading: boolean
}

const Ctx = createContext<WorkspaceCtx | null>(null)

export function WorkspaceProvider({
  urlSlug,
  children,
}: {
  urlSlug: string | null
  children: ReactNode
}) {
  const [workspaces, setWorkspaces] = useState<WorkspaceOut[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    listWorkspaces()
      .then((ws) => {
        if (live) setWorkspaces(ws)
      })
      .finally(() => {
        if (live) setLoading(false)
      })
    return () => {
      live = false
    }
  }, [])

  const active = resolveActiveWorkspace(workspaces, urlSlug)
  return <Ctx.Provider value={{ workspaces, active, loading }}>{children}</Ctx.Provider>
}

export function useWorkspace(): WorkspaceCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider')
  return ctx
}
