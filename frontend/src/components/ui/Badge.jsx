import { Icon } from './Icon.jsx'

const TONES = {
  green: 'badge-green',
  blue: 'badge-blue',
  red: 'badge-red',
  purple: 'badge-purple',
  gray: 'badge-gray',
}

const TONE_DOTS = {
  green: 'text-ok',
  blue: 'text-accent',
  red: 'text-danger',
  purple: 'text-band',
  gray: 'text-txt-low',
}

export function Badge({ tone = 'gray', dot = true, icon, className = '', children }) {
  return (
    <span className={`${TONES[tone] ?? TONES.gray} ${className}`}>
      {icon && <Icon name={icon} size={12} />}
      {dot && !icon && (
        <span className={`h-1.5 w-1.5 rounded-full bg-current ${TONE_DOTS[tone] ?? TONE_DOTS.gray}`} />
      )}
      {children}
    </span>
  )
}