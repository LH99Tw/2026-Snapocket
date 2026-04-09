import type { CategoryFilter, GraphNode, GraphEdge } from "../knowledgeGraph.type";
import {
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  NODE_COLOR,
  NODE_DOT_SIZE,
  NODE_DOT_OPACITY,
} from "../knowledgeGraph.constant";

const PRIMARY_LABEL_STYLE = { color: "#f9f9fd", fontSize: 12, fontWeight: 400 } as const;
const SECONDARY_LABEL_STYLE = { color: "#aaabaf", fontSize: 10, fontWeight: 400 } as const;

function isNodeVisible(node: GraphNode, filter: CategoryFilter): boolean {
  if (filter === "all") return true;
  if (filter === "assignments") return node.category === "assignment";
  if (filter === "exams") return node.category === "exam";
  if (filter === "class-materials") return node.category === "class";
  if (filter === "summaries") return node.category === "summary";
  return true;
}

interface KnowledgeGraphCanvasProps {
  activeFilter: CategoryFilter;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function KnowledgeGraphCanvas({ activeFilter, nodes, edges }: KnowledgeGraphCanvasProps) {
  const visibleNodes = nodes.filter((n) => isNodeVisible(n, activeFilter));
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  return (
    <div
      className="relative h-full w-full overflow-hidden"
      style={{ background: "#0c0e11" }}
    >
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 60% at 50% 50%, rgba(23,26,29,0.8) 0%, transparent 100%)",
        }}
      />

      <svg
        viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 h-full w-full"
        aria-hidden="true"
      >
        {edges.map((edge) => {
          if (!visibleIds.has(edge.from) || !visibleIds.has(edge.to)) return null;
          const from = nodeMap.get(edge.from);
          const to = nodeMap.get(edge.to);
          if (!from || !to) return null;
          return (
            <line
              key={`${edge.from}-${edge.to}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="rgba(129,236,255,0.12)"
              strokeWidth="1"
            />
          );
        })}

        {visibleNodes.map((node) => {
          const color = NODE_COLOR[node.category] ?? "#aaabaf";
          const dotSize = NODE_DOT_SIZE[node.size] ?? 8;
          const opacity = NODE_DOT_OPACITY[node.size] ?? 0.6;

          return (
            <circle
              key={node.id}
              cx={node.x}
              cy={node.y}
              r={dotSize / 2}
              fill={color}
              opacity={opacity}
            />
          );
        })}
      </svg>

      <div className="absolute inset-0" aria-label="Knowledge graph nodes">
        {visibleNodes.map((node) => {
          const xPct = (node.x / CANVAS_WIDTH) * 100;
          const yPct = (node.y / CANVAS_HEIGHT) * 100;
          const dotSize = NODE_DOT_SIZE[node.size] ?? 8;

          return (
            <div
              key={node.id}
              className="absolute flex items-center gap-2"
              style={{
                left: `${xPct}%`,
                top: `${yPct}%`,
                transform: "translate(0, -50%)",
              }}
            >
              <div style={{ width: dotSize, height: dotSize, flexShrink: 0 }} />
              <span
                className="whitespace-nowrap font-inter leading-none"
                style={node.size === "primary" ? PRIMARY_LABEL_STYLE : SECONDARY_LABEL_STYLE}
              >
                {node.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
