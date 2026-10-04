import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { checkHealth, createSession, createSessionEstimate, getPromptContext, getSession, listSessions } from './api/client'
import { METADATA, pdf, sessionDetail, sessionEstimate, sessionSummary, sessionTurn } from './test/fixtures'

vi.mock('./api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/client')>()),
  checkHealth: vi.fn(),
  getPromptContext: vi.fn(),
  createSession: vi.fn(),
  createSessionEstimate: vi.fn(),
  getSession: vi.fn(),
  listSessions: vi.fn(),
}))

const DESCRIPTION = 'App móvil para reservar clases en un gimnasio.'
const createSessionMock = vi.mocked(createSession)
const estimateMock = vi.mocked(createSessionEstimate)

beforeEach(() => {
  // The app defaults to English; most tests here assert the Spanish copy, so start from a saved 'es'.
  localStorage.setItem('response-language', 'es')
  vi.mocked(checkHealth).mockResolvedValue(true)
  vi.mocked(getPromptContext).mockResolvedValue({ prompt_version: 'v1', examples_markdown: '' })
  createSessionMock.mockReset()
  estimateMock.mockReset()
  vi.mocked(getSession).mockReset()
  vi.mocked(listSessions).mockReset()
  vi.mocked(listSessions).mockResolvedValue([])
  createSessionMock.mockResolvedValueOnce({ session_id: 'abcdef123456' })
})

async function fillForm() {
  const user = userEvent.setup()
  render(<App />)
  await screen.findByText('abcdef12')
  await user.type(screen.getByLabelText(/transcripción o descripción del proyecto/i), DESCRIPTION)
  return user
}

const TWO = 'Ahora añade una app móvil para reservar desde el teléfono.'

describe('App', () => {
  it('creates a session on load and shows its short id', async () => {
    render(<App />)
    expect(await screen.findByText('abcdef12')).toBeInTheDocument()
    expect(createSessionMock).toHaveBeenCalledTimes(1)
  })

  it('submits through the session endpoint with the files and shows the estimation and memory', async () => {
    estimateMock.mockResolvedValue(sessionEstimate({ text: '## Estimación: Gimnasio', history_turns: 1 }))
    const user = await fillForm()
    const file = pdf('brief.pdf')
    await user.upload(screen.getByLabelText(/adjuntos/i), file)

    await user.click(screen.getByRole('button', { name: 'Generar estimación' }))

    expect(await screen.findByRole('heading', { name: 'Estimación: Gimnasio' })).toBeInTheDocument()
    expect(estimateMock).toHaveBeenCalledWith(
      'abcdef123456',
      expect.objectContaining({ description: DESCRIPTION, language: 'es' }),
      [file],
      expect.any(AbortSignal),
    )
    const memory = screen.getByRole('heading', { name: 'Memoria del proyecto' }).parentElement as HTMLElement
    expect(within(memory).getByText(METADATA.project_name as string)).toBeInTheDocument()
    expect(within(memory).getByText('React')).toBeInTheDocument()
    expect(within(memory).getByText('FastAPI')).toBeInTheDocument()
    expect(screen.getByText('1 turno')).toBeInTheDocument()
  })

  it('starts a new conversation: new session, cleared result and form', async () => {
    estimateMock.mockResolvedValue(sessionEstimate({ text: '## Estimación: Gimnasio' }))
    const user = await fillForm()
    await user.click(screen.getByRole('button', { name: 'Generar estimación' }))
    await screen.findByRole('heading', { name: 'Estimación: Gimnasio' })

    createSessionMock.mockResolvedValueOnce({ session_id: 'zzzzzzzz9999' })
    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }))

    expect(await screen.findByText('zzzzzzzz')).toBeInTheDocument()
    expect(createSessionMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('heading', { name: 'Estimación: Gimnasio' })).not.toBeInTheDocument()
    expect(screen.getByLabelText(/transcripción o descripción del proyecto/i)).toHaveValue('')
    expect(screen.getByText('0 turnos')).toBeInTheDocument()
  })

  it('has no streaming switch', async () => {
    render(<App />)
    await screen.findByText('abcdef12')
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  it('sends the saved language and the newly selected language on the next request', async () => {
    estimateMock.mockResolvedValue(sessionEstimate({ text: '## Estimación: Gimnasio' }))
    const user = await fillForm()

    await user.click(screen.getByRole('button', { name: 'Generar estimación' }))
    await screen.findByRole('heading', { name: 'Estimación: Gimnasio' })
    expect(estimateMock).toHaveBeenLastCalledWith('abcdef123456', expect.objectContaining({ language: 'es' }), [], expect.any(AbortSignal))

    await user.click(screen.getByRole('radio', { name: /English/ }))
    await user.type(screen.getByLabelText(/transcript or project description/i), DESCRIPTION)
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(estimateMock).toHaveBeenLastCalledWith('abcdef123456', expect.objectContaining({ language: 'en' }), [], expect.any(AbortSignal))
  })

  it('starts in English and dark with a fresh browser (no saved preferences)', async () => {
    localStorage.clear()
    estimateMock.mockResolvedValue(sessionEstimate({ text: '## Estimate: Gym' }))
    const user = userEvent.setup()
    render(<App />)

    expect(screen.getByRole('radio', { name: /English/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeChecked()
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dataset.theme).toBe('dark')

    await screen.findByText('abcdef12')
    await user.type(screen.getByLabelText(/transcript or project description/i), DESCRIPTION)
    await user.click(screen.getByRole('button', { name: 'Generate estimate' }))
    expect(estimateMock).toHaveBeenLastCalledWith('abcdef123456', expect.objectContaining({ language: 'en' }), [], expect.any(AbortSignal))
  })

  it('switches the visible UI copy when the language changes', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Estimador de/)
    expect(screen.getByRole('button', { name: 'Generar estimación' })).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /English/ }))

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Software/)
    expect(screen.getByRole('button', { name: 'Generate estimate' })).toBeInTheDocument()
    expect(screen.getByLabelText(/transcript or project description/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New conversation' })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('en')
  })

  it('remembers the response language after a reload', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<App />)
    await user.click(screen.getByRole('radio', { name: /English/ }))
    unmount()
    createSessionMock.mockResolvedValue({ session_id: 'abcdef123456' })

    render(<App />)

    expect(screen.getByRole('radio', { name: /English/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Generate estimate' })).toBeInTheDocument()
  })

  it('shows API failures and lets the user retry', async () => {
    estimateMock
      .mockRejectedValueOnce(new Error('Error HTTP 502: El proveedor LLM tardó demasiado en responder.'))
      .mockResolvedValueOnce(sessionEstimate({ text: '## Estimación: Reintento' }))
    const user = await fillForm()
    const submit = screen.getByRole('button', { name: 'Generar estimación' })

    await user.click(submit)
    expect(await screen.findByRole('alert')).toHaveTextContent('tardó demasiado')
    expect(submit).toBeEnabled()
    expect(screen.getByLabelText(/transcripción o descripción del proyecto/i)).toHaveValue(DESCRIPTION)

    await user.click(submit)
    expect(await screen.findByRole('heading', { name: 'Estimación: Reintento' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('lists server sessions and restores the clicked one', async () => {
    vi.mocked(listSessions).mockResolvedValue([
      sessionSummary({ session_id: 'abcdef123456', project_name: 'Gimnasio', history_turns: 1 }),
      sessionSummary({ session_id: 'other0000000', project_name: 'Portal de reservas', history_turns: 2 }),
    ])
    vi.mocked(getSession).mockResolvedValue(sessionDetail({ session_id: 'other0000000', turns: [sessionTurn({ estimate: '## Estimación: Portal' })] }))
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /Portal de reservas/ }))

    await screen.findByRole('heading', { name: 'Estimación: Portal' })
    expect(screen.getByText('other000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Portal de reservas/ })).toHaveAttribute('aria-current', 'true')
  })

  it('shows the thread: two sends give two turns in order and an empty composer in follow-up mode', async () => {
    estimateMock
      .mockResolvedValueOnce(sessionEstimate({ text: '## Estimación: Uno', history_turns: 1 }))
      .mockResolvedValueOnce(sessionEstimate({ text: '## Estimación: Dos', history_turns: 2 }))
    const user = await fillForm()
    const composer = screen.getByLabelText(/transcripción o descripción del proyecto/i)
    await user.upload(screen.getByLabelText(/adjuntos/i), pdf('brief.pdf'))
    await user.selectOptions(screen.getByLabelText('Nivel de detalle'), 'detailed')

    await user.click(screen.getByRole('button', { name: 'Generar estimación' }))
    await screen.findByRole('heading', { name: 'Estimación: Uno' })

    // The hero gives way to the thread; the draft is gone but the options stay.
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
    expect(composer).toHaveValue('')
    expect(screen.queryByText('brief.pdf', { selector: 'li span' })).toBeInTheDocument() // chip in the thread
    expect(screen.getByLabelText('Nivel de detalle')).toHaveValue('detailed')
    expect(composer).toHaveAttribute('placeholder', expect.stringMatching(/Sigue la conversación/))

    await user.type(composer, TWO)
    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    await screen.findByRole('heading', { name: 'Estimación: Dos' })

    const thread = screen.getByRole('region', { name: 'Conversación' })
    expect(within(thread).getByText(DESCRIPTION)).toBeInTheDocument()
    const order = Array.from(thread.querySelectorAll('h2, [class*="whitespace-pre-wrap"]')).map((node) => node.textContent)
    expect(order).toEqual([DESCRIPTION, 'Estimación', 'Estimación: Uno', TWO, 'Estimación', 'Estimación: Dos'])
    expect(screen.getByRole('heading', { name: 'Estimación: Uno' })).toBeInTheDocument()
    expect(composer).toHaveValue('')
  })

  it('keeps the typed text and earlier turns when a follow-up fails', async () => {
    estimateMock
      .mockResolvedValueOnce(sessionEstimate({ text: '## Estimación: Uno' }))
      .mockRejectedValueOnce(new Error('Error HTTP 502: falló'))
    const user = await fillForm()
    await user.click(screen.getByRole('button', { name: 'Generar estimación' }))
    await screen.findByRole('heading', { name: 'Estimación: Uno' })
    const composer = screen.getByLabelText(/transcripción o descripción del proyecto/i)

    await user.type(composer, TWO)
    await user.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('falló')
    expect(composer).toHaveValue(TWO)
    expect(screen.getByRole('heading', { name: 'Estimación: Uno' })).toBeInTheDocument()
  })

  it('renders the turns of the selected session, with attachment names', async () => {
    vi.mocked(listSessions).mockResolvedValue([
      sessionSummary({ session_id: 'other0000000', project_name: 'Portal de reservas', history_turns: 2 }),
    ])
    vi.mocked(getSession).mockResolvedValue(
      sessionDetail({
        session_id: 'other0000000',
        turns: [
          sessionTurn({ description: 'Primer mensaje del cliente', estimate: '## Estimación: A', attachment_names: ['spec.pdf'] }),
          sessionTurn({ description: 'Segundo mensaje del cliente', estimate: '## Estimación: B' }),
        ],
      }),
    )
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /Portal de reservas/ }))

    await screen.findByRole('heading', { name: 'Estimación: B' })
    const thread = screen.getByRole('region', { name: 'Conversación' })
    expect(within(thread).getByText('Primer mensaje del cliente')).toBeInTheDocument()
    expect(within(thread).getByText('spec.pdf')).toBeInTheDocument()
    expect(within(thread).getByText('Segundo mensaje del cliente')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeInTheDocument()
  })
})
