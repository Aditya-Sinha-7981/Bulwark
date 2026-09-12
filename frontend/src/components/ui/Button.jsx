import { Icon } from './Icon.jsx'

export function Button({
  variant = 'primary',
  icon,
  iconRight,
  size = 'md',
  className = '',
  children,
  ...props
}) {
  const variantClass =
    variant === 'primary' ? 'btn-primary' : variant === 'ghost' ? 'btn-ghost' : 'btn-quiet'
  const sizeClass = size === 'sm' ? 'h-8 px-2.5 text-[13px]' : ''

  return (
    <button className={`btn ${variantClass} ${sizeClass} ${className}`} {...props}>
      {icon && <Icon name={icon} size={16} />}
      {children}
      {iconRight && <Icon name={iconRight} size={16} />}
    </button>
  )
}