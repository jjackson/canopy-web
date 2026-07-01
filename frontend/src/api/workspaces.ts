// Workspaces API — the tenant list backing the header switcher + provider.
import { apiV2 } from './client.v2'
import type { components } from './generated'

export type WorkspaceOut = components['schemas']['WorkspaceOut']

export async function listWorkspaces(): Promise<WorkspaceOut[]> {
  const { data } = await apiV2.GET('/api/workspaces/')
  return (data as unknown as WorkspaceOut[]) ?? []
}
