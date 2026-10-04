import { useState } from 'react'

import type { EstimationInput, ResponseLanguage, SessionSummary } from './api/types'
import { ConversationThread } from './components/ConversationThread'
import { EstimateForm } from './components/EstimateForm'
import { ErrorAlert } from './components/EstimationResult'
import { Sidebar } from './components/Sidebar'
import { useSession } from './hooks/useSession'
import type { PendingTurn, SessionInfo, ThreadTurn } from './hooks/useSession'
import { useResponseLanguage } from './hooks/useResponseLanguage'
import { useTheme } from './hooks/useTheme'
import type { Theme } from './hooks/useTheme'
import { LocaleProvider } from './i18n/LocaleContext'
import { useT } from './i18n/useLocale'

export default function App() {
  const [theme, setTheme] = useTheme()
  const [language, setLanguage] = useResponseLanguage()
  const { turns, pending, error, session, sessions, run, newConversation, selectSession } = useSession()
  const busy = pending?.status === 'loading'
  // Bumped after each successful send so the composer clears its draft.
  const [resetKey, setResetKey] = useState(0)

  return (
    <LocaleProvider locale={language}>
      <AppShell
        theme={theme}
        setTheme={setTheme}
        language={language}
        setLanguage={setLanguage}
        busy={busy}
        turns={turns}
        pending={pending}
        error={error}
        resetKey={resetKey}
        session={session}
        sessions={sessions}
        onNewConversation={newConversation}
        onSelectSession={selectSession}
        onSubmit={async (input, files) => {
          if (await run({ ...input, language }, files)) setResetKey((key) => key + 1)
        }}
      />
    </LocaleProvider>
  )
}

interface AppShellProps {
  theme: Theme
  setTheme: (theme: Theme) => void
  language: ResponseLanguage
  setLanguage: (language: ResponseLanguage) => void
  busy: boolean
  turns: ThreadTurn[]
  pending: PendingTurn | null
  error: string | null
  resetKey: number
  session: SessionInfo
  sessions: SessionSummary[]
  onNewConversation: () => void
  onSelectSession: (id: string) => void
  onSubmit: (input: EstimationInput, files: File[]) => void | Promise<void>
}

function AppShell({
  theme,
  setTheme,
  language,
  setLanguage,
  busy,
  turns,
  pending,
  error,
  resetKey,
  session,
  sessions,
  onNewConversation,
  onSelectSession,
  onSubmit,
}: AppShellProps) {
  const t = useT()
  const hasThread = turns.length > 0 || pending !== null

  return (
    <div className="grid min-h-screen md:grid-cols-[288px_1fr]">
      <Sidebar
        session={session}
        sessions={sessions}
        busy={busy}
        onNewConversation={onNewConversation}
        onSelectSession={onSelectSession}
        language={language}
        onLanguageChange={setLanguage}
        theme={theme}
        onThemeChange={setTheme}
      />

      <main className="min-w-0 px-4 pt-9 pb-20 md:px-12 md:pt-10 md:pb-12">
        <div className="mx-auto max-w-[740px]">
          {!hasThread && (
            <>
              <div className="mb-[18px] inline-flex animate-enter items-center gap-2 rounded-full bg-field py-1 pr-2.5 pl-1.5 font-mono text-[11.5px] text-muted shadow-[0_0_0_1px_var(--line)]">
                <span className="rounded-full bg-accent px-1.5 py-px text-btn-ink">CAG</span>
                {t('hero.badge')}
              </div>
              <h1 className="animate-enter text-[34px] leading-[1.05] font-bold tracking-[-0.035em] [animation-delay:30ms] md:text-[42px]">
                {t('hero.title.before')} <em className="text-accent not-italic">{t('hero.title.em')}</em>
              </h1>
              <p className="mt-3.5 mb-6 max-w-[560px] animate-enter text-[15.5px] text-muted [animation-delay:60ms]">
                {t('hero.subtitle.before')}{' '}
                <code className="rounded-md bg-accent-soft px-1.5 py-px font-mono text-[12.5px] text-ink">EstimationRequest</code>{' '}
                {t('hero.subtitle.after')}
              </p>
            </>
          )}

          <ConversationThread turns={turns} pending={pending} />
          <EstimateForm
            key={session.id ?? 'pending'}
            busy={busy}
            onSubmit={onSubmit}
            followUp={turns.length > 0}
            resetKey={resetKey}
          />
          {error && <ErrorAlert message={error} />}
        </div>
      </main>
    </div>
  )
}
