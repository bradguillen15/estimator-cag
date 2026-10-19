#!/usr/bin/env node
// Runs the API (FastAPI on :8000) and the UI (Vite on :5173) together, with prefixed logs.
// Ctrl+C stops both; if either process exits, the other one is stopped too.
// Postgres (ingestion jobs + pseudonym mappings) is always started via Docker and migrated
// (`alembic upgrade head`) before the API; Redis only when a cache flag is enabled. Both are stopped
// on exit only if this script started them.
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { parseEnv } from 'node:util'

const PROCESSES = [
  { name: 'api', color: 36, command: 'uv', args: ['run', 'uvicorn', 'app.main:app', '--reload'] },
  { name: 'web', color: 35, command: 'pnpm', args: ['--filter', 'estimator-web', 'dev'] },
]

const children = []
let stopping = false
let redisStartedHere = false
let postgresStartedHere = false

const TRUTHY = new Set(['1', 'true', 'yes', 'on'])
const REDIS_LABEL = '\x1b[31m[redis]\x1b[0m'
const POSTGRES_LABEL = '\x1b[34m[postgres]\x1b[0m'

// Mirrors the app: a real env var wins over `.env`. Values are never printed.
function cacheEnabled() {
  let fileEnv = {}
  const envFile = new URL('../.env', import.meta.url)
  if (existsSync(envFile)) {
    try {
      fileEnv = parseEnv(readFileSync(envFile, 'utf8'))
    } catch {
      fileEnv = {}
    }
  }
  return ['CACHE_ENABLED', 'SEMANTIC_CACHE_ENABLED'].some((name) => {
    const value = process.env[name] ?? fileEnv[name]
    return TRUTHY.has(String(value ?? '').trim().toLowerCase())
  })
}

function startRedis() {
  if (!cacheEnabled()) {
    process.stdout.write(`${REDIS_LABEL} skipped (no cache enabled)\n`)
    return
  }
  process.stdout.write(`${REDIS_LABEL} starting Redis via Docker…\n`)
  const result = spawnSync('docker', ['compose', 'up', '-d', '--wait', 'redis'], {
    stdio: 'ignore',
    shell: process.platform === 'win32',
  })
  if (result.status === 0) {
    redisStartedHere = true
    process.stdout.write(`${REDIS_LABEL} ready on localhost:6379\n`)
  } else {
    process.stderr.write(`${REDIS_LABEL} warning: could not start Redis (is Docker installed and running?); the cache will degrade to no cache\n`)
  }
}

function stopRedis() {
  if (!redisStartedHere) return
  redisStartedHere = false
  process.stdout.write(`${REDIS_LABEL} stopping…\n`)
  spawnSync('docker', ['compose', 'stop', 'redis'], { stdio: 'ignore', shell: process.platform === 'win32' })
}

function startPostgres() {
  process.stdout.write(`${POSTGRES_LABEL} starting Postgres via Docker…\n`)
  const result = spawnSync('docker', ['compose', 'up', '-d', '--wait', 'estimator-postgres'], {
    stdio: 'ignore',
    shell: process.platform === 'win32',
  })
  if (result.status !== 0) {
    process.stderr.write(`${POSTGRES_LABEL} warning: could not start Postgres (is Docker installed and running?); the ingestion endpoints will fail\n`)
    return
  }
  postgresStartedHere = true
  process.stdout.write(`${POSTGRES_LABEL} ready on localhost:5433; applying migrations…\n`)
  const migration = spawnSync('uv', ['run', 'alembic', 'upgrade', 'head'], {
    encoding: 'utf8',
    shell: process.platform === 'win32',
  })
  for (const [stream, target] of [[migration.stdout, process.stdout], [migration.stderr, process.stderr]]) {
    for (const line of (stream ?? '').split('\n')) if (line) target.write(`${POSTGRES_LABEL} ${line}\n`)
  }
  if (migration.status === 0) {
    process.stdout.write(`${POSTGRES_LABEL} migrations up to date\n`)
  } else {
    process.stderr.write(`${POSTGRES_LABEL} warning: migrations failed; the ingestion endpoints may fail\n`)
  }
}

function stopPostgres() {
  if (!postgresStartedHere) return
  postgresStartedHere = false
  process.stdout.write(`${POSTGRES_LABEL} stopping…\n`)
  spawnSync('docker', ['compose', 'stop', 'estimator-postgres'], { stdio: 'ignore', shell: process.platform === 'win32' })
}

function pipeWithPrefix(stream, target, label) {
  let pending = ''
  stream.setEncoding('utf8')
  stream.on('data', (chunk) => {
    const lines = (pending + chunk).split('\n')
    pending = lines.pop()
    for (const line of lines) target.write(`${label} ${line}\n`)
  })
  stream.on('end', () => pending && target.write(`${label} ${pending}\n`))
}

function stopAll(exitCode) {
  if (stopping) return
  stopping = true
  process.exitCode = exitCode
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM')
  }
  stopRedis()
  stopPostgres()
}

startRedis()
startPostgres()

for (const { name, color, command, args } of PROCESSES) {
  const label = `\x1b[${color}m[${name}]\x1b[0m`
  const child = spawn(command, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, FORCE_COLOR: '1' },
    shell: process.platform === 'win32',
  })
  pipeWithPrefix(child.stdout, process.stdout, label)
  pipeWithPrefix(child.stderr, process.stderr, label)

  child.on('error', (error) => {
    process.stderr.write(`${label} could not start \`${command}\`: ${error.message}\n`)
    stopAll(1)
  })
  child.on('exit', (code, signal) => {
    if (!stopping) process.stderr.write(`${label} exited (${signal ?? `code ${code}`}); stopping the rest…\n`)
    stopAll(code ?? 0)
  })
  children.push(child)
}

process.on('SIGINT', () => stopAll(0))
process.on('SIGTERM', () => stopAll(0))
