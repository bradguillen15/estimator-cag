import { useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent, KeyboardEvent } from 'react'

import { DESCRIPTION_MAX, DESCRIPTION_MIN, MAX_ATTACHMENTS } from '../api/types'
import type { DetailLevel, EstimationInput, OutputFormat, ProjectType } from '../api/types'
import { useLocale, useT } from '../i18n/useLocale'
import { detailLevelOptions, outputFormatOptions, projectTypeOptions } from '../i18n/messages'
import { Chevron, Paperclip } from './icons'

interface EstimateFormProps {
  busy: boolean
  onSubmit: (input: EstimationInput, files: File[]) => void
}

export function EstimateForm({ busy, onSubmit }: EstimateFormProps) {
  const t = useT()
  const locale = useLocale()
  const [description, setDescription] = useState('')
  const [projectType, setProjectType] = useState<ProjectType>('mobile_app')
  const [detailLevel, setDetailLevel] = useState<DetailLevel>('medium')
  const [outputFormat, setOutputFormat] = useState<OutputFormat>('phases_table')
  const [files, setFiles] = useState<File[]>([])
  const [capped, setCapped] = useState(false)
  const [rejected, setRejected] = useState(false)
  const [dragging, setDragging] = useState(false)

  const length = description.trim().length
  const valid = length >= DESCRIPTION_MIN && length <= DESCRIPTION_MAX

  const submit = () => {
    if (!valid || busy) return
    onSubmit(
      {
        description: description.trim(),
        project_type: projectType,
        detail_level: detailLevel,
        output_format: outputFormat,
      },
      files,
    )
  }

  const addFiles = (picked: File[]) => {
    // Drops bypass the input's `accept`, so filter here for both paths.
    const supported = picked.filter(isSupported)
    setRejected(supported.length < picked.length)
    const merged = [...files, ...supported]
    setCapped(merged.length > MAX_ATTACHMENTS)
    setFiles(merged.slice(0, MAX_ATTACHMENTS))
  }

  const pickFiles = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files ?? []))
    event.target.value = '' // allow picking the same file again after removing it
  }

  const handleDragOver = (event: DragEvent<HTMLElement>) => {
    if (!event.dataTransfer.types.includes('Files')) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    setDragging(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLElement>) => {
    // Ignore leave events fired when the pointer moves onto a child element.
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
    setDragging(false)
  }

  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    setDragging(false)
    addFiles(Array.from(event.dataTransfer.files))
  }

  const removeFile = (index: number) => {
    setCapped(false)
    setRejected(false)
    setFiles((current) => current.filter((_, position) => position !== index))
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    submit()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="animate-enter rounded-[22px] bg-surface p-5 shadow-card [animation-delay:90ms] md:p-7"
    >
      <label htmlFor="description" className="mb-2 flex items-baseline justify-between text-[13px] font-medium">
        {t('form.description')}
        <span className={`font-mono text-xs font-normal tabular-nums ${length > 0 && !valid ? 'text-danger' : 'text-faint'}`}>
          {length} / {DESCRIPTION_MAX}
          {length > 0 && length < DESCRIPTION_MIN && ` · ${t('form.description.min', { min: DESCRIPTION_MIN })}`}
        </span>
      </label>
      <textarea
        id="description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        onKeyDown={handleKeyDown}
        maxLength={DESCRIPTION_MAX}
        placeholder={t('form.placeholder')}
        className={`${CONTROL} block min-h-[120px] resize-y px-3.5 py-3 leading-relaxed placeholder:text-faint`}
      />

      <div className="mt-5">
        <label htmlFor="attachments" className="mb-2 block text-[13px] font-medium">
          {t('form.attachments')}
        </label>
        <input id="attachments" type="file" multiple accept={ACCEPT} onChange={pickFiles} className="peer sr-only" />
        <label
          htmlFor="attachments"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          data-dragging={dragging || undefined}
          className="flex cursor-pointer items-center justify-center gap-2 rounded-[14px] border border-dashed border-line-strong bg-field px-3 py-3.5 text-[13px] text-muted transition-[background-color,border-color,color] duration-150 ease-out-strong peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent hover:border-accent hover:text-ink data-dragging:border-accent data-dragging:bg-accent-soft data-dragging:text-ink"
        >
          <Paperclip className="size-4 flex-none" />
          <span>
            {t('form.attachments.drop')} <span className="font-medium text-accent">{t('form.attachments.browse')}</span>
          </span>
        </label>
        <p className={`mt-1.5 text-xs ${capped || rejected ? 'text-danger' : 'text-faint'}`}>
          {rejected ? t('form.attachments.unsupported') : t('form.attachments.hint', { max: MAX_ATTACHMENTS })}
        </p>
        {files.length > 0 && (
          <ul className="mt-2 grid gap-1.5">
            {files.map((file, index) => (
              <li
                key={`${file.name}-${index}`}
                className="flex items-center justify-between gap-3 rounded-[10px] bg-field px-3 py-1.5 font-mono text-xs shadow-[0_0_0_1px_var(--line)]"
              >
                <span className="truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  aria-label={t('form.attachments.remove', { name: file.name })}
                  className="cursor-pointer text-muted hover:text-danger focus-visible:outline-2 focus-visible:outline-accent"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-5 grid gap-3.5 md:grid-cols-3">
        <Select
          id="project_type"
          label={t('form.projectType')}
          value={projectType}
          options={projectTypeOptions(locale)}
          onChange={setProjectType}
        />
        <Select
          id="detail_level"
          label={t('form.detailLevel')}
          value={detailLevel}
          options={detailLevelOptions(locale)}
          onChange={setDetailLevel}
        />
        <Select
          id="output_format"
          label={t('form.outputFormat')}
          value={outputFormat}
          options={outputFormatOptions(locale)}
          onChange={setOutputFormat}
        />
      </div>

      <div className="mt-6 flex items-center justify-between gap-4">
        <span className="hidden text-xs text-faint sm:inline">
          <Kbd>⌘</Kbd> <Kbd>↵</Kbd> {t('form.shortcut')}
        </span>
        <button
          type="submit"
          disabled={!valid || busy}
          className="ml-auto inline-flex h-11 cursor-pointer items-center gap-2.5 rounded-full bg-btn px-6 font-semibold text-btn-ink transition-[transform,opacity] duration-150 ease-out-strong focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-accent enabled:active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-35"
        >
          {busy && (
            <span
              aria-hidden="true"
              className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent [animation-duration:600ms]"
            />
          )}
          {busy ? t('form.submitting') : t('form.submit')}
        </button>
      </div>
    </form>
  )
}

const ACCEPT = '.pdf,.docx'

function isSupported(file: File): boolean {
  return /\.(pdf|docx)$/i.test(file.name)
}

const CONTROL =
  'w-full rounded-[14px] bg-field outline-none transition-shadow duration-150 hover:shadow-[0_0_0_1px_var(--line-strong)] focus:shadow-[0_0_0_1px_var(--accent),0_0_0_4px_var(--accent-soft)]'

interface SelectProps<T extends string> {
  id: string
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}

function Select<T extends string>({ id, label, value, options, onChange }: SelectProps<T>) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-[13px] font-medium">
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value as T)}
          className={`${CONTROL} h-[42px] cursor-pointer appearance-none pr-9 pl-3`}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value} className="bg-field text-ink">
              {option.label}
            </option>
          ))}
        </select>
        <Chevron className="pointer-events-none absolute top-1/2 right-3 size-3 -translate-y-1/2 text-muted" />
      </div>
    </div>
  )
}

function Kbd({ children }: { children: string }) {
  return <kbd className="rounded-[5px] bg-field px-1.5 py-px font-mono text-[11px] shadow-[0_0_0_1px_var(--line-strong)]">{children}</kbd>
}
