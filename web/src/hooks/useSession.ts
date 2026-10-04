import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, createSession, createSessionEstimate, getSession, listSessions } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import type { EstimationRequest, GenerationMeta, ProjectMetadata, SessionDetail, SessionSummary } from '../api/types'

/** One finished exchange: what the user sent and the estimate that came back. */
export interface ThreadTurn {
  description: string
  attachmentNames: string[]
  text: string
  /** Null only for turns rebuilt without generation details. */
  meta: GenerationMeta | null
}

/** The turn being sent: shown as a user message plus a loading card, or the error that ended it. */
export interface PendingTurn {
  description: string
  attachmentNames: string[]
  status: 'loading' | 'error'
  error: string | null
}

export interface SessionInfo {
  /** Null while the session is being created (or creation failed). */
  id: string | null
  metadata: ProjectMetadata
  turns: number
}

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

const toThreadTurns = (detail: SessionDetail): ThreadTurn[] =>
  detail.turns.map((turn) => ({
    description: turn.description,
    attachmentNames: turn.attachment_names,
    text: turn.estimate,
    meta: { prompt_version: turn.prompt_version, cache_hit: turn.cache_hit },
  }))

/**
 * Conversation-scoped estimation: owns one server session, resumes the last one from
 * localStorage on mount (or creates a new one) and rebuilds the thread from the turns the server
 * returns. Also lists the server's sessions and switches between them. A new run aborts the
 * previous one.
 */
export function useSession() {
  const [turns, setTurns] = useState<ThreadTurn[]>([])
  const [pending, setPending] = useState<PendingTurn | null>(null)
  // Failures that belong to no turn: creating, resuming or switching sessions.
  const [error, setError] = useState<string | null>(null)
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

  /** Makes a server session the active one, showing its memory and the turns the server kept. */
  const adopt = useCallback((detail: SessionDetail) => {
    sessionIdRef.current = detail.session_id
    writeStoredSessionId(detail.session_id)
    setSession({ id: detail.session_id, metadata: detail.project_metadata, turns: detail.history_turns })
    setTurns(toThreadTurns(detail))
    setPending(null)
    setError(null)
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
        setError(messageOf(error))
      })
    return () => {
      // Invalidates a pending creation (StrictMode double mount keeps only the last one).
      invalidate()
      controller.abort()
    }
  }, [abortInFlight, startSession, invalidate, adopt, refreshSessions])

  const run = useCallback(
    /** Resolves true when the turn was added to the thread (the composer can then clear). */
    async (request: EstimationRequest, files: File[]): Promise<boolean> => {
      const controller = abortInFlight()
      const { signal } = controller
      const attachmentNames = files.map((file) => file.name)
      const sent = { description: request.description, attachmentNames }
      setError(null)
      setPending({ ...sent, status: 'loading', error: null })

      try {
        let id = sessionIdRef.current ?? (await startSession(signal))
        if (id === null) return false

        let response
        try {
          response = await createSessionEstimate(id, request, files, signal)
        } catch (error) {
          // The server forgot the session (e.g. it restarted): start over once, memory is lost.
          if (!(error instanceof ApiError) || error.status !== 404) throw error
          id = await startSession(signal)
          if (id === null) return false
          // A restarted session has no history: the earlier turns belong to the lost one.
          setTurns([])
          response = await createSessionEstimate(id, request, files, signal)
        }

        if (signal.aborted) return false
        setTurns((current) => [
          ...current,
          {
            ...sent,
            text: response.text,
            meta: { prompt_version: response.prompt_version, cache_hit: response.cache_hit },
          },
        ])
        setPending(null)
        setSession({ id, metadata: response.project_metadata, turns: response.history_turns })
        void refreshSessions()
        return true
      } catch (error) {
        if (isAbort(error) || signal.aborted) return false
        setPending({ ...sent, status: 'error', error: messageOf(error) })
        return false
      }
    },
    [abortInFlight, startSession, refreshSessions],
  )

  const newConversation = useCallback(async () => {
    const controller = abortInFlight()
    setTurns([])
    setPending(null)
    setError(null)
    try {
      await startSession(controller.signal)
      if (!controller.signal.aborted) void refreshSessions()
    } catch (error) {
      if (isAbort(error) || controller.signal.aborted) return
      setError(messageOf(error))
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
        setPending(null) // the run this switch aborted would otherwise stay "loading" forever
        setError(messageOf(error))
      }
    },
    [abortInFlight, adopt, refreshSessions],
  )

  return { turns, pending, error, session, sessions, run, newConversation, selectSession }
}
