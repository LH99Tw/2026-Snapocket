const BUTTON_STYLE = {
  background: "rgba(23,26,29,0.6)",
  border: "1px solid rgba(70,72,75,0.1)",
  borderRadius: 8,
} as const;

export function GraphControls() {
  return (
    <div className="absolute right-6 top-20 z-10 flex flex-col gap-2">
      {/* 줌 인 */}
      <button
        className="flex h-10 w-10 items-center justify-center"
        style={BUTTON_STYLE}
        aria-label="Zoom in"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="8" cy="8" r="5.5" stroke="#aaabaf" strokeWidth="1.5" />
          <path d="M6 8H10M8 6V10" stroke="#aaabaf" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M12.5 12.5L16 16" stroke="#aaabaf" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {/* 줌 아웃 */}
      <button
        className="flex h-10 w-10 items-center justify-center"
        style={BUTTON_STYLE}
        aria-label="Zoom out"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="8" cy="8" r="5.5" stroke="#aaabaf" strokeWidth="1.5" />
          <path d="M6 8H10" stroke="#aaabaf" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M12.5 12.5L16 16" stroke="#aaabaf" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {/* 전체 화면 맞춤 */}
      <button
        className="flex h-10 w-10 items-center justify-center"
        style={BUTTON_STYLE}
        aria-label="Fit to screen"
      >
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <path d="M3 8V3H8M14 3H19V8M19 14V19H14M8 19H3V14" stroke="#aaabaf" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M8 11H14M11 8V14" stroke="#aaabaf" strokeWidth="1" strokeLinecap="round" opacity="0.5" />
        </svg>
      </button>
    </div>
  );
}
