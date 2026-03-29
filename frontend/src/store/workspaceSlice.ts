import { create } from 'zustand'

interface WorkspaceState {
  sessionId: number | null
  status: string
  approach: Record<string, unknown> | null
  evalCases: Record<string, unknown>[]
  skillDraft: Record<string, unknown> | null
  streamingText: string
  isStreaming: boolean
  sources: Record<string, unknown>[]

  setSession: (id: number) => void
  setStatus: (status: string) => void
  setApproach: (approach: Record<string, unknown>) => void
  setEvalCases: (cases: Record<string, unknown>[]) => void
  setSkillDraft: (draft: Record<string, unknown>) => void
  appendStreamingText: (text: string) => void
  clearStreamingText: () => void
  setIsStreaming: (streaming: boolean) => void
  setSources: (sources: Record<string, unknown>[]) => void
  reset: () => void
}

const initialState = {
  sessionId: null as number | null,
  status: '',
  approach: null as Record<string, unknown> | null,
  evalCases: [] as Record<string, unknown>[],
  skillDraft: null as Record<string, unknown> | null,
  streamingText: '',
  isStreaming: false,
  sources: [] as Record<string, unknown>[],
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  ...initialState,

  setSession: (id) => set({ sessionId: id }),
  setStatus: (status) => set({ status }),
  setApproach: (approach) => set({ approach }),
  setEvalCases: (cases) => set({ evalCases: cases }),
  setSkillDraft: (draft) => set({ skillDraft: draft }),
  appendStreamingText: (text) =>
    set((state) => ({ streamingText: state.streamingText + text })),
  clearStreamingText: () => set({ streamingText: '' }),
  setIsStreaming: (streaming) => set({ isStreaming: streaming }),
  setSources: (sources) => set({ sources }),
  reset: () => set(initialState),
}))
