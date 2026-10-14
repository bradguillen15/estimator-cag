import type { Theme } from '../hooks/useTheme'
import { useT } from '../i18n/useLocale'
import { SegmentedControl } from './SegmentedControl'
import type { SegmentOption } from './SegmentedControl'

interface ThemeToggleProps {
  value: Theme
  onChange: (theme: Theme) => void
  compact?: boolean
}

export function ThemeToggle({ value, onChange, compact }: ThemeToggleProps) {
  const t = useT()

  const options: SegmentOption<Theme>[] = [
    {
      value: 'dark',
      label: t('theme.dark'),
      icon: (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" className="size-[13px]">
          <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
        </svg>
      ),
    },
    {
      value: 'light',
      label: t('theme.light'),
      icon: (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" className="size-[13px]">
          <circle cx="8" cy="8" r="3" />
          <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
        </svg>
      ),
    },
  ]

  return <SegmentedControl name="theme" label={t('theme.label')} value={value} options={options} onChange={onChange} compact={compact} />
}
