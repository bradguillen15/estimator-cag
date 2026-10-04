import { useEffect, useRef, useState } from 'react'

import type { GenerationMeta } from '../api/types'
import type { EstimationState } from '../hooks/useSession'
import { useT } from '../i18n/useLocale'
import { Check, Copy } from './icons'
import { Markdown } from './Markdown'
import { Tooltip } from './Tooltip'

const COPIED_FEEDBACK_MS = 1600

export function EstimationResult({ state }: { state: EstimationState }) {
  const t = useT()

  if (state.status === 'idle') return null

  if (state.status === 'error') {
    return (
      <div
        role="alert"
        className="mt-5 animate-enter rounded-[14px] bg-danger-soft px-4 py-3.5 text-[13.5px] text-danger shadow-[0_0_0_1px_color-mix(in_srgb,var(--danger)_25%,transparent)]"
      >
        {state.error}
      </div>
    )
  }

  return (
    <section
      className="mt-12 animate-enter"
      aria-labelledby="estimation-heading"
      aria-live="polite"
      aria-busy={state.status !== 'done'}
    >
      <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="estimation-heading" className="text-[26px] font-bold tracking-[-0.03em]">
          {t('result.heading')}
        </h2>
        <div className="flex items-center gap-2">
          {state.meta && <MetaChips meta={state.meta} />}
          {state.status === 'done' && state.text && <CopyButton text={state.text} />}
        </div>
      </div>
      <article className="rounded-[22px] bg-surface p-5 shadow-card md:p-7">
        {state.status === 'loading' ? (
          <Skeleton label={t('result.generating')} />
        ) : (
          <Markdown>{state.text}</Markdown>
        )}
      </article>
    </section>
  )
}

function CopyButton({ text }: { text: string }) {
  const t = useT()
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      return
    }
    setCopied(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setCopied(false), COPIED_FEEDBACK_MS)
  }

  const label = copied ? t('result.copied') : t('result.copy')
  return (
    <Tooltip label={label} side="top" align="end">
      <button
        type="button"
        onClick={copy}
        aria-label={label}
        className="grid size-8 cursor-pointer place-items-center rounded-full bg-field text-muted shadow-[0_0_0_1px_var(--line-strong)] transition-[transform,color] duration-150 ease-out-strong hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent active:scale-[0.97]"
      >
        {copied ? <Check className="size-4 text-accent" /> : <Copy className="size-4" />}
      </button>
    </Tooltip>
  )
}

function MetaChips({ meta }: { meta: GenerationMeta }) {
  const t = useT()
  return (
    <div className="flex flex-wrap gap-1.5">
      {meta.cache_hit && (
        <span className="rounded-full bg-accent-soft px-[9px] py-[3px] font-mono text-[11.5px] font-medium text-accent shadow-[0_0_0_1px_color-mix(in_srgb,var(--accent)_30%,transparent)]">
          {t('result.cached')}
        </span>
      )}
      <span className="rounded-full bg-field px-[9px] py-[3px] font-mono text-[11.5px] text-muted shadow-[0_0_0_1px_var(--line)]">
        prompt_version <b className="font-medium text-ink">{meta.prompt_version}</b>
      </span>
    </div>
  )
}

function Skeleton({ label }: { label: string }) {
  const bar = 'h-3 rounded-md bg-[linear-gradient(90deg,var(--accent-soft),transparent_60%,var(--accent-soft))] bg-size-[200%_100%] animate-shimmer'
  return (
    <div className="grid gap-2.5" aria-label={label}>
      <span className={`${bar} h-[18px] w-[45%]`} />
      <span className={`${bar} w-[90%]`} />
      <span className={`${bar} w-3/4`} />
      <span className={`${bar} w-[82%]`} />
    </div>
  )
}
