import { LoginForm } from "@/features/auth";
import { NeuralNetworkBg } from "./neuralNetworkBg";

export function LoginPage() {
  return (
    <div className="flex min-h-screen w-full bg-snap-bg font-inter">
      {/* 왼쪽 시각적 패널 */}
      <section className="relative hidden lg:flex flex-col w-1/2 bg-snap-panel overflow-hidden">
        {/* 뉴럴 네트워크 SVG 배경 */}
        <NeuralNetworkBg />

        {/* 블러 오버레이 — 분위기 연출 */}
        <div
          className="absolute rounded-full pointer-events-none"
          style={{
            width: 384,
            height: 614,
            top: "20%",
            left: "28%",
            background: "rgba(129,236,255,0.05)",
            filter: "blur(80px)",
          }}
        />
        <div
          className="absolute rounded-full pointer-events-none"
          style={{
            width: 256,
            height: 410,
            bottom: "15%",
            left: "5%",
            background: "rgba(172,137,255,0.05)",
            filter: "blur(60px)",
          }}
        />

        {/* 브랜드 콘텐츠 오버레이 */}
        <div className="relative z-10 flex flex-col justify-end h-full px-16 pb-20">
          {/* 로고 + 슬로건 */}
          <div className="flex flex-col gap-2 mb-10">
            <h1
              className="font-manrope font-extrabold text-snap-white leading-none"
              style={{ fontSize: 60, letterSpacing: -3 }}
            >
              Snapocket
            </h1>
            <p
              className="font-manrope text-snap-cyan-2"
              style={{ fontSize: 20, letterSpacing: -0.5, lineHeight: "32.5px" }}
            >
              The intelligence behind every lens.
            </p>
          </div>

          {/* 통계 */}
          <div
            className="flex gap-10 pt-6"
            style={{ borderTop: "1px solid rgba(129,236,255,0.20)" }}
          >
            <div className="flex flex-col gap-0.5">
              <span
                className="font-manrope font-bold text-snap-white"
                style={{ fontSize: 30, letterSpacing: -0.75, lineHeight: "36px" }}
              >
                10M+
              </span>
              <span
                className="font-inter text-snap-muted/60 uppercase"
                style={{ fontSize: 10, letterSpacing: 2, lineHeight: "15px" }}
              >
                Assets Analyzed
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span
                className="font-manrope font-bold text-snap-white"
                style={{ fontSize: 30, letterSpacing: -0.75, lineHeight: "36px" }}
              >
                99.9%
              </span>
              <span
                className="font-inter text-snap-muted/60 uppercase"
                style={{ fontSize: 10, letterSpacing: 2, lineHeight: "15px" }}
              >
                Recognition Accuracy
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 오른쪽 로그인 폼 패널 */}
      <section className="flex flex-col w-full lg:w-1/2 bg-snap-bg">
        <div className="flex flex-1 flex-col justify-center px-8 sm:px-16 lg:px-[100px]">
          <div className="w-full max-w-[448px] mx-auto flex flex-col gap-8">
            {/* 헤더 */}
            <div className="flex flex-col gap-2">
              <h2
                className="font-manrope font-bold text-snap-white"
                style={{ fontSize: 30, letterSpacing: -0.75, lineHeight: "36px" }}
              >
                Welcome back
              </h2>
              <p className="font-inter text-snap-muted" style={{ fontSize: 16, lineHeight: "24px" }}>
                Access your curated digital gallery.
              </p>
            </div>

            {/* 폼 */}
            <LoginForm />

            {/* 회원가입 링크 */}
            <p className="text-center font-inter text-snap-muted" style={{ fontSize: 14, lineHeight: "20px" }}>
              New to Snapocket?{" "}
              <a
                href="/signup"
                className="text-snap-cyan font-semibold hover:text-snap-cyan/80 transition-colors"
              >
                Create an Account
              </a>
            </p>
          </div>
        </div>

        {/* 하단 푸터 */}
        <footer className="flex items-center justify-between px-8 sm:px-12 py-5">
          <span
            className="font-inter text-snap-muted/30"
            style={{ fontSize: 10, letterSpacing: 1, lineHeight: "15px" }}
          >
            © 2024 Snapocket AI. The Digital Curator.
          </span>
          <nav className="flex gap-6" aria-label="Footer links">
            {(["Privacy", "Terms", "Security"] as const).map((label) => (
              <a
                key={label}
                href={`/${label.toLowerCase()}`}
                className="font-inter text-snap-muted/40 hover:text-snap-muted/60 transition-colors"
                style={{ fontSize: 10, letterSpacing: 1, lineHeight: "15px" }}
              >
                {label}
              </a>
            ))}
          </nav>
        </footer>
      </section>
    </div>
  );
}
