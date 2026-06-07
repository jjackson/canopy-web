/**
 * Coordination between the run package (which owns the section content + scroll
 * position) and the left rail (which lists the sections as jump links and
 * highlights the one you're looking at).
 *
 * The package registers the sections it actually rendered and reports the
 * active one via scroll-spy; the rail reads that and calls {@link jump} to
 * scroll-to-section. Kept in context so neither component has to re-fetch the
 * run or thread props through the shell.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

export interface RunSection {
  id: string
  label: string
}

/** DOM id for a run section anchor, so the rail and package agree on targets. */
export function runSectionDomId(id: string): string {
  return `run-section-${id}`
}

interface RunSectionNavValue {
  sections: RunSection[]
  activeId: string | null
  setSections: (sections: RunSection[]) => void
  setActiveId: (id: string | null) => void
  jump: (id: string) => void
}

const RunSectionNavContext = createContext<RunSectionNavValue | null>(null)

export function RunSectionNavProvider({ children }: { children: ReactNode }) {
  const [sections, setSections] = useState<RunSection[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)

  const jump = useCallback((id: string) => {
    const el = document.getElementById(runSectionDomId(id))
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // Reflect the click immediately; scroll-spy will keep it honest after.
    setActiveId(id)
  }, [])

  const value = useMemo(
    () => ({ sections, activeId, setSections, setActiveId, jump }),
    [sections, activeId, jump],
  )

  return (
    <RunSectionNavContext.Provider value={value}>
      {children}
    </RunSectionNavContext.Provider>
  )
}

/** Returns the nav context, or null when rendered outside a provider. */
export function useRunSectionNav(): RunSectionNavValue | null {
  return useContext(RunSectionNavContext)
}
