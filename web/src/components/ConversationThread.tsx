import { useEffect, useRef } from 'react'

import type { PendingTurn, ThreadTurn } from '../hooks/useSession'
import { useT } from '../i18n/useLocale'
import { ErrorAlert, EstimationResult } from './EstimationResult'
import { Paperclip } from './icons'

interface ConversationThreadProps {
  turns: ThreadTurn[]
  pending: PendingTurn | null
}

/** The session as a conversation, oldest first: each turn is the user's message and its estimate. */
export function ConversationThread({ turns, pending }: ConversationThreadProps) {
  const t = useT()
  const lastRef = useRef<HTMLDivElement>(null)
  const shownRef = useRef(turns.length + (pending ? 1 : 0))
  const count = turns.length + (pending ? 1 : 0)

  // Bring a newly added turn into view; a thread rebuilt on load/switch stays where it is.
  useEffect(() => {
    const grew = count > shownRef.current
    shownRef.current = count
    if (!grew) return
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    lastRef.current?.scrollIntoView?.({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  }, [count])

  if (count === 0) return null

  return (
    <section aria-label={t('thread.label')} className="mb-8">
      {turns.map((turn, index) => (
        <div key={index} ref={!pending && index === turns.length - 1 ? lastRef : undefined} className="scroll-mt-6">
          <UserMessage description={turn.description} attachmentNames={turn.attachmentNames} />
          <EstimationResult state={{ status: 'done', text: turn.text, meta: turn.meta }} />
        </div>
      ))}
      {pending && (
        <div ref={lastRef} className="scroll-mt-6">
          <UserMessage description={pending.description} attachmentNames={pending.attachmentNames} />
          {pending.status === 'error' ? (
            <ErrorAlert message={pending.error ?? ''} />
          ) : (
            <EstimationResult state={{ status: 'loading' }} />
          )}
        </div>
      )}
    </section>
  )
}

function UserMessage({ description, attachmentNames }: { description: string; attachmentNames: string[] }) {
  const t = useT()
  return (
    <div className="mt-8 flex animate-enter flex-col items-end first:mt-0">
      <span className="mb-1 mr-1 text-[11.5px] font-medium text-faint">{t('thread.you')}</span>
      <div className="max-w-[88%] rounded-[18px] rounded-br-md bg-accent-soft px-4 py-3 text-[14.5px] leading-relaxed whitespace-pre-wrap break-words">
        {description}
      </div>
      {attachmentNames.length > 0 && (
        <ul className="mt-1.5 flex max-w-[88%] flex-wrap justify-end gap-1.5">
          {attachmentNames.map((name, index) => (
            <li
              key={`${name}-${index}`}
              className="inline-flex items-center gap-1.5 rounded-full bg-field px-2.5 py-1 font-mono text-[11.5px] text-muted shadow-[0_0_0_1px_var(--line)]"
            >
              <Paperclip className="size-3 flex-none" />
              <span className="truncate">{name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
