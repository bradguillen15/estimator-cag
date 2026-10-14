import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, createSession, createSessionEstimate, createSessionReviewedEstimate, getSession, listSessions } from '../api/client'
import { EMPTY_PROJECT_METADATA } from '../api/types'
import type {
  Audience,
  EstimationRequest,
  GenerationMeta,
  ProjectMetadata,
  SessionDetail,
  SessionEstimationResponse,
  SessionReviewedEstimateResponse,
  SessionSummary,
} from '../api/types'

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
  /** The turn goes through the critic review (a longer wait). */
  review: boolean
  error: string | null
}

/** What the server remembers beyond the sliding window, plus the tier of the latest turn. */
export interface SessionMemory {
  anchors: number
  summaryChars: number
  audience: Audience | null
  audienceRule: string | null
}

export interface SessionInfo {
  /** Null while the session is being created (or creation failed). */
  id: string | null
  metadata: ProjectMetadata
  turns: number
  /** Absent until known (new or just-created sessions). */
  memory?: SessionMemory
}

const memoryOf = (detail: SessionDetail): SessionMemory => ({
  anchors: detail.anchors_count,
  summaryChars: detail.summary_chars,
  audience: detail.last_audience,
  audienceRule: detail.last_audience_rule,
})

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

const isReviewed = (response: SessionEstimationResponse): response is SessionReviewedEstimateResponse => 'final_verdict' in response
const isAbort = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError'
const messageOf = (error: unknown): string => (error instanceof Error ? error.message : String(error))

const toThreadTurns = (detail: SessionDetail): ThreadTurn[] =>
  detail.turns.map((turn) => ({
    description: turn.description,
    attachmentNames: turn.attachment_names,
    text: turn.estimate,
    meta: {
      prompt_version: turn.prompt_version,
      cache_hit: turn.cache_hit,
      ...(turn.final_verdict ? { final_verdict: turn.final_verdict } : {}),
    },
  }))

/** Per-turn audience is not stored: only the latest turn's tier is known on a rebuilt thread. */
const withLastAudience = (turns: ThreadTurn[], detail: SessionDetail): ThreadTurn[] =>
  turns.map((turn, index) =>
    index === turns.length - 1 && detail.last_audience && turn.meta
      ? { ...turn, meta: { ...turn.meta, audience: detail.last_audience, audience_rule: detail.last_audience_rule ?? undefined } }
      : turn,
  )

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
    setSession({ id: detail.session_id, metadata: detail.project_metadata, turns: detail.history_turns, memory: memoryOf(detail) })
    setTurns(withLastAudience(toThreadTurns(detail), detail))
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

  /** Best effort, like the list: anchors/summary live only in the session detail. */
  const refreshMemory = useCallback(async (id: string, signal: AbortSignal) => {
    try {
      const detail = await getSession(id, signal)
      if (signal.aborted || sessionIdRef.current !== id) return
      const memory = memoryOf(detail)
      setSession((current) => (current.id === id ? { ...current, memory } : current))
    } catch {
      // Keep the previous memory.
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
    async (request: EstimationRequest, files: File[], review = false): Promise<boolean> => {
      const controller = abortInFlight()
      const { signal } = controller
      const attachmentNames = files.map((file) => file.name)
      const sent = { description: request.description, attachmentNames }
      setError(null)
      setPending({ ...sent, status: 'loading', review, error: null })
      const send = review ? createSessionReviewedEstimate : createSessionEstimate

      try {
        let id = sessionIdRef.current ?? (await startSession(signal))
        if (id === null) return false

        let response: SessionEstimationResponse | SessionReviewedEstimateResponse
        try {
          response = await send(id, request, files, signal)
        } catch (error) {
          // The server forgot the session (e.g. it restarted): start over once, memory is lost.
          if (!(error instanceof ApiError) || error.status !== 404) throw error
          id = await startSession(signal)
          if (id === null) return false
          // A restarted session has no history: the earlier turns belong to the lost one.
          setTurns([])
          response = await send(id, request, files, signal)
        }

        if (signal.aborted) return false
        setTurns((current) => [
          ...current,
          {
            ...sent,
            text: response.text,
            meta: {
              prompt_version: response.prompt_version,
              cache_hit: response.cache_hit,
              audience: response.audience,
              audience_rule: response.audience_rule,
              ...(isReviewed(response) ? { final_verdict: response.final_verdict, iterations: response.iterations } : {}),
            },
          },
        ])
        setPending(null)
        setSession((current) => ({
          id,
          metadata: response.project_metadata,
          turns: response.history_turns,
          // Anchors/summary only come with the session detail (refreshed below); keep the last known ones.
          memory: {
            anchors: current.memory?.anchors ?? 0,
            summaryChars: current.memory?.summaryChars ?? 0,
            audience: response.audience,
            audienceRule: response.audience_rule,
          },
        }))
        void refreshSessions()
        void refreshMemory(id, signal)
        return true
      } catch (error) {
        if (isAbort(error) || signal.aborted) return false
        setPending({ ...sent, status: 'error', review, error: messageOf(error) })
        return false
      }
    },
    [abortInFlight, startSession, refreshSessions, refreshMemory],
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
