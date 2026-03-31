import { Loader2 } from 'lucide-react'

export default function LoadingSpinner({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-6 h-6 text-accent-teal animate-spin mr-3" />
      <span className="text-text-secondary text-sm">{message}</span>
    </div>
  )
}
