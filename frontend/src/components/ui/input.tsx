import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-stone-700 bg-stone-950 px-2.5 py-1 text-sm text-stone-200 transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-stone-200 placeholder:text-stone-600 focus-visible:border-orange-400/50 focus-visible:ring-2 focus-visible:ring-orange-400/20 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-stone-900 disabled:opacity-60 aria-invalid:border-red-400/50 aria-invalid:ring-2 aria-invalid:ring-red-400/20",
        className
      )}
      {...props}
    />
  )
}

export { Input }
