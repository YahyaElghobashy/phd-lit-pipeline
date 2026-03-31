import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

interface TerminalPanelProps {
  className?: string
}

export default function TerminalPanel({ className = '' }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const fitRef = useRef<FitAddon | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const term = new Terminal({
      theme: {
        background: '#2D2117',
        foreground: '#F3EDE5',
        cursor: '#C4704B',
        selectionBackground: '#C4704B40',
        black: '#2D2117',
        red: '#BF5540',
        green: '#5B8C5A',
        yellow: '#C4944B',
        blue: '#6B8FAD',
        magenta: '#9B7BA8',
        cyan: '#7B9E87',
        white: '#F3EDE5',
        brightBlack: '#8C7A68',
        brightRed: '#D4705A',
        brightGreen: '#7BAC7A',
        brightYellow: '#D4A85B',
        brightBlue: '#8BAFC8',
        brightMagenta: '#B59BC2',
        brightCyan: '#9BBEA7',
        brightWhite: '#FAF6F1',
      },
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: 13,
      lineHeight: 1.4,
      cursorBlink: true,
      scrollback: 10000,
    })

    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(containerRef.current)

    // Small delay to let the DOM settle before fitting
    setTimeout(() => fit.fit(), 50)

    termRef.current = term
    fitRef.current = fit

    // Connect WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/terminal`
    let ws: WebSocket

    function connect() {
      ws = new WebSocket(wsUrl)
      ws.binaryType = 'arraybuffer'

      ws.onopen = () => {
        term.writeln('\x1b[2m── Terminal connected ──\x1b[0m')
        term.writeln('')
        // Send initial size
        const dims = fit.proposeDimensions()
        if (dims) {
          ws.send(JSON.stringify({ type: 'resize', cols: dims.cols, rows: dims.rows }))
        }
      }

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          term.write(new Uint8Array(event.data))
        } else {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'exit') {
              term.writeln(`\r\n\x1b[2m── Process exited (code ${msg.code}) ──\x1b[0m`)
            } else if (msg.type === 'started') {
              term.writeln(`\x1b[33m▶ Running: ${msg.command}\x1b[0m`)
              term.writeln('')
            }
          } catch {
            term.write(event.data)
          }
        }
      }

      ws.onclose = () => {
        setTimeout(connect, 3000) // Reconnect after 3s
      }

      wsRef.current = ws
    }

    connect()

    // Handle resize
    const observer = new ResizeObserver(() => {
      fit.fit()
      const dims = fit.proposeDimensions()
      if (dims && ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: dims.cols, rows: dims.rows }))
      }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      ws?.close()
      term.dispose()
    }
  }, [])

  return (
    <div className={`overflow-hidden rounded-xl border border-border ${className}`}>
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#2D2117] border-b border-[#3D3127]">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <div className="w-3 h-3 rounded-full bg-[#BF5540]/70" />
            <div className="w-3 h-3 rounded-full bg-[#C4944B]/70" />
            <div className="w-3 h-3 rounded-full bg-[#5B8C5A]/70" />
          </div>
          <span className="text-xs text-[#8C7A68] font-mono ml-2">Pipeline Terminal</span>
        </div>
        <button
          onClick={() => termRef.current?.clear()}
          className="text-xs text-[#8C7A68] hover:text-[#F3EDE5] transition-colors"
        >
          Clear
        </button>
      </div>
      <div ref={containerRef} className="h-[400px] p-1 bg-[#2D2117]" />
    </div>
  )
}
