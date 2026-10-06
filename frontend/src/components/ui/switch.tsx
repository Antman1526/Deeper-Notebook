import * as React from "react"

import { cn } from "@/lib/utils"

type SwitchProps = Omit<React.ComponentProps<"button">, "onChange" | "type" | "role"> & {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}

// v0.8.130 — on/off control (UI audit 4.3). A native <button role="switch">, so
// Space and Enter work without key handling and it never submits a form. Settings
// used an outline Button with role="switch", which looked like any other button.
function Switch({ checked, onCheckedChange, className, onClick, disabled, ...props }: SwitchProps) {
  const state = checked ? "checked" : "unchecked"
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      data-slot="switch"
      data-state={state}
      disabled={disabled}
      onClick={(event) => {
        onClick?.(event)
        if (!event.defaultPrevented) onCheckedChange(!checked)
      }}
      className={cn(
        "inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-transparent p-0.5 transition-colors outline-none disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-foreground/25",
        className
      )}
      {...props}
    >
      <span
        data-slot="switch-thumb"
        data-state={state}
        className="pointer-events-none block size-5 rounded-full bg-background shadow-sm transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0"
      />
    </button>
  )
}

export { Switch }
