import type { ReactNode } from 'react'

import { Tooltip } from './Tooltip'

export interface SegmentOption<T extends string> {
  value: T
  label: string
  icon?: ReactNode
}

interface SegmentedControlProps<T extends string> {
  /** Radio group name; must be unique on the page. */
  name: string
  label: string
  value: T
  options: SegmentOption<T>[]
  onChange: (value: T) => void
  /** Icon/code only; the label moves to a tooltip and stays available to assistive tech. */
  compact?: boolean
}

/** Pill-shaped radio group used for the sidebar preferences (theme, language). */
export function SegmentedControl<T extends string>({ name, label, value, options, onChange, compact = false }: SegmentedControlProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="grid auto-cols-fr grid-flow-col rounded-full bg-field p-[3px] shadow-[0_0_0_1px_var(--line)]"
    >
      {options.map((option, index) => {
        const segment = (
          <label key={option.value} className="relative">
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="peer absolute opacity-0"
            />
            <span className={`flex h-7 cursor-pointer items-center justify-center gap-1.5 ${compact ? 'min-w-9 px-2' : ''} rounded-full text-[12.5px] text-muted transition-colors duration-150 peer-checked:bg-accent-soft peer-checked:text-accent peer-checked:shadow-[0_0_0_1px_color-mix(in_srgb,var(--accent)_35%,transparent)] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-1 peer-focus-visible:outline-accent hover:text-ink`}>
              {option.icon}
              {compact ? <span className="sr-only">{option.label}</span> : option.label}
            </span>
          </label>
        )
        if (!compact) return segment
        // The last segment sits near the sidebar edge: anchor its tooltip to the right.
        const align = index === options.length - 1 ? 'end' : 'center'
        return (
          <Tooltip key={option.value} label={option.label} side="top" align={align}>
            {segment}
          </Tooltip>
        )
      })}
    </div>
  )
}
