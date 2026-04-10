"use client";

import type { CategoryFilter } from "../knowledgeGraph.type";
import { CATEGORY_FILTERS } from "../knowledgeGraph.constant";

interface TopHeaderProps {
  activeFilter: CategoryFilter;
  onFilterChange: (filter: CategoryFilter) => void;
}

export function TopHeader({ activeFilter, onFilterChange }: TopHeaderProps) {
  return (
    <header
      className="fixed left-[81px] right-0 top-0 z-10 flex h-16 items-center px-6"
      style={{ background: "rgba(12,14,17,0.7)", backdropFilter: "blur(12px)" }}
    >
      {/* 브랜드명 */}
      <div className="mr-8">
        <span
          className="font-manrope font-bold"
          style={{
            fontSize: 20,
            letterSpacing: -0.4,
            lineHeight: "28px",
            background: "linear-gradient(90deg, #81ecff 0%, #ac89ff 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          Snapocket
        </span>
      </div>

      {/* TODO: [API] getGraphSummary() 결과(node_count, tag_count)를 헤더 우측에 표시 */}
      {/* TODO: [API] 카테고리 필터 변경 시 부모(KnowledgeGraphPage)의 getNodes(category) 재호출이 이루어지도록
            현재 onFilterChange prop이 상위에서 처리 중이므로 상위 useEffect에 activeFilter 의존성 추가 필요 */}
      {/* 카테고리 칩 */}
      <nav className="flex items-center gap-2" aria-label="Category filters">
        {CATEGORY_FILTERS.map(({ id, label }) => {
          const isActive = activeFilter === id;
          return (
            <button
              key={id}
              onClick={() => onFilterChange(id)}
              className="flex items-center px-4 h-[28px] rounded-full font-manrope transition-colors"
              style={
                isActive
                  ? {
                      background: "#81ecff",
                      color: "#003840",
                      fontSize: 12,
                      fontWeight: 500,
                      letterSpacing: -0.4,
                    }
                  : {
                      background: "#111417",
                      border: "1px solid rgba(70,72,75,0.15)",
                      color: "#aaabaf",
                      fontSize: 12,
                      fontWeight: 500,
                      letterSpacing: -0.4,
                    }
              }
            >
              {label}
            </button>
          );
        })}
      </nav>

    </header>
  );
}
