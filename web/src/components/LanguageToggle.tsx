import type { ResponseLanguage } from '../api/types'
import { useLocale, useT } from '../i18n/useLocale'
import { languageOptions } from '../i18n/messages'
import { SegmentedControl } from './SegmentedControl'
import type { SegmentOption } from './SegmentedControl'

interface LanguageToggleProps {
  value: ResponseLanguage
  onChange: (language: ResponseLanguage) => void
  compact?: boolean
}

export function LanguageToggle({ value, onChange, compact }: LanguageToggleProps) {
  const t = useT()
  const locale = useLocale()
  const options: SegmentOption<ResponseLanguage>[] = languageOptions(locale).map(({ value: optionValue, label }) => ({
    value: optionValue,
    label,
    icon: (
      <span aria-hidden="true" className="font-mono text-[10px] tracking-wide uppercase opacity-70">
        {optionValue}
      </span>
    ),
  }))

  return (
    <SegmentedControl name="response-language" label={t('language.label')} value={value} options={options} onChange={onChange} compact={compact} />
  )
}
