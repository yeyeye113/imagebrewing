// ============================================================
// Reusable UI Components
// 视觉体系：玻璃拟态卡片 + 电光辉光交互（fx-* 见 index.css）
// ============================================================

import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/* ── Card ────────────────────────────────────────────────── */
interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 交互卡片：hover 抬升 + 电光描边（列表项 / 可点击卡用） */
  interactive?: boolean
}

export function Card({ children, className, interactive, ...props }: CardProps) {
  return (
    <div className={cn('fx-card', interactive && 'fx-card-hover', className)} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-100 dark:border-gray-800', className)}>
      {children}
    </div>
  )
}

export function CardContent({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('px-4 sm:px-6 py-4', className)}>{children}</div>
}

/* ── Button ──────────────────────────────────────────────── */
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'fx-btn-primary bg-gray-900 text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white',
  secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 active:bg-gray-300 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700 active:scale-[0.98]',
  ghost: 'text-gray-600 hover:bg-gray-100 active:bg-gray-200 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200',
  danger: 'bg-red-50 text-red-600 hover:bg-red-100 active:bg-red-200 dark:bg-red-950/50 dark:text-red-400 dark:hover:bg-red-950 active:scale-[0.98]',
}

const buttonSizes: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
}

export function Button({ variant = 'primary', size = 'md', loading = false, className, children, disabled, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors gap-2',
        'disabled:opacity-50 disabled:pointer-events-none',
        'cursor-pointer',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50 focus-visible:ring-offset-1 dark:focus-visible:ring-offset-gray-950',
        buttonVariants[variant],
        buttonSizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  )
}

/* ── Slider ──────────────────────────────────────────────── */
interface SliderProps {
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  label?: string
  description?: string
  negative?: boolean
}

export function Slider({ value, onChange, min = 0, max = 100, step = 1, label, description, negative }: SliderProps) {
  const pct = ((value - min) / (max - min)) * 100
  const color = negative
    ? value > 60 ? 'bg-red-500' : value > 30 ? 'bg-amber-500' : 'bg-green-500'
    : value > 60 ? 'bg-green-500' : value > 30 ? 'bg-amber-500' : 'bg-red-500'

  return (
    <div className="space-y-1">
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
          <span className="text-sm text-gray-500 tabular-nums">{value}</span>
        </div>
      )}
      {description && <p className="text-xs text-gray-400">{description}</p>}
      <div className="relative">
        <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
          <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }} />
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
      </div>
    </div>
  )
}

/* ── Badge ───────────────────────────────────────────────── */
interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info'
  className?: string
}

const badgeVariants: Record<string, string> = {
  default: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300',
  success: 'bg-green-50 text-green-700 dark:bg-green-950/50 dark:text-green-400',
  warning: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400',
  danger: 'bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400',
  info: 'bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400',
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span className={cn('inline-flex items-center px-2 py-0.5 rounded text-xs font-medium', badgeVariants[variant], className)}>
      {children}
    </span>
  )
}

/* ── Input ───────────────────────────────────────────────── */
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function Input({ label, error, className, value, ...props }: InputProps) {
  return (
    <div className="space-y-1">
      {label && <label className="block text-sm font-medium text-gray-700">{label}</label>}
      <input
        className={cn(
          'w-full px-3 py-2 border rounded-md text-sm bg-white dark:bg-gray-900 dark:text-gray-100',
          'focus:outline-none focus:ring-2 focus:ring-gray-900/10 dark:focus:ring-gray-100/10 focus:border-gray-400 dark:focus:border-gray-600',
          'placeholder:text-gray-400 dark:placeholder:text-gray-500',
          error ? 'border-red-300 dark:border-red-800' : 'border-gray-200 dark:border-gray-700',
          className,
        )}
        {...props}
        value={value ?? ''}
      />
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

/* ── Textarea ────────────────────────────────────────────── */
interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
}

export function Textarea({ label, className, ...props }: TextareaProps) {
  return (
    <div className="space-y-1">
      {label && <label className="block text-sm font-medium text-gray-700">{label}</label>}
      <textarea
        className={cn(
          'w-full px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-md text-sm resize-y bg-white dark:bg-gray-900 dark:text-gray-100',
          'focus:outline-none focus:ring-2 focus:ring-gray-900/10 dark:focus:ring-gray-100/10 focus:border-gray-400 dark:focus:border-gray-600',
          'placeholder:text-gray-400 dark:placeholder:text-gray-500',
          className,
        )}
        rows={3}
        {...props}
      />
    </div>
  )
}

/* ── Tabs ────────────────────────────────────────────────── */
interface TabsProps<T extends string> {
  tabs: { key: T; label: string }[]
  active: T
  onChange: (key: T) => void
}

export function Tabs<T extends string>({ tabs, active, onChange }: TabsProps<T>) {
  return (
    <div className="flex gap-1 border-b border-gray-200 dark:border-gray-800">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            'px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer',
            active === tab.key
              ? 'border-gray-900 dark:border-gray-100 text-gray-900 dark:text-gray-100'
              : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

/* ── Collapsible ─────────────────────────────────────────── */
interface CollapsibleProps {
  title: string
  subtitle?: string
  defaultOpen?: boolean
  children: ReactNode
}

export function Collapsible({ title, subtitle, defaultOpen = false, children }: CollapsibleProps) {
  return (
    <details open={defaultOpen} className="group fx-card overflow-hidden">
      <summary className="flex items-center justify-between px-4 py-3 cursor-pointer select-none rounded-[inherit] hover:bg-gray-50/80 dark:hover:bg-gray-800/50 transition-colors">
        <div>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}</span>
          {subtitle && <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">{subtitle}</span>}
        </div>
        <span className="text-gray-400 group-open:rotate-180 transition-transform">▾</span>
      </summary>
      <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800">{children}</div>
    </details>
  )
}

/* ── Progress Bar ────────────────────────────────────────── */
export function ProgressBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div
      className={cn('h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden', className)}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="fx-progress-fill h-full rounded-full transition-[width] duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

/* ── Metric Card ─────────────────────────────────────────── */
export function MetricCard({
  label,
  value,
  subtext,
  className,
}: {
  label: string
  value: ReactNode
  subtext?: string
  className?: string
}) {
  return (
    <div
      className={cn(
        'group/metric relative overflow-hidden rounded-lg px-4 py-3',
        'bg-gray-50 dark:bg-gray-800/50 border border-transparent',
        'transition-colors duration-300 hover:border-cyan-500/25 dark:hover:border-cyan-400/25',
        className,
      )}
    >
      {/* hover 时右上角泛起一抹极光，提示该指标可关注 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-8 -top-8 h-20 w-20 rounded-full bg-gradient-to-br from-cyan-400/15 to-violet-500/15 opacity-0 blur-xl transition-opacity duration-300 group-hover/metric:opacity-100"
      />
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 dark:text-gray-100 tabular-nums">{value}</div>
      {subtext && <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">{subtext}</div>}
    </div>
  )
}

/* ── Empty State ─────────────────────────────────────────── */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      {icon && <div className="fx-float text-gray-300 dark:text-gray-600 mb-4">{icon}</div>}
      <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-1">{title}</h3>
      {description && <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 max-w-md">{description}</p>}
      {action}
    </div>
  )
}

/* ── Table ───────────────────────────────────────────────── */
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full text-sm">{children}</table>
    </div>
  )
}

export function Th({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <th className={cn('text-left font-medium text-gray-500 dark:text-gray-400 px-3 py-2 border-b border-gray-100 dark:border-gray-800', className)}>
      {children}
    </th>
  )
}

export function Td({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={cn('px-3 py-2 border-b border-gray-50 dark:border-gray-800/80 text-gray-700 dark:text-gray-300', className)}>{children}</td>
}
