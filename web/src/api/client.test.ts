import { beforeEach, describe, expect, it, vi } from 'vitest'

import { jsonResponse, pdf, REQUEST, sessionEstimate } from '../test/fixtures'
import { ApiError, checkHealth, createSession, createSessionEstimate, getPromptContext } from './client'

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})

describe('createSession', () => {
  it('posts to /sessions and returns the new id', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ session_id: 'abc' }, 201))

    await expect(createSession()).resolves.toEqual({ session_id: 'abc' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/sessions')
    expect(init?.method).toBe('POST')
  })

  it('lets aborts propagate untouched so callers can ignore them', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    await expect(createSession()).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('createSessionEstimate', () => {
  it('posts multipart form data without an explicit Content-Type', async () => {
    fetchMock.mockResolvedValue(jsonResponse(sessionEstimate()))
    const files = [pdf('a.pdf'), pdf('b.pdf')]

    await expect(createSessionEstimate('abc', REQUEST, files)).resolves.toEqual(sessionEstimate())

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/sessions/abc/estimate')
    expect(init?.method).toBe('POST')
    expect(new Headers(init?.headers).has('Content-Type')).toBe(false)
    const form = init?.body as FormData
    expect(form).toBeInstanceOf(FormData)
    expect(form.get('transcript')).toBe(REQUEST.description)
    expect(form.has('description')).toBe(false)
    expect(form.get('project_type')).toBe('web_saas')
    expect(form.get('detail_level')).toBe('medium')
    expect(form.get('output_format')).toBe('line_items')
    expect(form.get('language')).toBe('es')
    expect((form.getAll('attachments') as File[]).map((file) => file.name)).toEqual(['a.pdf', 'b.pdf'])
  })

  it('sends no attachments field when there are no files', async () => {
    fetchMock.mockResolvedValue(jsonResponse(sessionEstimate()))
    await createSessionEstimate('abc', REQUEST, [])
    expect((fetchMock.mock.calls[0][1]?.body as FormData).has('attachments')).toBe(false)
  })

  it('encodes the session id in the URL', async () => {
    fetchMock.mockResolvedValue(jsonResponse(sessionEstimate()))
    await createSessionEstimate('a/b c', REQUEST, [])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/sessions/a%2Fb%20c/estimate')
  })

  it('surfaces the API detail message with the status code', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Session not found' }, 404))

    const error = await createSessionEstimate('abc', REQUEST, []).catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: 'Error HTTP 404: Session not found' })
  })

  it('summarises FastAPI validation errors', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: [{ loc: ['body', 'transcript'], msg: 'String should have at least 20 characters' }] }, 422),
    )

    await expect(createSessionEstimate('abc', REQUEST, [])).rejects.toThrow(
      'Error HTTP 422: transcript: String should have at least 20 characters',
    )
  })

  it('falls back to the status text when the error body is not JSON', async () => {
    fetchMock.mockResolvedValue(new Response('<html>oops</html>', { status: 500, statusText: 'Internal Server Error' }))
    await expect(createSessionEstimate('abc', REQUEST, [])).rejects.toThrow('Error HTTP 500: Internal Server Error')
  })

  it('explains how to start the API when the network request fails', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(createSessionEstimate('abc', REQUEST, [])).rejects.toThrow(/No se pudo conectar a la API.*uv run uvicorn/)
  })
})

describe('checkHealth and getPromptContext', () => {
  it('reports whether the API answers /health', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: 'ok' }))
    fetchMock.mockResolvedValueOnce(new Response('', { status: 503 }))
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    expect(await checkHealth()).toBe(true)
    expect(await checkHealth()).toBe(false)
    expect(await checkHealth()).toBe(false)
  })

  it('loads the CAG context', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ prompt_version: 'v1', examples_markdown: '### Ejemplo 1' }))
    await expect(getPromptContext()).resolves.toEqual({ prompt_version: 'v1', examples_markdown: '### Ejemplo 1' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/context')
  })
})
