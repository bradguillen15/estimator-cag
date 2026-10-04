import type { DetailLevel, OutputFormat, ProjectType, ResponseLanguage } from '../api/types'

export type Locale = ResponseLanguage

type Vars = Record<string, string | number>

const es = {
  'brand.name': 'Estimator CAG',
  'hero.badge': 'Cache-Augmented Generation',
  'hero.title.before': 'Estimador de',
  'hero.title.em': 'software',
  'hero.subtitle.before': 'Describe el proyecto y elige tipo, detalle y formato. El formulario construye un',
  'hero.subtitle.after': 'y lo envía al servicio.',

  'sidebar.api': 'API',
  'sidebar.session': 'Conversación',
  'sidebar.session.id': 'ID de sesión',
  'sidebar.session.memory': 'Memoria del proyecto',
  'sidebar.session.memory.name': 'Nombre',
  'sidebar.session.memory.team': 'Equipo asumido',
  'sidebar.session.memory.tech': 'Tecnologías',
  'sidebar.session.memory.scope': 'Alcance acordado',
  'sidebar.session.turns': 'Turnos en el historial: {count}',
  'sidebar.session.hint': 'La memoria guarda los hechos del proyecto; el historial, los últimos turnos.',
  'sidebar.session.new': 'Nueva conversación',
  'sidebar.cag': 'Contexto CAG',
  'sidebar.cag.hint': 'Ejemplos inyectados en el system prompt del servidor.',
  'sidebar.examples': 'Ejemplos estáticos',
  'sidebar.examples.loading': 'Cargando ejemplos…',
  'sidebar.language': 'Idioma',
  'sidebar.language.hint': 'Se aplica a la interfaz y a la siguiente estimación.',
  'sidebar.appearance': 'Apariencia',

  'api.checking': 'Comprobando API',
  'api.up': 'API disponible',
  'api.down': 'API no disponible',

  'theme.label': 'Tema',
  'theme.light': 'Claro',
  'theme.dark': 'Oscuro',

  'language.label': 'Idioma',
  'language.es': 'Español',
  'language.en': 'English',

  'form.description': 'Transcripción o descripción del proyecto',
  'form.description.min': 'mínimo {min}',
  'form.placeholder':
    'Ej.: Necesitamos un MVP web de e-commerce con catálogo, carrito, pagos y panel de administración…',
  'form.attachments': 'Adjuntos (PDF o Word)',
  'form.attachments.hint': 'Máximo {max} archivos; se ignoran los extra.',
  'form.attachments.remove': 'Quitar {name}',
  'form.projectType': 'Tipo de proyecto',
  'form.detailLevel': 'Nivel de detalle',
  'form.outputFormat': 'Formato de salida',
  'form.shortcut': 'para generar',
  'form.submit': 'Generar estimación',
  'form.submitting': 'Generando…',

  'projectType.mobile_app': 'App móvil',
  'projectType.web_saas': 'Web / SaaS',
  'projectType.internal_tool': 'Herramienta interna',
  'projectType.data_pipeline': 'Pipeline de datos',

  'detailLevel.summary': 'Resumen',
  'detailLevel.medium': 'Medio',
  'detailLevel.detailed': 'Detallado',

  'outputFormat.phases_table': 'Tabla por fases',
  'outputFormat.line_items': 'Partidas / line items',
  'outputFormat.narrative': 'Narrativo',

  'result.heading': 'Estimación',
  'result.generating': 'Generando estimación',
  'result.cached': 'desde caché',

  'error.connect':
    'No se pudo conectar a la API en {api}. Levanta el servicio con: uv run uvicorn app.main:app --reload',
  'error.http': 'Error HTTP {status}: {detail}',
  'error.unknown': 'Error desconocido',
} as const

const en: { [K in keyof typeof es]: string } = {
  'brand.name': 'CAG Estimator',
  'hero.badge': 'Cache-Augmented Generation',
  'hero.title.before': 'Software',
  'hero.title.em': 'estimator',
  'hero.subtitle.before': 'Describe the project and pick type, detail and format. The form builds an',
  'hero.subtitle.after': 'and sends it to the service.',

  'sidebar.api': 'API',
  'sidebar.session': 'Conversation',
  'sidebar.session.id': 'Session ID',
  'sidebar.session.memory': 'Project memory',
  'sidebar.session.memory.name': 'Name',
  'sidebar.session.memory.team': 'Assumed team',
  'sidebar.session.memory.tech': 'Technologies',
  'sidebar.session.memory.scope': 'Agreed scope',
  'sidebar.session.turns': 'Turns in history: {count}',
  'sidebar.session.hint': 'Memory keeps the project facts; history keeps the latest turns.',
  'sidebar.session.new': 'New conversation',
  'sidebar.cag': 'CAG context',
  'sidebar.cag.hint': 'Examples injected into the server system prompt.',
  'sidebar.examples': 'Static examples',
  'sidebar.examples.loading': 'Loading examples…',
  'sidebar.language': 'Language',
  'sidebar.language.hint': 'Applies to the UI and the next estimate.',
  'sidebar.appearance': 'Appearance',

  'api.checking': 'Checking API',
  'api.up': 'API available',
  'api.down': 'API unavailable',

  'theme.label': 'Theme',
  'theme.light': 'Light',
  'theme.dark': 'Dark',

  'language.label': 'Language',
  'language.es': 'Español',
  'language.en': 'English',

  'form.description': 'Transcript or project description',
  'form.description.min': 'minimum {min}',
  'form.placeholder':
    'e.g. We need a web e-commerce MVP with catalog, cart, payments and an admin panel…',
  'form.attachments': 'Attachments (PDF or Word)',
  'form.attachments.hint': 'Up to {max} files; extras are ignored.',
  'form.attachments.remove': 'Remove {name}',
  'form.projectType': 'Project type',
  'form.detailLevel': 'Detail level',
  'form.outputFormat': 'Output format',
  'form.shortcut': 'to generate',
  'form.submit': 'Generate estimate',
  'form.submitting': 'Generating…',

  'projectType.mobile_app': 'Mobile app',
  'projectType.web_saas': 'Web / SaaS',
  'projectType.internal_tool': 'Internal tool',
  'projectType.data_pipeline': 'Data pipeline',

  'detailLevel.summary': 'Summary',
  'detailLevel.medium': 'Medium',
  'detailLevel.detailed': 'Detailed',

  'outputFormat.phases_table': 'Phases table',
  'outputFormat.line_items': 'Line items',
  'outputFormat.narrative': 'Narrative',

  'result.heading': 'Estimate',
  'result.generating': 'Generating estimate',
  'result.cached': 'cached',

  'error.connect':
    'Could not connect to the API at {api}. Start the service with: uv run uvicorn app.main:app --reload',
  'error.http': 'HTTP error {status}: {detail}',
  'error.unknown': 'Unknown error',
}

export type MessageKey = keyof typeof es

const catalogs: Record<Locale, Record<MessageKey, string>> = { es, en }

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(vars[key] ?? `{${key}}`))
}

export function translate(locale: Locale, key: MessageKey, vars?: Vars): string {
  return interpolate(catalogs[locale][key] ?? catalogs.es[key], vars)
}

const PROJECT_TYPE_VALUES: ProjectType[] = ['mobile_app', 'web_saas', 'internal_tool', 'data_pipeline']
const DETAIL_LEVEL_VALUES: DetailLevel[] = ['summary', 'medium', 'detailed']
const OUTPUT_FORMAT_VALUES: OutputFormat[] = ['phases_table', 'line_items', 'narrative']

export function projectTypeOptions(locale: Locale): { value: ProjectType; label: string }[] {
  return PROJECT_TYPE_VALUES.map((value) => ({
    value,
    label: translate(locale, `projectType.${value}`),
  }))
}

export function detailLevelOptions(locale: Locale): { value: DetailLevel; label: string }[] {
  return DETAIL_LEVEL_VALUES.map((value) => ({
    value,
    label: translate(locale, `detailLevel.${value}`),
  }))
}

export function outputFormatOptions(locale: Locale): { value: OutputFormat; label: string }[] {
  return OUTPUT_FORMAT_VALUES.map((value) => ({
    value,
    label: translate(locale, `outputFormat.${value}`),
  }))
}

export function languageOptions(locale: Locale): { value: ResponseLanguage; label: string }[] {
  return [
    { value: 'en', label: translate(locale, 'language.en') },
    { value: 'es', label: translate(locale, 'language.es') },
  ]
}
