interface SidebarNavProps {
  onAddNew?: () => void;
}

export function SidebarNav({ onAddNew }: SidebarNavProps) {
  return (
    <aside
      className="fixed left-0 top-0 z-20 flex h-full w-[81px] flex-col items-center justify-between py-6"
      style={{
        background: '#0c0e11',
        borderRight: '1px solid rgba(255,255,255,0.05)',
      }}
    >
      {/* 상단: 로고 + 네비게이션 */}
      <div className="flex flex-col items-center gap-6">
        {/* 브랜드 로고 */}
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg"
          style={{
            background: 'linear-gradient(135deg, #81ecff 0%, #00e3fd 100%)',
          }}
        ></div>

        {/* 네비게이션 링크들 */}
        <nav
          className="flex flex-col items-center gap-2"
          aria-label="Main navigation"
        >
          {/* Graph View — 활성 */}
          <button
            className="flex h-12 w-[63px] items-center justify-center rounded-lg"
            style={{
              background: 'rgba(129,236,255,0.1)',
              borderLeft: '2px solid #81ecff',
            }}
            aria-current="page"
            aria-label="Graph View"
          >
            <img src="/graph.svg" alt="그래프 로고" />
          </button>

          {/* Calendar — 비활성 */}
          <button
            className="flex h-12 w-[63px] items-center justify-center rounded-lg"
            aria-label="Calendar"
          >
            <img src="/calendar.svg" alt="캘린더 로고" />
          </button>

          {/* Add New — CTA */}
          <button
            className="flex h-[50px] w-[63px] items-center justify-center rounded-lg"
            style={{ background: '#81ecff' }}
            aria-label="Add New"
            onClick={onAddNew}
          >
            <img src="/add.svg" alt="추가 로고" />
          </button>
        </nav>
      </div>

      {/* 하단: 설정, 도움말, 프로필 */}
      <div className="flex flex-col items-center gap-4">
        <button
          className="flex h-12 w-[63px] items-center justify-center rounded-lg"
          aria-label="Settings"
        >
          <img src="/setting.svg" alt="설정 로고" />
        </button>

        <button
          className="flex h-12 w-[63px] items-center justify-center rounded-lg"
          aria-label="Help"
        >
          <img src="/help.svg" alt="도움말 로고" />
        </button>

        {/* 사용자 아바타 */}
        <button
          className="flex h-[35px] w-[35px] items-center justify-center rounded-full overflow-hidden"
          style={{
            border: '1px solid rgba(129,236,255,0.2)',
            background: '#1a2a2a',
          }}
          aria-label="User profile"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle
              cx="10"
              cy="7"
              r="4"
              stroke="#81ecff"
              strokeWidth="1.5"
              opacity="0.5"
            />
            <path
              d="M2 18C2 14.7 5.6 12 10 12C14.4 12 18 14.7 18 18"
              stroke="#81ecff"
              strokeWidth="1.5"
              strokeLinecap="round"
              opacity="0.5"
            />
          </svg>
        </button>
      </div>
    </aside>
  )
}
