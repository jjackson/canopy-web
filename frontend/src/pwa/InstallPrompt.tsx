import { useEffect, useState, type JSX } from 'react'

// Chrome fires this when the app is installable; the event is not in lib.dom.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/**
 * Android lets us offer installation; iOS does not (you'd dig through the share
 * sheet). Chrome fires `beforeinstallprompt` only when the app QUALIFIES and
 * isn't already installed — so rendering nothing until it fires is exactly
 * right: no button that lies, and it disappears once installed.
 */
export function InstallPrompt(): JSX.Element | null {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault() // stop Chrome's own mini-infobar; we place the button
      setDeferred(e as BeforeInstallPromptEvent)
    }
    const onInstalled = () => setDeferred(null)
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  if (!deferred) return null

  return (
    <button
      type="button"
      data-testid="install-prompt"
      onClick={async () => {
        await deferred.prompt()
        await deferred.userChoice
        setDeferred(null) // single-use: the event can't be prompted twice
      }}
      className="w-full rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-[13px] font-medium text-primary transition-colors hover:bg-primary/20"
    >
      Install Canopy on this device
    </button>
  )
}
