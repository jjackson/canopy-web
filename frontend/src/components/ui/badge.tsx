import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default:
          "bg-orange-400/10 border border-orange-400/30 text-orange-400 [a]:hover:bg-orange-400/20",
        secondary:
          "bg-stone-800 border border-stone-700 text-stone-300 [a]:hover:bg-stone-700",
        destructive:
          "bg-red-400/10 border border-red-400/30 text-red-400 [a]:hover:bg-red-400/20",
        outline:
          "border border-stone-700 text-stone-300 [a]:hover:bg-stone-800 [a]:hover:text-stone-100",
        ghost:
          "text-stone-400 hover:bg-stone-800 hover:text-stone-200",
        link: "text-orange-400 underline-offset-4 hover:text-orange-300 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
