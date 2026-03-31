import { useEffect, useState } from 'react'
import { CheckCircle, Info, X } from 'lucide-react'

export interface ToastMessage {
  id: string
  text: string
  variant?: 'info' | 'success'
}

let _addToast: ((msg: Omit<ToastMessage, 'id'>) => void) | null = null

/** Imperatively show a toast from anywhere. */
export function showToast(text: string, variant: 'info' | 'success' = 'info') {
  _addToast?.({ text, variant })
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  useEffect(() => {
    _addToast = (msg) => {
      const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
      setToasts((prev) => [...prev, { ...msg, id }])
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 3500)
    }
    return () => { _addToast = null }
  }, [])

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl bg-bg-surface border border-border shadow-lg text-sm animate-slide-up"
        >
          {t.variant === 'success' ? (
            <CheckCircle className="w-4 h-4 text-success shrink-0" />
          ) : (
            <Info className="w-4 h-4 text-accent-teal shrink-0" />
          )}
          <span className="text-text-primary">{t.text}</span>
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            className="ml-2 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
