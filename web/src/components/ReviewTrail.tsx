import type { CriticIssue, CriticVerdict, ReviewIteration } from '../api/types'
import { useT } from '../i18n/useLocale'

const VERDICT_STYLE: Record<CriticVerdict, string> = {
  accept: 'bg-accent-soft text-accent',
  needs_iteration: 'bg-field text-ink',
  reject: 'bg-danger-soft text-danger',
}

const SEVERITY_STYLE: Record<CriticIssue['severity'], string> = {
  critical: 'bg-danger-soft text-danger',
  major: 'bg-accent-soft text-accent',
  minor: 'bg-field text-muted',
}

const SEVERITY_ORDER: CriticIssue['severity'][] = ['critical', 'major', 'minor']

const CHIP = 'rounded-full px-[9px] py-[3px] text-[11.5px] font-medium shadow-[0_0_0_1px_var(--line)]'

/** Final outcome of the critic review loop for a turn. */
export function VerdictBadge({ verdict }: { verdict: CriticVerdict }) {
  const t = useT()
  return <span className={`${CHIP} ${VERDICT_STYLE[verdict]}`}>{t(`verdict.${verdict}`)}</span>
}

/** Collapsible list of the actor attempts: the critic's verdict and issues (most severe first) for each. */
export function ReviewTrail({ iterations }: { iterations: ReviewIteration[] }) {
  const t = useT()
  return (
    <details className="mt-3 rounded-[14px] bg-surface px-4 py-3 shadow-card">
      <summary className="cursor-pointer text-[13px] font-medium">{t('review.trail')}</summary>
      <ol className="mt-3 grid gap-3">
        {iterations.map((iteration) => (
          <li key={iteration.attempt} className="text-[13px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t('review.attempt', { attempt: iteration.attempt })}</span>
              <VerdictBadge verdict={iteration.verdict} />
            </div>
            {iteration.issues.length === 0 ? (
              <p className="mt-1.5 text-xs text-faint">{t('review.noIssues')}</p>
            ) : (
              <ul className="mt-1.5 grid gap-1.5">
                {[...iteration.issues]
                  .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
                  .map((issue, index) => (
                    <li key={index} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className={`${CHIP} ${SEVERITY_STYLE[issue.severity]}`}>{t(`severity.${issue.severity}`)}</span>
                      <span className="text-xs font-medium text-muted">{t(`issue.${issue.category}`)}</span>
                      <span className="text-muted">{issue.message}</span>
                    </li>
                  ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </details>
  )
}
