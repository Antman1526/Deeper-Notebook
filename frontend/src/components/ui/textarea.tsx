import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      // v0.8.130 — no box-shadow focus ring; the global 3px outline is the one ring.
      className={cn(
        "border-input placeholder:text-muted-foreground focus-visible:border-ring aria-invalid:border-destructive dark:bg-input/30 flex field-sizing-content min-h-16 min-w-0 w-full rounded-md border bg-transparent px-3 py-2 text-base transition-[color,border-color] outline-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
