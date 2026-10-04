import { useEffect, useState } from 'react'

import { API_LABEL, checkHealth, getPromptContext } from '../api/client'
import type { PromptContext, ResponseLanguage } from '../api/types'
import { useT } from '../i18n/useLocale'
import type { SessionInfo } from '../hooks/useSession'
import type { Theme } from '../hooks/useTheme'
import { Chevron, RulerMeasure } from './icons'
import { LanguageToggle } from './LanguageToggle'
import { Markdown } from './Markdown'
import { ThemeToggle } from './ThemeToggle'

interface SidebarProps {
  session: SessionInfo
  busy: boolean
  onNewConversation: () => void
  language: ResponseLanguage
  onLanguageChange: (language: ResponseLanguage) => void
  theme: Theme
  onThemeChange: (theme: Theme) => void
}

export function Sidebar({ session, busy, onNewConversation, language, onLanguageChange, theme, onThemeChange }: SidebarProps) {
  const t = useT()

  return (
    <aside className="flex flex-col gap-7 border-b border-line bg-sidebar px-4 py-5 md:sticky md:top-0 md:h-screen md:gap-8 md:overflow-y-auto md:border-r md:border-b-0 md:px-[22px] md:py-7">
      <div className="flex items-center gap-2.5 font-semibold tracking-[-0.01em]">
        <span className="grid size-[26px] place-items-center rounded-[10px] bg-btn text-btn-ink">
          <RulerMeasure className="size-4" />
        </span>
        {t('brand.name')}
      </div>

      <section>
        <SectionTitle>{t('sidebar.api')}</SectionTitle>
        <ApiStatus />
      </section>

      <SessionPanel session={session} busy={busy} onNewConversation={onNewConversation} />

      <section>
        <SectionTitle>{t('sidebar.cag')}</SectionTitle>
        <p className="text-[12.5px] text-muted">{t('sidebar.cag.hint')}</p>
        <CagExamples />
      </section>

      <div className="flex flex-col gap-7 md:mt-auto md:gap-6">
        <section>
          <SectionTitle>{t('sidebar.language')}</SectionTitle>
          <LanguageToggle value={language} onChange={onLanguageChange} />
          <p className="mt-2 text-[12.5px] text-muted">{t('sidebar.language.hint')}</p>
        </section>

        <section>
          <SectionTitle>{t('sidebar.appearance')}</SectionTitle>
          <ThemeToggle value={theme} onChange={onThemeChange} />
        </section>
      </div>
    </aside>
  )
}

const EM_DASH = '—'

function SessionPanel({ session, busy, onNewConversation }: Pick<SidebarProps, 'session' | 'busy' | 'onNewConversation'>) {
  const t = useT()
  const { id, metadata, turns } = session
  const rows: [string, string][] = [
    [t('sidebar.session.memory.name'), metadata.project_name ?? EM_DASH],
    [t('sidebar.session.memory.team'), metadata.assumed_team_size?.toString() ?? EM_DASH],
    [
      t('sidebar.session.memory.tech'),
      metadata.mentioned_technologies.length > 0 ? metadata.mentioned_technologies.join(', ') : EM_DASH,
    ],
    [t('sidebar.session.memory.scope'), metadata.agreed_scope ?? EM_DASH],
  ]

  return (
    <section>
      <SectionTitle>{t('sidebar.session')}</SectionTitle>
      <span
        title={id ?? undefined}
        className="inline-flex max-w-full items-center gap-2 rounded-full bg-field px-2.5 py-[5px] font-mono text-xs text-muted shadow-[0_0_0_1px_var(--line)]"
      >
        <span className="sr-only">{t('sidebar.session.id')}</span>
        <span className="truncate">{id ? id.slice(0, 8) : EM_DASH}</span>
      </span>

      <div className="mt-3 rounded-[14px] bg-field px-3 py-2.5 shadow-[0_0_0_1px_var(--line)]">
        <h4 className="mb-1.5 text-[13.5px] font-medium">{t('sidebar.session.memory')}</h4>
        <dl className="grid gap-1.5 text-[12.5px]">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-faint">{label}</dt>
              <dd className="text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <p className="mt-2.5 font-mono text-xs text-muted">{t('sidebar.session.turns', { count: turns })}</p>
      <p className="mt-2 text-[12.5px] text-muted">{t('sidebar.session.hint')}</p>

      <button
        type="button"
        onClick={onNewConversation}
        disabled={busy || id === null}
        className="mt-3 inline-flex h-9 cursor-pointer items-center rounded-full bg-field px-4 text-[13.5px] font-medium shadow-[0_0_0_1px_var(--line-strong)] transition-[transform,opacity] duration-150 ease-out-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent enabled:active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-35"
      >
        {t('sidebar.session.new')}
      </button>
    </section>
  )
}

function SectionTitle({ children }: { children: string }) {
  return <h3 className="mb-3 text-[11px] font-semibold tracking-[0.09em] text-faint uppercase">{children}</h3>
}

type Health = 'checking' | 'up' | 'down'

function ApiStatus() {
  const t = useT()
  const [health, setHealth] = useState<Health>('checking')

  useEffect(() => {
    let active = true
    checkHealth().then((ok) => active && setHealth(ok ? 'up' : 'down'))
    return () => {
      active = false
    }
  }, [])

  const dot = {
    checking: 'bg-faint',
    up: 'bg-ok shadow-[0_0_0_3px_color-mix(in_srgb,var(--ok)_18%,transparent),0_0_10px_color-mix(in_srgb,var(--ok)_60%,transparent)]',
    down: 'bg-danger',
  }[health]
  const label = { checking: t('api.checking'), up: t('api.up'), down: t('api.down') }[health]

  return (
    <span
      title={label}
      className="inline-flex max-w-full items-center gap-2 rounded-full bg-field px-2.5 py-[5px] font-mono text-xs text-muted shadow-[0_0_0_1px_var(--line)]"
    >
      <i className={`size-1.5 flex-none rounded-full ${dot}`} aria-hidden="true" />
      <span className="truncate">{API_LABEL}</span>
      <span className="sr-only">{label}</span>
    </span>
  )
}

function CagExamples() {
  const t = useT()
  const [context, setContext] = useState<PromptContext | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getPromptContext()
      .then(setContext)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  return (
    <details className="group mt-3 rounded-[14px] bg-field shadow-[0_0_0_1px_var(--line)]">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-[13.5px] font-medium [&::-webkit-details-marker]:hidden">
        <span>
          {t('sidebar.examples')}
          {context && <span className="ml-2 font-mono text-[11px] font-normal text-faint">{context.prompt_version}</span>}
        </span>
        <Chevron className="size-3 text-faint transition-transform duration-200 ease-out-strong group-open:rotate-180 motion-reduce:transition-none" />
      </summary>
      <div className="max-h-[46vh] overflow-y-auto border-t border-line px-3 pt-1 pb-3">
        {error && <p className="pt-2 text-xs text-danger">{error}</p>}
        {!error && !context && <p className="pt-2 text-xs text-faint">{t('sidebar.examples.loading')}</p>}
        {context && <Markdown className="md-compact" breaks={false}>{context.examples_markdown}</Markdown>}
      </div>
    </details>
  )
}
