import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, createSession, createSessionEstimate } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import { METADATA, REQUEST, sessionEstimate } from '../test/fixtures'
import { useSession } from './useSession'

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  createSession: vi.fn(),
  createSessionEstimate: vi.fn(),
}))

const createSessionMock = vi.mocked(createSession)
const estimateMock = vi.mocked(createSessionEstimate)

beforeEach(() => {
  createSessionMock.mockReset()
  estimateMock.mockReset()
  createSessionMock.mockResolvedValueOnce({ session_id: 's1' })
})

async function mounted() {
  const hook = renderHook(() => useSession())
  await waitFor(() => expect(hook.result.current.session.id).toBe('s1'))
  return hook
}

describe('useSession', () => {
  it('creates a session on mount and starts idle with empty memory', async () => {
    const { result } = await mounted()

    expect(createSessionMock).toHaveBeenCalledTimes(1)
    expect(result.current.state).toEqual({ status: 'idle', text: '', meta: null, error: null })
    expect(result.current.session).toEqual({ id: 's1', metadata: EMPTY_PROJECT_METADATA, turns: 0 })
  })

  it('creates a single session under StrictMode double mount', async () => {
    createSessionMock.mockReset()
    createSessionMock.mockResolvedValueOnce({ session_id: 'first' }).mockResolvedValueOnce({ session_id: 'second' })

    const { result } = renderHook(() => useSession(), { reactStrictMode: true })

    await waitFor(() => expect(result.current.session.id).not.toBeNull())
    expect(createSessionMock).toHaveBeenCalledTimes(2)
    expect(result.current.session.id).toBe('second')
  })

  it('surfaces a session-creation failure as an error state', async () => {
    createSessionMock.mockReset()
    createSessionMock.mockRejectedValueOnce(new ApiError('Error HTTP 500: boom', 500))

    const { result } = renderHook(() => useSession())

    await waitFor(() => expect(result.current.state.status).toBe('error'))
    expect(result.current.state.error).toBe('Error HTTP 500: boom')
    expect(result.current.session.id).toBeNull()
  })

  it('shows loading, then the result with memory and turns', async () => {
    let resolve!: (value: ReturnType<typeof sessionEstimate>) => void
    estimateMock.mockReturnValue(new Promise((r) => (resolve = r)))
    const { result } = await mounted()
    const files = [new File(['x'], 'a.pdf')]

    act(() => void result.current.run(REQUEST, files))
    expect(result.current.state.status).toBe('loading')

    await act(async () => resolve(sessionEstimate({ history_turns: 2 })))

    expect(result.current.state).toEqual({
      status: 'done',
      text: '## Estimación',
      meta: { prompt_version: 'v1', cache_hit: false },
      error: null,
    })
    expect(result.current.session).toEqual({ id: 's1', metadata: METADATA, turns: 2 })
    expect(estimateMock).toHaveBeenCalledWith('s1', REQUEST, files, expect.any(AbortSignal))
  })

  it('creates the session first when run is called before one exists', async () => {
    createSessionMock.mockReset()
    createSessionMock.mockRejectedValueOnce(new ApiError('down')).mockResolvedValueOnce({ session_id: 's2' })
    estimateMock.mockResolvedValue(sessionEstimate())
    const { result } = renderHook(() => useSession())
    await waitFor(() => expect(result.current.state.status).toBe('error'))

    await act(() => result.current.run(REQUEST, []))

    expect(estimateMock).toHaveBeenCalledWith('s2', REQUEST, [], expect.any(AbortSignal))
    expect(result.current.state.status).toBe('done')
    expect(result.current.session.id).toBe('s2')
  })

  it('recreates the session and retries once on 404', async () => {
    createSessionMock.mockResolvedValueOnce({ session_id: 's2' })
    estimateMock
      .mockRejectedValueOnce(new ApiError('Error HTTP 404: not found', 404))
      .mockResolvedValueOnce(sessionEstimate({ history_turns: 1 }))
    const { result } = await mounted()

    await act(() => result.current.run(REQUEST, []))

    expect(createSessionMock).toHaveBeenCalledTimes(2)
    expect(estimateMock).toHaveBeenNthCalledWith(1, 's1', REQUEST, [], expect.any(AbortSignal))
    expect(estimateMock).toHaveBeenNthCalledWith(2, 's2', REQUEST, [], expect.any(AbortSignal))
    expect(result.current.state.status).toBe('done')
    expect(result.current.session).toEqual({ id: 's2', metadata: METADATA, turns: 1 })
  })

  it('gives up when the retry also fails', async () => {
    createSessionMock.mockResolvedValueOnce({ session_id: 's2' })
    estimateMock.mockRejectedValue(new ApiError('Error HTTP 404: not found', 404))
    const { result } = await mounted()

    await act(() => result.current.run(REQUEST, []))

    expect(estimateMock).toHaveBeenCalledTimes(2)
    expect(result.current.state).toMatchObject({ status: 'error', error: 'Error HTTP 404: not found' })
  })

  it('does not retry other errors', async () => {
    estimateMock.mockRejectedValue(new ApiError('Error HTTP 502: upstream', 502))
    const { result } = await mounted()

    await act(() => result.current.run(REQUEST, []))

    expect(createSessionMock).toHaveBeenCalledTimes(1)
    expect(estimateMock).toHaveBeenCalledTimes(1)
    expect(result.current.state).toMatchObject({ status: 'error', error: 'Error HTTP 502: upstream' })
  })

  it('resets state and memory and creates a new session on newConversation', async () => {
    estimateMock.mockResolvedValue(sessionEstimate())
    const { result } = await mounted()
    await act(() => result.current.run(REQUEST, []))
    expect(result.current.session.turns).toBe(1)

    createSessionMock.mockResolvedValueOnce({ session_id: 's2' })
    await act(() => result.current.newConversation())

    expect(createSessionMock).toHaveBeenCalledTimes(2)
    expect(result.current.state).toEqual({ status: 'idle', text: '', meta: null, error: null })
    expect(result.current.session).toEqual({ id: 's2', metadata: EMPTY_PROJECT_METADATA, turns: 0 })
  })

  it('ignores the result of a request aborted by newConversation', async () => {
    let resolve!: (value: ReturnType<typeof sessionEstimate>) => void
    estimateMock.mockReturnValue(new Promise((r) => (resolve = r)))
    const { result } = await mounted()
    act(() => void result.current.run(REQUEST, []))

    createSessionMock.mockResolvedValueOnce({ session_id: 's2' })
    await act(() => result.current.newConversation())
    await act(async () => resolve(sessionEstimate()))

    expect(result.current.state.status).toBe('idle')
    expect(result.current.session).toEqual({ id: 's2', metadata: EMPTY_PROJECT_METADATA, turns: 0 })
  })
})
