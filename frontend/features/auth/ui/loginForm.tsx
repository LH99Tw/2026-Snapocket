'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import type { LoginFormState } from '@/features/auth/loginForm.type'
import { login } from '@/features/auth/api'
import { ApiError } from '@/shared/api'

export function LoginForm() {
  const router = useRouter()
  const [form, setForm] = useState<LoginFormState>({ email: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  function handleChange(field: keyof LoginFormState) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setErrorMessage(null)
      setForm((prev) => ({ ...prev, [field]: e.target.value }))
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setIsLoading(true)
    setErrorMessage(null)

    try {
      await login({ email: form.email, password: form.password })
      router.push('/')
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message)
      } else {
        setErrorMessage('로그인에 실패했습니다. 다시 시도해주세요.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <button
        type="button"
        className="flex items-center justify-center gap-3 w-full h-[54px] rounded-lg bg-snap-social border border-snap-border/20 text-snap-white font-inter text-base font-medium transition-colors hover:bg-[#2a2e33] cursor-pointer"
      >
        <img width="20px" height="20px" src="/google.png" alt="Google 로고" />
        <span>Continue with Google</span>
      </button>

      <div className="flex items-center gap-3">
        <div className="flex-1 h-px bg-snap-border/20" />
        <span className="text-snap-muted/60 font-inter text-[10px] tracking-[1px] whitespace-nowrap">
          or sign in with email
        </span>
        <div className="flex-1 h-px bg-snap-border/20" />
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        <div className="flex flex-col gap-2">
          <label
            htmlFor="email"
            className="font-inter text-[10px] text-snap-muted tracking-[1.5px] uppercase"
          >
            Email Address
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="name@company.com"
            value={form.email}
            onChange={handleChange('email')}
            required
            className="w-full h-[51px] rounded-lg bg-snap-input px-4 font-inter text-base text-snap-white placeholder:text-snap-muted/30 outline-none focus:ring-1 focus:ring-snap-cyan/40 transition"
          />
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <label
              htmlFor="password"
              className="font-inter text-[10px] text-snap-muted tracking-[1.5px] uppercase"
            >
              Password
            </label>
            <button
              type="button"
              className="font-inter text-[10px] text-snap-cyan tracking-[0.5px] font-semibold hover:text-snap-cyan/80 transition-colors"
            >
              Forgot?
            </button>
          </div>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              placeholder="••••••••"
              value={form.password}
              onChange={handleChange('password')}
              required
              className="w-full h-[51px] rounded-lg bg-snap-input px-4 pr-12 font-inter text-base text-snap-white placeholder:text-snap-muted/30 outline-none focus:ring-1 focus:ring-snap-cyan/40 transition"
            />
            <button
              type="button"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-snap-muted/50 hover:text-snap-muted transition-colors"
            >
              {showPassword ? (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {errorMessage !== null && (
          <p role="alert" className="font-inter text-[13px] text-red-400">
            {errorMessage}
          </p>
        )}

        {/* 로그인 버튼 */}
        <button
          type="submit"
          disabled={isLoading}
          className="relative w-full h-14 rounded-lg font-manrope font-bold text-base text-snap-btn-text overflow-hidden transition-opacity hover:opacity-90 mt-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
          style={{
            background: 'linear-gradient(135deg, #81ecff 0%, #00e3fd 100%)',
          }}
        >
          {isLoading ? 'Signing in…' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}
