// ============================================================
// FX — 未来感特效组件库
// 设计基调：quiet-luxury × sci-fi HUD
// 原则：动效服务信息层级，绝不喧宾夺主；
//       所有组件尊重 prefers-reduced-motion（降级为静态呈现）。
// ============================================================

import {
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type HTMLAttributes,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion/react'
import { cn } from '@/lib/utils'

/* ── GlobalGlowTrail 全局鼠标追踪流光 ────────────────────────
   跟随鼠标的流动光斑，营造沉浸式交互感 */
export function GlobalGlowTrail() {
  const [active, setActive] = useState(false)
  const [position, setPosition] = useState({ x: -1000, y: -1000 })
  const [isDark, setIsDark] = useState(false)
  const reduced = useReducedMotion()

  useEffect(() => {
    // 监听主题变化
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'))
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    setIsDark(document.documentElement.classList.contains('dark'))

    const onMove = (e: PointerEvent) => {
      setPosition({ x: e.clientX, y: e.clientY })
    }
    const onEnter = () => setActive(true)
    const onLeave = () => setActive(false)

    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerenter', onEnter)
    document.addEventListener('pointerleave', onLeave)

    return () => {
      observer.disconnect()
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerenter', onEnter)
      document.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  if (reduced) return null

  return (
    <div
      className={cn('fx-glow-trail', active && 'active')}
      style={{
        left: position.x,
        top: position.y,
        background: isDark
          ? 'radial-gradient(circle, rgba(139, 92, 246, 0.2) 0%, rgba(6, 182, 212, 0.1) 40%, transparent 70%)'
          : 'radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, rgba(6, 182, 212, 0.05) 40%, transparent 70%)',
      }}
    />
  )
}

/* ── InteractiveCard 交互式流光卡片 ─────────────────────────
   hover 时泛起流动光效 */
export function InteractiveCard({
  children,
  className,
  variant = 'default',
}: {
  children: ReactNode
  className?: string
  variant?: 'default' | 'glow' | 'rainbow'
}) {
  const [isHovered, setIsHovered] = useState(false)
  const [ripples, setRipples] = useState<{ x: number; y: number; id: number }[]>([])
  const ref = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()

  const handleClick = (e: React.PointerEvent) => {
    if (reduced) return
    const rect = ref.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const id = Date.now()
    setRipples((prev) => [...prev, { x, y, id }])
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== id))
    }, 1500)
  }

  return (
    <div
      ref={ref}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'relative transition-all duration-300',
        variant === 'rainbow' && 'fx-rainbow-border',
        variant === 'glow' && 'fx-flow-card',
        variant === 'default' && 'fx-card fx-card-hover',
        className,
      )}
    >
      {children}
      {/* 点击涟漪效果 */}
      {ripples.map((r) => (
        <span
          key={r.id}
          className="fx-ripple"
          style={{ left: r.x, top: r.y, width: 40, height: 40, marginLeft: -20, marginTop: -20 }}
        />
      ))}
    </div>
  )
}

/* ── ColorFlowButton 流光按钮 ────────────────────────────────
   hover 时边缘流动彩虹色 */
export function ColorFlowButton({
  children,
  className,
  variant = 'primary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' }) {
  const [isHovered, setIsHovered] = useState(false)
  const [ripples, setRipples] = useState<{ x: number; y: number; id: number }[]>([])
  const ref = useRef<HTMLButtonElement>(null)
  const reduced = useReducedMotion()

  const handleClick = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (reduced) return
    const rect = ref.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const id = Date.now()
    setRipples((prev) => [...prev, { x, y, id }])
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== id))
    }, 600)
    props.onClick?.(e as any)
  }

  const baseStyles = {
    primary: 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-white',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700',
    ghost: 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800',
  }

  return (
    <button
      ref={ref}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'relative overflow-hidden rounded-md font-medium transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/50',
        baseStyles[variant],
        className,
      )}
      {...props}
    >
      {/* 流光遮罩 */}
      <span
        className={cn(
          'absolute inset-0 bg-gradient-to-r from-cyan-500/0 via-violet-500/30 to-fuchsia-500/0',
          'bg-[length:200%_100%] transition-opacity duration-300',
          isHovered && !reduced ? 'opacity-100' : 'opacity-0',
        )}
        style={{
          backgroundPosition: isHovered && !reduced ? '100% 0' : '0% 0',
          transition: 'background-position 0.5s ease, opacity 0.3s ease',
        }}
      />
      <span className="relative z-10 inline-flex items-center gap-2">{children}</span>
      {/* 点击涟漪 */}
      {ripples.map((r) => (
        <span
          key={r.id}
          className="absolute bg-white/30 rounded-full"
          style={{
            left: r.x,
            top: r.y,
            width: 0,
            height: 0,
            marginLeft: 0,
            marginTop: 0,
            animation: 'fx-ripple-expand 0.6s ease-out forwards',
            pointerEvents: 'none',
          }}
        />
      ))}
    </button>
  )
}

/* ── ParticleField 粒子星域 ──────────────────────────────────
   Canvas 星点缓慢漂移 + 近邻连线 + 指针引力连线。
   页面隐藏时暂停 rAF 省电；主题切换时自动换色；
   reduced-motion 下只静态绘制一帧星点。 */
export function ParticleField({ density = 1, className }: { density?: number; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let raf = 0
    let w = 0
    let h = 0
    let parts: { x: number; y: number; vx: number; vy: number; r: number }[] = []
    const mouse = { x: -1e4, y: -1e4 }

    // 主题感知调色：暗色用电光青，浅色用石板灰，透明度均低于 0.6 保证不干扰前景
    const palette = () => {
      const dark = document.documentElement.classList.contains('dark')
      return dark
        ? { dot: 'rgba(165, 243, 252, ', dotA: 0.5, line: 'rgba(103, 232, 249, ', lineA: 0.1 }
        : { dot: 'rgba(71, 85, 105, ', dotA: 0.3, line: 'rgba(100, 116, 139, ', lineA: 0.08 }
    }
    let colors = palette()

    const LINK_DIST = 110
    const MOUSE_DIST = 150

    const resize = () => {
      const b = canvas.getBoundingClientRect()
      w = b.width
      h = b.height
      canvas.width = Math.max(1, Math.round(w * dpr))
      canvas.height = Math.max(1, Math.round(h * dpr))
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      // 密度随面积缩放，上限 130 颗防止大屏 O(n²) 连线过载
      const n = Math.min(130, Math.round(((w * h) / 16000) * density))
      parts = Array.from({ length: n }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
        r: Math.random() * 1.3 + 0.4,
      }))
    }

    const drawFrame = (animate: boolean) => {
      ctx.clearRect(0, 0, w, h)
      for (const p of parts) {
        if (animate) {
          p.x += p.vx
          p.y += p.vy
          if (p.x < -8) p.x = w + 8
          else if (p.x > w + 8) p.x = -8
          if (p.y < -8) p.y = h + 8
          else if (p.y > h + 8) p.y = -8
        }
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = `${colors.dot}${colors.dotA})`
        ctx.fill()
      }
      for (let i = 0; i < parts.length; i++) {
        const a = parts[i]
        for (let j = i + 1; j < parts.length; j++) {
          const b = parts[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK_DIST * LINK_DIST) {
            const t = 1 - Math.sqrt(d2) / LINK_DIST
            ctx.strokeStyle = `${colors.line}${(colors.lineA * t).toFixed(3)})`
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
        // 指针附近的星点朝光标牵出亮线，赋予「引力交互」感
        const mdx = a.x - mouse.x
        const mdy = a.y - mouse.y
        const md2 = mdx * mdx + mdy * mdy
        if (md2 < MOUSE_DIST * MOUSE_DIST) {
          const t = 1 - Math.sqrt(md2) / MOUSE_DIST
          ctx.strokeStyle = `${colors.line}${(colors.lineA * 2.2 * t).toFixed(3)})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.lineTo(mouse.x, mouse.y)
          ctx.stroke()
        }
      }
    }

    const loop = () => {
      drawFrame(true)
      raf = requestAnimationFrame(loop)
    }

    const start = () => {
      if (!raf && !reduced) raf = requestAnimationFrame(loop)
    }
    const stop = () => {
      if (raf) {
        cancelAnimationFrame(raf)
        raf = 0
      }
    }

    const onVisibility = () => (document.hidden ? stop() : start())
    const onResize = () => {
      resize()
      if (reduced) drawFrame(false)
    }
    const onPointer = (e: PointerEvent) => {
      const b = canvas.getBoundingClientRect()
      mouse.x = e.clientX - b.left
      mouse.y = e.clientY - b.top
    }
    const onPointerLeave = () => {
      mouse.x = -1e4
      mouse.y = -1e4
    }

    // 主题类名变化时刷新调色板（浅/深切换无需重建组件）
    const observer = new MutationObserver(() => {
      colors = palette()
      if (reduced) drawFrame(false)
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

    resize()
    if (reduced) {
      drawFrame(false)
    } else {
      start()
    }
    window.addEventListener('resize', onResize)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pointermove', onPointer, { passive: true })
    window.addEventListener('pointerout', onPointerLeave)

    return () => {
      stop()
      observer.disconnect()
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pointermove', onPointer)
      window.removeEventListener('pointerout', onPointerLeave)
    }
  }, [density, reduced])

  return <canvas ref={canvasRef} aria-hidden className={cn('absolute inset-0 h-full w-full', className)} />
}

/* ── AmbientBackground 全局氛围层 ────────────────────────────
   固定于视口：全息网格 + 三团极光 + 粒子星域 + 呼吸渐变。
   置于 -z-10，配合外层容器 isolate 保证内容永远在其上方。 */
export function AmbientBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* 呼吸渐变底层 */}
      <div className="absolute inset-0 fx-breathing-gradient" />
      <div className="absolute inset-0 fx-grid" />
      <div className="fx-aurora-blob absolute -top-36 -left-28 h-[48vh] w-[44vw] min-w-80 rounded-full bg-cyan-400" />
      <div className="fx-aurora-blob fx-delay-2 absolute top-[16vh] right-[-12vw] h-[44vh] w-[40vw] min-w-72 rounded-full bg-violet-500" />
      <div className="fx-aurora-blob fx-delay-3 absolute bottom-[-20vh] left-[20vw] h-[46vh] w-[42vw] min-w-72 rounded-full bg-fuchsia-400" />
      <ParticleField className="opacity-70" />
    </div>
  )
}

/* ── SpotlightCard 鼠标追光容器 ──────────────────────────────
   把指针坐标写入 CSS 变量，交给 .fx-spotlight::before 渲染光斑；
   JS 只做坐标注入，绘制全在合成层，零重排。 */
export function SpotlightCard({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null)

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el) return
    const b = el.getBoundingClientRect()
    el.style.setProperty('--spot-x', `${e.clientX - b.left}px`)
    el.style.setProperty('--spot-y', `${e.clientY - b.top}px`)
  }

  return (
    <div ref={ref} onPointerMove={onPointerMove} className={cn('fx-spotlight', className)} {...props}>
      {children}
    </div>
  )
}

/* ── TiltCard 3D 视差倾斜 ────────────────────────────────────
   指针位置驱动 rotateX/rotateY，spring 回弹；触屏/减动效自动关闭。 */
export function TiltCard({
  children,
  className,
  maxTilt = 6,
}: {
  children: ReactNode
  className?: string
  maxTilt?: number
}) {
  const reduced = useReducedMotion()
  const rx = useMotionValue(0)
  const ry = useMotionValue(0)
  const srx = useSpring(rx, { stiffness: 160, damping: 18 })
  const sry = useSpring(ry, { stiffness: 160, damping: 18 })

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (reduced || e.pointerType === 'touch') return
    const b = e.currentTarget.getBoundingClientRect()
    const px = (e.clientX - b.left) / b.width - 0.5
    const py = (e.clientY - b.top) / b.height - 0.5
    ry.set(px * maxTilt * 2)
    rx.set(-py * maxTilt * 2)
  }
  const onPointerLeave = () => {
    rx.set(0)
    ry.set(0)
  }

  return (
    <motion.div
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      style={{ rotateX: srx, rotateY: sry, transformPerspective: 900 }}
      className={cn('will-change-transform', className)}
    >
      {children}
    </motion.div>
  )
}

/* ── BorderBeam 旋转光束描边 ─────────────────────────────────
   父元素需 relative + rounded；光束沿边框巡游一圈。 */
export function BorderBeam({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn('fx-beam-mask pointer-events-none absolute inset-0 rounded-[inherit]', className)}>
      <span className="fx-beam" />
    </span>
  )
}

/* ── AnimatedNumber 数字弹簧滚动 ─────────────────────────────
   数值变化时以 spring 滚动到位；reduced-motion 下直出终值。 */
export function AnimatedNumber({
  value,
  format = (n: number) => n.toFixed(0),
  className,
}: {
  value: number
  format?: (n: number) => string
  className?: string
}) {
  const reduced = useReducedMotion()
  const mv = useMotionValue(reduced ? value : 0)
  const spring = useSpring(mv, { stiffness: 110, damping: 24, mass: 0.7 })
  const text = useTransform(spring, (v) => format(v))

  useEffect(() => {
    mv.set(value)
  }, [value, mv])

  if (reduced) return <span className={cn('tabular-nums', className)}>{format(value)}</span>
  return <motion.span className={cn('tabular-nums', className)}>{text}</motion.span>
}

/* ── DecodeText 全息解码文字 ─────────────────────────────────
   字符从乱码符号逐个「解码」为真实文本，营造 HUD 读取感。 */
const GLYPHS = '!<>-_\\/[]{}—=+*^?#'

export function DecodeText({
  text,
  className,
  duration = 850,
}: {
  text: string
  className?: string
  duration?: number
}) {
  const reduced = useReducedMotion()
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduced) {
      el.textContent = text
      return
    }
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      // easeOutCubic：前段快速揭示、尾段稳定收束
      const eased = 1 - Math.pow(1 - t, 3)
      const solved = Math.floor(eased * text.length)
      let out = text.slice(0, solved)
      for (let i = solved; i < text.length; i++) {
        out += text[i] === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0]
      }
      el.textContent = out
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [text, duration, reduced])

  // 首帧即渲染真实文本占好版面，避免解码期布局抖动
  return (
    <span ref={ref} className={className} aria-label={text}>
      {text}
    </span>
  )
}

/* ── Reveal 视口入场 ─────────────────────────────────────────
   进入视口时淡入上浮，一次性触发；列表用 delay 做 stagger。 */
export function Reveal({
  children,
  className,
  delay = 0,
  y = 14,
}: {
  children: ReactNode
  className?: string
  delay?: number
  y?: number
}) {
  const reduced = useReducedMotion()
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-36px' }}
      transition={{ duration: 0.5, delay, ease: [0.21, 0.47, 0.32, 0.98] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ── ProgressRing 辉光进度环 ─────────────────────────────────
   SVG 环形进度：渐变描边 + 辉光滤镜 + spring 平滑推进，
   中心插槽自由放置数字/状态。 */
export function ProgressRing({
  value,
  size = 132,
  stroke = 9,
  className,
  children,
}: {
  value: number // 0-100
  size?: number
  stroke?: number
  className?: string
  children?: ReactNode
}) {
  const gradId = useId()
  const reduced = useReducedMotion()
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const clamped = Math.min(100, Math.max(0, value))
  const offset = c * (1 - clamped / 100)

  return (
    <div className={cn('relative inline-flex items-center justify-center', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgb(34 211 238)" />
            <stop offset="55%" stopColor="rgb(139 92 246)" />
            <stop offset="100%" stopColor="rgb(236 72 153)" />
          </linearGradient>
        </defs>
        {/* 轨道 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          className="stroke-gray-200/80 dark:stroke-white/10"
        />
        {/* 进度弧：辉光由 drop-shadow 滤镜给出 */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${gradId})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={reduced ? false : { strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 60, damping: 20 }}
          style={{ filter: 'drop-shadow(0 0 6px rgb(34 211 238 / 0.5))' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  )
}

/* ── PulseDot 呼吸辉光圆点 ───────────────────────────────────
   在线 / 运行中状态指示。 */
export function PulseDot({ className, style }: { className?: string; style?: CSSProperties }) {
  return <span aria-hidden style={style} className={cn('fx-pulse-dot inline-block h-2 w-2 rounded-full', className)} />
}
