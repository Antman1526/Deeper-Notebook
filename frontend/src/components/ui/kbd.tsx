import * as React from "react"

import { cn } from "@/lib/utils"

// v0.8.130 — one keyboard-key chip. Five places hand-rolled their own (one at
// 10px, one unstyled), each with different padding, border and radius.
function Kbd({ className, ...props }: React.ComponentProps<"kbd">) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "pointer-events-none inline-flex h-5 min-w-5 select-none items-center justify-center gap-0.5 rounded-sm border border-border bg-muted px-1.5 font-mono text-xs font-medium text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

export { Kbd }
