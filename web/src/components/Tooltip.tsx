import type { ReactNode } from 'react'

type Side = 'top' | 'bottom'
type Align = 'start' | 'center' | 'end'

interface TooltipProps {
  label: string
  side?: Side
  align?: Align
  children: ReactNode
}

const SIDE: Record<Side, string> = {
  top: 'bottom-full mb-2',
  bottom: 'top-full mt-2',
}

const ALIGN: Record<Align, string> = {
  start: 'left-0',
  center: 'left-1/2 -translate-x-1/2',
  end: 'right-0',
}

// Scale from the corner closest to the trigger.
const ORIGIN: Record<Side, Record<Align, string>> = {
  top: { start: 'origin-bottom-left', center: 'origin-bottom', end: 'origin-bottom-right' },
  bottom: { start: 'origin-top-left', center: 'origin-top', end: 'origin-top-right' },
}

/**
 * Hover/keyboard-focus tooltip for icon-only controls. Visual only (aria-hidden):
 * the trigger must carry its own accessible name. Delayed in, instant out.
 */
export function Tooltip({ label, side = 'top', align = 'center', children }: TooltipProps) {
  return (
    <span className="group/tip relative inline-flex">
      {children}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute z-20 rounded-lg bg-sidebar px-2 py-1 text-[11.5px] font-medium whitespace-nowrap text-ink opacity-0 shadow-[0_0_0_1px_var(--line-strong),0_6px_16px_rgb(0_0_0/0.18)] transition-[opacity,scale] duration-[125ms] ease-out-strong scale-[0.97] group-hover/tip:scale-100 group-hover/tip:opacity-100 group-hover/tip:delay-[450ms] group-has-[:focus-visible]/tip:scale-100 group-has-[:focus-visible]/tip:opacity-100 motion-reduce:scale-100 ${SIDE[side]} ${ALIGN[align]} ${ORIGIN[side][align]}`}
      >
        {label}
      </span>
    </span>
  )
}
