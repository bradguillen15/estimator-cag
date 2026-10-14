import { type ReactNode, useEffect, useState } from 'react'

import { API_LABEL, checkHealth, getPromptContext } from '../api/client'
import type { ProjectMetadata, PromptContext, ResponseLanguage, SessionSummary } from '../api/types'
import { useT } from '../i18n/useLocale'
import type { SessionInfo } from '../hooks/useSession'
import type { Theme } from '../hooks/useTheme'
import { Chevron, Plus, RulerMeasure } from './icons'
import { LanguageToggle } from './LanguageToggle'
import { Markdown } from './Markdown'
import { ThemeToggle } from './ThemeToggle'
import { Tooltip } from './Tooltip'

interface SidebarProps {
  session: SessionInfo
  sessions: SessionSummary[]
  busy: boolean
  onNewConversation: () => void
  onSelectSession: (id: string) => void
  language: ResponseLanguage
  onLanguageChange: (language: ResponseLanguage) => void
  theme: Theme
  onThemeChange: (theme: Theme) => void
}

export function Sidebar({
  session,
  sessions,
  busy,
  onNewConversation,
  onSelectSession,
  language,
  onLanguageChange,
  theme,
  onThemeChange,
}: SidebarProps) {
  const t = useT()

  return (
    <aside className="flex flex-col gap-6 border-b border-line bg-sidebar px-4 py-5 md:sticky md:top-0 md:h-screen md:gap-6 md:overflow-y-auto md:border-r md:border-b-0 md:px-[22px] md:py-7">
      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5 font-semibold tracking-[-0.01em]">
            <span className="grid size-[26px] place-items-center rounded-[10px] bg-btn text-btn-ink">
              <RulerMeasure className="size-4" />
            </span>
            {t('brand.name')}
          </div>
          <Tooltip label={t('sidebar.session.new')} side="bottom" align="end">
            <button
              type="button"
              onClick={onNewConversation}
              disabled={busy || session.id === null}
              aria-label={t('sidebar.session.new')}
              className="grid size-8 cursor-pointer place-items-center rounded-full bg-field text-muted shadow-[0_0_0_1px_var(--line-strong)] transition-[transform,opacity] duration-150 ease-out-strong hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent enabled:active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-35"
            >
              <Plus className="size-4" />
            </button>
          </Tooltip>
        </div>
        <SessionMeta session={session} />
      </div>

      <SessionList sessions={sessions} activeId={session.id} busy={busy} onSelect={onSelectSession} />

      <MemoryPanel metadata={session.metadata} />

      <section>
        <SectionTitle hint={t('sidebar.cag.hint')}>{t('sidebar.cag')}</SectionTitle>
        <CagExamples />
      </section>

      <div className="flex items-center justify-between gap-2 md:mt-auto">
        <ApiStatus />
        <div className="flex items-center gap-2">
          <LanguageToggle value={language} onChange={onLanguageChange} compact />
          <ThemeToggle value={theme} onChange={onThemeChange} compact />
        </div>
      </div>
    </aside>
  )
}

const EM_DASH = '—'

function SessionMeta({ session }: { session: SessionInfo }) {
  const t = useT()
  const { id, turns } = session
  return (
    <p title={id ?? undefined} className="font-mono text-xs text-muted">
      <span className="sr-only">{t('sidebar.session.id')}</span>
      <span>{id ? id.slice(0, 8) : EM_DASH}</span>
      {' · '}
      <span>{t(turns === 1 ? 'sidebar.session.turnsShort.one' : 'sidebar.session.turnsShort', { count: turns })}</span>
    </p>
  )
}

interface SessionListProps {
  sessions: SessionSummary[]
  activeId: string | null
  busy: boolean
  onSelect: (id: string) => void
}

function SessionList({ sessions, activeId, busy, onSelect }: SessionListProps) {
  const t = useT()
  if (sessions.length === 0) return null

  return (
    <section>
      <SectionTitle>{t('sidebar.sessions')}</SectionTitle>
      <ul className="-mx-1 flex max-h-[30vh] flex-col gap-1 overflow-y-auto px-1 py-1">
        {sessions.map((item) => {
          const active = item.session_id === activeId
          const title = item.project_name ?? `${t('sidebar.sessions.untitled')} · ${item.session_id.slice(0, 8)}`
          return (
            <li key={item.session_id}>
              <button
                type="button"
                onClick={() => onSelect(item.session_id)}
                disabled={busy}
                aria-current={active ? 'true' : undefined}
                className={`flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-[14px] px-3 py-2 text-left transition-[background-color,box-shadow,transform] duration-150 ease-out-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50 enabled:active:scale-[0.98] ${
                  active ? 'bg-field shadow-[0_0_0_1px_var(--line-strong)]' : 'hover:bg-field'
                }`}
              >
                <span className="w-full truncate text-[13px] font-medium text-ink">{title}</span>
                <span className="font-mono text-[11px] text-muted">
                  {t(item.history_turns === 1 ? 'sidebar.session.turnsShort.one' : 'sidebar.session.turnsShort', {
                    count: item.history_turns,
                  })}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function MemoryPanel({ metadata }: { metadata: ProjectMetadata }) {
  const t = useT()
  // Facts present on first mount must not flash; any later appearance or change does.
  const [settled, setSettled] = useState(false)
  useEffect(() => setSettled(true), [])
  const flash = settled ? 'memory-flash' : ''

  const { project_name, assumed_team_size, mentioned_technologies, agreed_scope } = metadata
  const empty = !project_name && assumed_team_size === null && mentioned_technologies.length === 0 && !agreed_scope

  return (
    <section>
      <SectionTitle>{t('sidebar.session.memory')}</SectionTitle>
      <div className="rounded-[14px] bg-field px-3 py-3 shadow-[0_0_0_1px_var(--line)]">
        {empty ? (
          <p className="text-[12.5px] text-faint">{t('sidebar.session.memory.empty')}</p>
        ) : (
          <dl className="flex flex-col gap-3 text-[13px]">
            {project_name && (
              <Fact label={t('sidebar.session.memory.name')}>
                <span key={project_name} className={`-mx-1 rounded px-1 font-medium break-words ${flash}`}>
                  {project_name}
                </span>
              </Fact>
            )}
            {assumed_team_size !== null && (
              <Fact label={t('sidebar.session.memory.team')}>
                <span key={assumed_team_size} className={`-mx-1 rounded px-1 ${flash}`}>
                  {t(assumed_team_size === 1 ? 'sidebar.session.memory.teamSize.one' : 'sidebar.session.memory.teamSize', {
                    count: assumed_team_size,
                  })}
                </span>
              </Fact>
            )}
            {mentioned_technologies.length > 0 && (
              <Fact label={t('sidebar.session.memory.tech')}>
                <ul className="flex flex-wrap gap-1">
                  {mentioned_technologies.map((tech) => (
                    <li
                      key={tech}
                      className={`rounded-full bg-sidebar px-2 py-[2px] text-[11.5px] text-ink shadow-[0_0_0_1px_var(--line)] ${flash}`}
                    >
                      {tech}
                    </li>
                  ))}
                </ul>
              </Fact>
            )}
            {agreed_scope && (
              <Fact label={t('sidebar.session.memory.scope')}>
                <ClampedText key={agreed_scope} className={flash}>
                  {agreed_scope}
                </ClampedText>
              </Fact>
            )}
          </dl>
        )}
      </div>
    </section>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-[11px] text-faint">{label}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  )
}

// Rough length past which three lines in the sidebar overflow; avoids measuring the DOM.
const CLAMP_THRESHOLD = 120

function ClampedText({ children, className = '' }: { children: string; className?: string }) {
  const t = useT()
  const [expanded, setExpanded] = useState(false)
  const clampable = children.length > CLAMP_THRESHOLD

  return (
    <>
      <p className={`-mx-1 rounded px-1 leading-[1.5] break-words text-muted ${clampable && !expanded ? 'line-clamp-3' : ''} ${className}`}>
        {children}
      </p>
      {clampable && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="mt-1 cursor-pointer text-[11.5px] font-medium text-accent hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {t(expanded ? 'sidebar.session.memory.less' : 'sidebar.session.memory.more')}
        </button>
      )}
    </>
  )
}

function SectionTitle({ children, hint }: { children: string; hint?: string }) {
  return (
    <h3 title={hint} className="mb-3 text-[11px] font-semibold tracking-[0.09em] text-faint uppercase">
      {children}
    </h3>
  )
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
    <span title={`${API_LABEL} · ${label}`} className="inline-flex items-center">
      <i className={`size-2 flex-none rounded-full ${dot}`} aria-hidden="true" />
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
    <details className="group rounded-[14px] bg-field shadow-[0_0_0_1px_var(--line)]">
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
