import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { checkHealth, getPromptContext } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import type { SessionSummary } from '../api/types'
import type { SessionInfo } from '../hooks/useSession'
import { METADATA, sessionSummary } from '../test/fixtures'
import { withLocale } from '../test/render'
import { Sidebar } from './Sidebar'

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  checkHealth: vi.fn(),
  getPromptContext: vi.fn(),
}))

const checkHealthMock = vi.mocked(checkHealth)
const getPromptContextMock = vi.mocked(getPromptContext)

function renderSidebar(overrides: Partial<Parameters<typeof Sidebar>[0]> = {}, locale: 'es' | 'en' = 'es') {
  const props = {
    session: { id: null, metadata: EMPTY_PROJECT_METADATA, turns: 0 } as SessionInfo,
    sessions: [] as SessionSummary[],
    busy: false,
    onNewConversation: vi.fn(),
    onSelectSession: vi.fn(),
    language: locale,
    onLanguageChange: vi.fn(),
    theme: 'light' as const,
    onThemeChange: vi.fn(),
    ...overrides,
  }
  withLocale(<Sidebar {...props} />, locale)
  return props
}

beforeEach(() => {
  checkHealthMock.mockResolvedValue(true)
  getPromptContextMock.mockResolvedValue({ prompt_version: 'v1', examples_markdown: '### Ejemplo 1 — Marketplace B2B' })
})

describe('Sidebar', () => {
  it('reports when the API is reachable', async () => {
    renderSidebar()
    expect(await screen.findByText('API disponible')).toBeInTheDocument()
  })

  it('reports when the API is down', async () => {
    checkHealthMock.mockResolvedValue(false)
    renderSidebar()
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
  })

  it('shows English API status labels when the locale is English', async () => {
    renderSidebar({}, 'en')
    expect(await screen.findByText('API available')).toBeInTheDocument()
  })

  it('shows the CAG examples the server injects, with their prompt version', async () => {
    const user = userEvent.setup()
    renderSidebar()

    await user.click(screen.getByText('Ejemplos estáticos'))

    expect(await screen.findByRole('heading', { name: 'Ejemplo 1 — Marketplace B2B' })).toBeVisible()
    expect(screen.getByText('v1')).toBeInTheDocument()
  })

  it('explains why the examples could not be loaded', async () => {
    getPromptContextMock.mockRejectedValue(new Error('Error HTTP 500: Falta la plantilla'))
    renderSidebar()
    expect(await screen.findByText('Error HTTP 500: Falta la plantilla')).toBeInTheDocument()
  })

  it('shows the short session id and the history turns on one meta line', () => {
    renderSidebar({ session: { id: '0123456789abcdef', metadata: METADATA, turns: 3 } })

    const meta = screen.getByText('01234567').closest('p') as HTMLElement
    expect(meta).toHaveTextContent('ID de sesión01234567 · 3 turnos')
    expect(meta).toHaveAttribute('title', '0123456789abcdef')
    expect(screen.queryByText(/89abcdef/)).not.toBeInTheDocument()
  })

  it('uses the singular turn label and English copy', () => {
    renderSidebar({ session: { id: '0123456789abcdef', metadata: METADATA, turns: 1 } }, 'en')
    expect(screen.getByText('1 turn')).toBeInTheDocument()
  })

  it('shows only the project facts that are known', () => {
    renderSidebar({
      session: { id: 'abcdefgh', metadata: { ...EMPTY_PROJECT_METADATA, project_name: 'Portal', mentioned_technologies: ['React', 'FastAPI'] }, turns: 1 },
    })

    expect(screen.getByRole('heading', { name: 'Memoria del proyecto' })).toBeInTheDocument()
    expect(screen.getByText('Portal')).toBeInTheDocument()
    expect(screen.getByText('React')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
    expect(screen.getByText('Nombre')).toBeInTheDocument()
    expect(screen.getByText('Tecnologías')).toBeInTheDocument()
    expect(screen.queryByText('Equipo asumido')).not.toBeInTheDocument()
    expect(screen.queryByText('Alcance acordado')).not.toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })

  it('shows every fact when all are known', () => {
    renderSidebar({ session: { id: 'abcdefgh', metadata: METADATA, turns: 1 } })
    expect(screen.getByText('Portal de reservas')).toBeInTheDocument()
    expect(screen.getByText('4 personas')).toBeInTheDocument()
    expect(screen.getByText('MVP con calendario')).toBeInTheDocument()
    // Short scope: nothing to expand.
    expect(screen.queryByRole('button', { name: 'Ver más' })).not.toBeInTheDocument()
  })

  it('clamps a long agreed scope behind a show-more toggle', async () => {
    const user = userEvent.setup()
    const scope = 'Reservas con calendario, pagos en línea, notificaciones por email y panel de administración. '.repeat(3)
    renderSidebar({ session: { id: 'abcdefgh', metadata: { ...METADATA, agreed_scope: scope }, turns: 1 } }, 'en')

    const toggle = screen.getByRole('button', { name: 'Show more' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('shows a hint instead of empty rows when no facts are known', () => {
    renderSidebar({ session: { id: 'abcdefgh', metadata: EMPTY_PROJECT_METADATA, turns: 0 } })
    expect(screen.getByText('Los datos aparecerán a medida que describas el proyecto.')).toBeInTheDocument()
    expect(screen.queryByText('Nombre')).not.toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })

  it('starts a new conversation from the icon button', async () => {
    const user = userEvent.setup()
    const { onNewConversation } = renderSidebar({ session: { id: 'abcdefgh', metadata: EMPTY_PROJECT_METADATA, turns: 0 } })

    const button = screen.getByRole('button', { name: 'Nueva conversación' })
    await user.click(button)

    expect(onNewConversation).toHaveBeenCalledTimes(1)
  })

  it('disables the new-conversation button while busy or without a session', () => {
    renderSidebar({ busy: true, session: { id: 'abcdefgh', metadata: EMPTY_PROJECT_METADATA, turns: 0 } })
    expect(screen.getByRole('button', { name: 'Nueva conversación' })).toBeDisabled()
  })

  it('disables the new-conversation button while the session is being created', () => {
    renderSidebar()
    expect(screen.getByRole('button', { name: 'Nueva conversación' })).toBeDisabled()
  })

  it('has no streaming switch anymore', () => {
    renderSidebar()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  it('offers Spanish and English as languages, with the current one selected', () => {
    renderSidebar()

    const group = screen.getByRole('radiogroup', { name: 'Idioma' })
    expect(within(group).getByRole('radio', { name: /Español/ })).toBeChecked()
    expect(within(group).getByRole('radio', { name: /English/ })).not.toBeChecked()
  })

  it('lists the default option first (English, Dark)', () => {
    renderSidebar()

    const labels = (name: string) =>
      within(screen.getByRole('radiogroup', { name }))
        .getAllByRole('radio')
        .map((radio) => radio.closest('label')?.textContent?.trim())
    const [firstLanguage, secondLanguage] = labels('Idioma')
    const [firstTheme, secondTheme] = labels('Tema')
    expect(firstLanguage).toMatch(/English/)
    expect(secondLanguage).toMatch(/Español/)
    expect(firstTheme).toMatch(/Oscuro/)
    expect(secondTheme).toMatch(/Claro/)
  })

  it('renders the brand badge with a decorative icon instead of a letter', () => {
    renderSidebar()

    const brand = screen.getByText('Estimator CAG')
    expect(brand.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument()
    expect(brand.textContent?.trim()).toBe('Estimator CAG')
  })

  it('reports the language the user picks', async () => {
    const user = userEvent.setup()
    const { onLanguageChange } = renderSidebar()

    await user.click(screen.getByRole('radio', { name: /English/ }))

    expect(onLanguageChange).toHaveBeenCalledWith('en')
  })

  it('switches between light and dark themes', async () => {
    const user = userEvent.setup()
    const { onThemeChange } = renderSidebar()
    expect(screen.getByRole('radio', { name: 'Claro' })).toBeChecked()

    await user.click(screen.getByRole('radio', { name: 'Oscuro' }))

    expect(onThemeChange).toHaveBeenCalledWith('dark')
  })

  describe('session list', () => {
    const sessions = [
      sessionSummary({ session_id: 'aaaaaaaa1111', project_name: 'Portal de reservas', history_turns: 2 }),
      sessionSummary({ session_id: 'bbbbbbbb2222', project_name: null, history_turns: 1 }),
    ]

    it('is hidden when the server lists no sessions', () => {
      renderSidebar()
      expect(screen.queryByRole('heading', { name: 'Sesiones' })).not.toBeInTheDocument()
    })

    it('lists sessions with name fallback and turn count', () => {
      renderSidebar({ sessions })

      expect(screen.getByRole('heading', { name: 'Sesiones' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Portal de reservas.*2 turnos/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Proyecto sin nombre · bbbbbbbb.*1 turno/ })).toBeInTheDocument()
    })

    it('highlights the active session', () => {
      renderSidebar({
        sessions,
        session: { id: 'aaaaaaaa1111', metadata: EMPTY_PROJECT_METADATA, turns: 2 },
      })

      expect(screen.getByRole('button', { name: /Portal de reservas/ })).toHaveAttribute('aria-current', 'true')
      expect(screen.getByRole('button', { name: /Proyecto sin nombre/ })).not.toHaveAttribute('aria-current')
    })

    it('calls onSelectSession with the clicked id', async () => {
      const user = userEvent.setup()
      const props = renderSidebar({ sessions })

      await user.click(screen.getByRole('button', { name: /Proyecto sin nombre/ }))

      expect(props.onSelectSession).toHaveBeenCalledWith('bbbbbbbb2222')
    })

    it('disables the rows while busy', () => {
      renderSidebar({ sessions, busy: true })
      expect(screen.getByRole('button', { name: /Portal de reservas/ })).toBeDisabled()
    })
  })
})
