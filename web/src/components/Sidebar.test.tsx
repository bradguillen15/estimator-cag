import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { checkHealth, getPromptContext } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import type { SessionInfo } from '../hooks/useSession'
import { METADATA } from '../test/fixtures'
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
    busy: false,
    onNewConversation: vi.fn(),
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

  it('shows the short session id, the project memory and the history turns', () => {
    renderSidebar({ session: { id: '0123456789abcdef', metadata: METADATA, turns: 3 } })

    expect(screen.getByRole('heading', { name: 'Conversación' })).toBeInTheDocument()
    expect(screen.getByText('01234567')).toBeInTheDocument()
    expect(screen.queryByText(/89abcdef/)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Memoria del proyecto' })).toBeInTheDocument()
    expect(screen.getByText('Portal de reservas')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('React, FastAPI')).toBeInTheDocument()
    expect(screen.getByText('MVP con calendario')).toBeInTheDocument()
    expect(screen.getByText('Turnos en el historial: 3')).toBeInTheDocument()
    expect(screen.getByText(/La memoria guarda los hechos del proyecto/)).toBeInTheDocument()
  })

  it('shows an em dash for every empty memory field', () => {
    renderSidebar({ session: { id: 'abcdefgh', metadata: EMPTY_PROJECT_METADATA, turns: 0 } })
    expect(screen.getAllByText('—')).toHaveLength(4)
  })

  it('starts a new conversation on click', async () => {
    const user = userEvent.setup()
    const { onNewConversation } = renderSidebar({ session: { id: 'abcdefgh', metadata: EMPTY_PROJECT_METADATA, turns: 0 } })

    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }))

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
})
