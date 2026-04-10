'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import GraphIcon from '@/public/graph.svg'
import CalendarIcon from '@/public/calendar.svg'

interface SidebarNavProps {
  onUpload?: () => void
}

export function SidebarNav({ onUpload }: SidebarNavProps) {
  const [isOpen, setIsOpen] = useState(false)
  const pathname = usePathname()

  const isGraph = pathname === '/'
  const isCalendar = pathname === '/calendar'

  return (
    <aside
      className="fixed left-0 top-0 z-30 flex h-full flex-col justify-between overflow-hidden py-6 transition-[width] duration-300 ease-in-out"
      style={{
        width: isOpen ? 256 : 81,
        background: '#171a1d',
        borderRight: '1px solid rgba(70,72,75,0.2)',
      }}
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      {/* 상단: 브랜드 + 네비게이션 + CTA */}
      <div className="flex flex-col gap-6">
        {/* 브랜드 헤더 */}
        <div className="flex items-center gap-3 px-[19px]">
          <div
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
            style={{ background: '#00e3fd' }}
          />

          <div
            className="flex flex-col overflow-hidden transition-all duration-300"
            style={{
              opacity: isOpen ? 1 : 0,
              width: isOpen ? 'auto' : 0,
              whiteSpace: 'nowrap',
            }}
          >
            <span
              className="font-manrope font-bold text-xl leading-7"
              style={{
                background: 'linear-gradient(90deg, #81ecff 0%, #ac89ff 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                letterSpacing: '-0.4px',
              }}
            >
              Snapocket
            </span>
            <span
              className="font-inter font-bold text-[10px] tracking-[2px]"
              style={{ color: '#aaabaf' }}
            >
              Intelligent Graph
            </span>
          </div>
        </div>

        {/* 네비게이션 탭 */}
        <nav className="flex flex-col">
          {/* Graph View */}
          <Link
            href="/"
            className="relative flex items-center py-3 pl-[19px] transition-colors"
            style={{
              background: isGraph ? 'rgba(129,236,255,0.05)' : 'transparent',
              borderLeft: isGraph
                ? '2px solid #81ecff'
                : '2px solid transparent',
            }}
          >
            <div className="flex h-6 w-[43px] shrink-0 items-center justify-center">
              <GraphIcon fill={isGraph ? "#00E3Fd" : "#FFFFFF"} />
            </div>
            <span
              className="font-inter text-sm transition-all duration-300 overflow-hidden"
              style={{
                fontWeight: isGraph ? 700 : 400,
                color: isGraph ? '#81ecff' : '#aaabaf',
                letterSpacing: '-0.4px',
                opacity: isOpen ? 1 : 0,
                maxWidth: isOpen ? 120 : 0,
                whiteSpace: 'nowrap',
              }}
            >
              Graph View
            </span>
          </Link>

          {/* Calendar */}
          <Link
            href="/calendar"
            className="flex items-center py-3 pl-[21px] transition-colors"
            style={{
              background: isCalendar ? 'rgba(129,236,255,0.05)' : 'transparent',
              borderLeft: isCalendar
                ? '2px solid #81ecff'
                : '2px solid transparent',
            }}
          >
            <div className="flex h-5 w-[41px] shrink-0 items-center justify-center">
              <CalendarIcon fill={isCalendar ? "#00E3Fd" : "#FFFFFF"} />
            </div>
            <span
              className="font-inter text-sm transition-all duration-300 overflow-hidden"
              style={{
                fontWeight: isCalendar ? 700 : 400,
                color: isCalendar ? '#81ecff' : '#aaabaf',
                letterSpacing: '-0.4px',
                opacity: isOpen ? 1 : 0,
                maxWidth: isOpen ? 120 : 0,
                whiteSpace: 'nowrap',
              }}
            >
              Calendar
            </span>
          </Link>
        </nav>

        {/* CTA 버튼 */}
        <div className="px-[19px]">
          <button
            className="flex items-center justify-center rounded-xl transition-all duration-300 cursor-pointer"
            style={{
              background: 'linear-gradient(135deg, #81ecff 0%, #00e3fd 100%)',
              height: 52,
              width: isOpen ? 208 : 50,
            }}
            onClick={onUpload}
            aria-label="Upload new file"
          >
            <div className="flex h-[14px] w-[14px] shrink-0 items-center justify-center">
              <img src="/add.svg" alt="" />
            </div>
            <span
              className="font-inter font-bold text-sm tracking-[1.4px] transition-all duration-300 overflow-hidden"
              style={{
                color: '#003840',
                opacity: isOpen ? 1 : 0,
                maxWidth: isOpen ? 120 : 0,
                whiteSpace: 'nowrap',
                marginLeft: isOpen ? 8 : 0,
              }}
            >
              New Node
            </span>
          </button>
        </div>
      </div>

      {/* 하단: 설정, 지원, 프로필 */}
      <div className="flex flex-col">
        {/* Settings */}
        <div className="flex items-center py-3 pl-[21px]">
          <div className="flex h-5 w-[41px] shrink-0 items-center justify-center">
            <img src="/setting.svg" alt="" />
          </div>
          <span
            className="font-inter text-sm transition-all duration-300 overflow-hidden"
            style={{
              color: '#aaabaf',
              letterSpacing: '-0.4px',
              opacity: isOpen ? 1 : 0,
              maxWidth: isOpen ? 120 : 0,
              whiteSpace: 'nowrap',
            }}
          >
            Settings
          </span>
        </div>

        {/* Support */}
        <div className="flex items-center py-3 pl-[21px]">
          <div className="flex h-5 w-[41px] shrink-0 items-center justify-center">
            <img src="/help.svg" alt="" />
          </div>
          <span
            className="font-inter text-sm transition-all duration-300 overflow-hidden"
            style={{
              color: '#aaabaf',
              letterSpacing: '-0.4px',
              opacity: isOpen ? 1 : 0,
              maxWidth: isOpen ? 120 : 0,
              whiteSpace: 'nowrap',
            }}
          >
            Support
          </span>
        </div>

        {/* 사용자 프로필 */}
        <div
          className="flex items-center py-4 pl-[19px]"
          style={{ borderTop: '1px solid rgba(70,72,75,0.1)' }}
        >
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full"
            style={{
              border: '1px solid rgba(70,72,75,0.3)',
              background: '#1a2a2a',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
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
          </div>

          {/* TODO: [API] getMe() 호출 후 name, email(또는 role) 표시. 현재는 하드코딩 값 사용 */}
          <div
            className="ml-3 flex flex-col transition-all duration-300 overflow-hidden"
            style={{
              opacity: isOpen ? 1 : 0,
              maxWidth: isOpen ? 140 : 0,
              whiteSpace: 'nowrap',
            }}
          >
            <span
              className="font-inter font-bold text-xs"
              style={{ color: '#f9f9fd', letterSpacing: '-0.4px' }}
            >
              Alex Rivera
            </span>
            <span
              className="font-inter text-[10px]"
              style={{ color: '#aaabaf', letterSpacing: '-0.4px' }}
            >
              Premium Curator
            </span>
          </div>
        </div>
      </div>
    </aside>
  )
}
