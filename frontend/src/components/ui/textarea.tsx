import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-lg border border-stone-700 bg-stone-950 px-2.5 py-2 text-sm text-stone-200 transition-colors outline-none placeholder:text-stone-600 focus-visible:border-orange-400/50 focus-visible:ring-2 focus-visible:ring-orange-400/20 disabled:cursor-not-allowed disabled:bg-stone-900 disabled:opacity-60 aria-invalid:border-red-400/50 aria-invalid:ring-2 aria-invalid:ring-red-400/20",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
