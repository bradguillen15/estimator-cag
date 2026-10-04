import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, createSession, createSessionEstimate, getSession, listSessions } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import type { EstimationRequest, GenerationMeta, ProjectMetadata, SessionDetail, SessionSummary } from '../api/types'

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

const STORAGE_KEY = 'estimator.sessionId'

function readStoredSessionId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredSessionId(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Storage unavailable (private mode, blocked): resuming after a reload just won't work.
  }
}

const isAbort = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError'
const messageOf = (error: unknown): string => (error instanceof Error ? error.message : String(error))

/**
 * Conversation-scoped estimation: owns one server session, resumes the last one from
 * localStorage on mount (or creates a new one) and replays the project memory/history the server
 * returns. Also lists the server's sessions and switches between them. A new run aborts the
 * previous one.
 */
export function useSession() {
  const [state, setState] = useState<EstimationState>(IDLE)
  const [session, setSession] = useState<SessionInfo>(NO_SESSION)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
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
    writeStoredSessionId(session_id)
    setSession({ ...NO_SESSION, id: session_id })
    return session_id
  }, [])

  /** Makes a server session the active one, showing its memory and last estimate (no meta chips). */
  const adopt = useCallback((detail: SessionDetail) => {
    sessionIdRef.current = detail.session_id
    writeStoredSessionId(detail.session_id)
    setSession({ id: detail.session_id, metadata: detail.project_metadata, turns: detail.history_turns })
    setState(
      detail.last_estimate === null ? IDLE : { status: 'done', text: detail.last_estimate, meta: null, error: null },
    )
  }, [])

  /** Best effort: a listing failure must never get in the way of estimating. */
  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions())
    } catch {
      // Keep the previous list.
    }
  }, [])

  useEffect(() => {
    const controller = abortInFlight()
    const { signal } = controller
    const epoch = ++epochRef.current

    async function boot() {
      const storedId = readStoredSessionId()
      if (storedId) {
        try {
          const detail = await getSession(storedId, signal)
          if (epoch !== epochRef.current || signal.aborted) return
          adopt(detail)
          return
        } catch (error) {
          if (isAbort(error) || signal.aborted) return
          // Gone (404) or unreachable: fall through to a fresh session.
        }
      }
      await startSession(signal)
    }

    boot()
      .then(() => {
        if (!signal.aborted) void refreshSessions()
      })
      .catch((error: unknown) => {
        if (isAbort(error) || signal.aborted) return
        setState({ ...IDLE, status: 'error', error: messageOf(error) })
      })
    return () => {
      // Invalidates a pending creation (StrictMode double mount keeps only the last one).
      invalidate()
      controller.abort()
    }
  }, [abortInFlight, startSession, invalidate, adopt, refreshSessions])

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
        void refreshSessions()
      } catch (error) {
        if (isAbort(error) || signal.aborted) return
        setState({ ...IDLE, status: 'error', error: messageOf(error) })
      }
    },
    [abortInFlight, startSession, refreshSessions],
  )

  const newConversation = useCallback(async () => {
    const controller = abortInFlight()
    setState(IDLE)
    try {
      await startSession(controller.signal)
      if (!controller.signal.aborted) void refreshSessions()
    } catch (error) {
      if (isAbort(error) || controller.signal.aborted) return
      setState({ ...IDLE, status: 'error', error: messageOf(error) })
    }
  }, [abortInFlight, startSession, refreshSessions])

  const selectSession = useCallback(
    async (id: string) => {
      if (id === sessionIdRef.current) return
      const controller = abortInFlight()
      const { signal } = controller
      const epoch = ++epochRef.current
      try {
        const detail = await getSession(id, signal)
        if (epoch !== epochRef.current || signal.aborted) return
        adopt(detail)
      } catch (error) {
        if (isAbort(error) || signal.aborted) return
        if (error instanceof ApiError && error.status === 404) void refreshSessions()
        setState({ ...IDLE, status: 'error', error: messageOf(error) })
      }
    },
    [abortInFlight, adopt, refreshSessions],
  )

  return { state, session, sessions, run, newConversation, selectSession }
}
