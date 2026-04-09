'use client'

export interface ToastItem {
  id: string
  fileName: string
  status: 'processing' | 'complete'
  analysisId: string
}

interface ToastStatusProps {
  items: ToastItem[]
  onItemClick: (item: ToastItem) => void
}

export function ToastStatus({ items, onItemClick }: ToastStatusProps) {
  const visible = items.filter((i) => i.status === 'processing' || i.status === 'complete')
  if (visible.length === 0) return null

  return (
    <div className="absolute bottom-8 right-6 z-10 flex flex-col gap-2 w-[280px]">
      {visible.map((item) => (
        <ToastCard key={item.id} item={item} onClick={() => onItemClick(item)} />
      ))}
    </div>
  )
}

function ToastCard({ item, onClick }: { item: ToastItem; onClick: () => void }) {
  const isComplete = item.status === 'complete'

  return (
    <div
      onClick={isComplete ? onClick : undefined}
      className="flex flex-col gap-2 px-4 py-3 transition-all"
      style={{
        background: 'rgba(23,26,29,0.95)',
        border: `1px solid ${isComplete ? 'rgba(129,236,255,0.25)' : 'rgba(70,72,75,0.25)'}`,
        borderRadius: 12,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        backdropFilter: 'blur(12px)',
        cursor: isComplete ? 'pointer' : 'default',
      }}
      role={isComplete ? 'button' : 'status'}
      aria-live="polite"
    >
      {/* Row 1: indicator + label + icon */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isComplete ? (
            <div className="h-2 w-2 rounded-full" style={{ background: '#81ecff' }} />
          ) : (
            <div
              className="h-2 w-2 rounded-full"
              style={{
                background: '#f59e0b',
                animation: 'toast-pulse 1.4s ease-in-out infinite',
              }}
            />
          )}
          <span
            className="font-inter"
            style={{ fontSize: 12, fontWeight: 600, color: '#f9f9fd' }}
          >
            {isComplete ? 'Analysis Complete' : 'Analyzing…'}
          </span>
        </div>

        {isComplete ? (
          /* checkmark */
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 6L5 9L10 3"
              stroke="#81ecff"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          /* spinner */
          <div
            className="h-3 w-3 rounded-full border"
            style={{
              borderColor: 'rgba(245,158,11,0.2)',
              borderTopColor: '#f59e0b',
              animation: 'toast-spin 0.9s linear infinite',
            }}
          />
        )}
      </div>

      {/* Row 2: file name */}
      <span
        className="font-inter truncate"
        style={{ fontSize: 11, color: '#aaabaf' }}
        title={item.fileName}
      >
        {item.fileName}
      </span>

      {/* Row 3: progress bar */}
      <div
        className="h-[3px] w-full overflow-hidden rounded-full"
        style={{ background: 'rgba(129,236,255,0.08)' }}
      >
        {isComplete ? (
          <div
            className="h-full w-full rounded-full"
            style={{
              background: 'linear-gradient(90deg, #81ecff 0%, #ac89ff 100%)',
            }}
          />
        ) : (
          <div
            className="h-full rounded-full"
            style={{
              width: '60%',
              background: 'linear-gradient(90deg, #f59e0b 0%, #fcd34d 100%)',
              animation: 'toast-progress 2s ease-in-out infinite alternate',
            }}
          />
        )}
      </div>

      {/* Click hint for complete */}
      {isComplete && (
        <span
          className="font-inter"
          style={{ fontSize: 10, color: 'rgba(129,236,255,0.5)', letterSpacing: '0.8px' }}
        >
          CLICK TO VIEW →
        </span>
      )}

      <style>{`
        @keyframes toast-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        @keyframes toast-spin {
          to { transform: rotate(360deg); }
        }
        @keyframes toast-progress {
          0%   { transform: translateX(-40%); }
          100% { transform: translateX(80%); }
        }
      `}</style>
    </div>
  )
}
