import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, createSession, createSessionEstimate } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import type { EstimationRequest, GenerationMeta, ProjectMetadata } from '../api/types'

export type EstimationStatus = 'idle' | 'loading' | 'done' | 'error'

export interface EstimationState {
  status: EstimationStatus
  text: string
  meta: GenerationMeta | null
  error: string | null
}

export interface SessionInfo {
  /** Null while the session is being created (or creation failed). */
  id: string | null
  metadata: ProjectMetadata
  turns: number
}

const IDLE: EstimationState = { status: 'idle', text: '', meta: null, error: null }
const NO_SESSION: SessionInfo = { id: null, metadata: EMPTY_PROJECT_METADATA, turns: 0 }

const isAbort = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError'
const messageOf = (error: unknown): string => (error instanceof Error ? error.message : String(error))

/**
 * Conversation-scoped estimation: owns one server session, creates it on mount and replays
 * the project memory/history the server returns. A new run aborts the previous one.
 */
export function useSession() {
  const [state, setState] = useState<EstimationState>(IDLE)
  const [session, setSession] = useState<SessionInfo>(NO_SESSION)
  const abortRef = useRef<AbortController | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  // Bumped on every (re)start so results of superseded session creations are ignored.
  const epochRef = useRef(0)

  const invalidate = useCallback(() => {
    epochRef.current++
  }, [])

  const abortInFlight = useCallback((): AbortController => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    return controller
  }, [])

  /** Creates a session and stores it. Returns its id, or null when superseded/aborted. Throws on failure. */
  const startSession = useCallback(async (signal: AbortSignal): Promise<string | null> => {
    const epoch = ++epochRef.current
    sessionIdRef.current = null
    setSession(NO_SESSION)
    const { session_id } = await createSession(signal)
    if (epoch !== epochRef.current || signal.aborted) return null
    sessionIdRef.current = session_id
    setSession({ ...NO_SESSION, id: session_id })
    return session_id
  }, [])

  useEffect(() => {
    const controller = abortInFlight()
    startSession(controller.signal).catch((error: unknown) => {
      if (isAbort(error) || controller.signal.aborted) return
      setState({ ...IDLE, status: 'error', error: messageOf(error) })
    })
    return () => {
      // Invalidates a pending creation (StrictMode double mount keeps only the last one).
      invalidate()
      controller.abort()
    }
  }, [abortInFlight, startSession, invalidate])

  const run = useCallback(
    async (request: EstimationRequest, files: File[]) => {
      const controller = abortInFlight()
      const { signal } = controller
      setState({ ...IDLE, status: 'loading' })

      try {
        let id = sessionIdRef.current ?? (await startSession(signal))
        if (id === null) return

        let response
        try {
          response = await createSessionEstimate(id, request, files, signal)
        } catch (error) {
          // The server forgot the session (e.g. it restarted): start over once, memory is lost.
          if (!(error instanceof ApiError) || error.status !== 404) throw error
          id = await startSession(signal)
          if (id === null) return
          response = await createSessionEstimate(id, request, files, signal)
        }

        if (signal.aborted) return
        setState({
          status: 'done',
          text: response.text,
          meta: { prompt_version: response.prompt_version, cache_hit: response.cache_hit },
          error: null,
        })
        setSession({ id, metadata: response.project_metadata, turns: response.history_turns })
      } catch (error) {
        if (isAbort(error) || signal.aborted) return
        setState({ ...IDLE, status: 'error', error: messageOf(error) })
      }
    },
    [abortInFlight, startSession],
  )

  const newConversation = useCallback(async () => {
    const controller = abortInFlight()
    setState(IDLE)
    try {
      await startSession(controller.signal)
    } catch (error) {
      if (isAbort(error) || controller.signal.aborted) return
      setState({ ...IDLE, status: 'error', error: messageOf(error) })
    }
  }, [abortInFlight, startSession])

  return { state, session, run, newConversation }
}
