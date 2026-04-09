const NODES = [
  { id: "n1", x: 320, y: 60 },
  { id: "n2", x: 140, y: 140 },
  { id: "n3", x: 510, y: 110 },
  { id: "n4", x: 270, y: 230 },
  { id: "n5", x: 430, y: 195 },
  { id: "n6", x: 90, y: 295 },
  { id: "n7", x: 375, y: 350 },
  { id: "n8", x: 570, y: 270 },
  { id: "n9", x: 200, y: 390 },
  { id: "n10", x: 490, y: 430 },
  { id: "n11", x: 320, y: 470 },
  { id: "n12", x: 130, y: 510 },
  { id: "n13", x: 620, y: 490 },
  { id: "n14", x: 260, y: 575 },
  { id: "n15", x: 445, y: 595 },
  { id: "n16", x: 80, y: 660 },
  { id: "n17", x: 360, y: 675 },
  { id: "n18", x: 565, y: 650 },
  { id: "n19", x: 195, y: 745 },
  { id: "n20", x: 490, y: 760 },
  { id: "n21", x: 315, y: 815 },
  { id: "n22", x: 140, y: 875 },
  { id: "n23", x: 510, y: 855 },
  { id: "n24", x: 265, y: 955 },
  { id: "n25", x: 430, y: 970 },
] as const;

const EDGES: [string, string, number][] = [
  ["n1", "n2", 0.35],
  ["n1", "n3", 0.3],
  ["n1", "n4", 0.4],
  ["n1", "n5", 0.5],
  ["n2", "n4", 0.25],
  ["n2", "n6", 0.2],
  ["n2", "n9", 0.15],
  ["n3", "n5", 0.35],
  ["n3", "n8", 0.3],
  ["n4", "n7", 0.45],
  ["n4", "n9", 0.2],
  ["n5", "n7", 0.4],
  ["n5", "n10", 0.25],
  ["n6", "n9", 0.2],
  ["n6", "n12", 0.15],
  ["n7", "n11", 0.5],
  ["n7", "n10", 0.3],
  ["n8", "n10", 0.25],
  ["n8", "n13", 0.2],
  ["n9", "n12", 0.2],
  ["n9", "n14", 0.3],
  ["n10", "n15", 0.35],
  ["n10", "n13", 0.2],
  ["n11", "n14", 0.45],
  ["n11", "n15", 0.4],
  ["n12", "n16", 0.15],
  ["n12", "n14", 0.25],
  ["n13", "n18", 0.2],
  ["n13", "n15", 0.25],
  ["n14", "n17", 0.4],
  ["n14", "n19", 0.25],
  ["n15", "n17", 0.35],
  ["n15", "n20", 0.3],
  ["n16", "n19", 0.2],
  ["n17", "n21", 0.45],
  ["n17", "n20", 0.3],
  ["n18", "n20", 0.25],
  ["n18", "n23", 0.2],
  ["n19", "n22", 0.2],
  ["n19", "n21", 0.35],
  ["n20", "n23", 0.3],
  ["n20", "n21", 0.4],
  ["n21", "n24", 0.35],
  ["n21", "n25", 0.3],
  ["n22", "n24", 0.2],
  ["n23", "n25", 0.25],
];

const HIGHLIGHTED_NODES = new Set(["n1", "n5", "n7", "n11", "n17", "n21"]);
const BRIGHT_EDGES = new Set(["n1-n5", "n5-n7", "n7-n11", "n11-n17", "n17-n21"]);

const nodeMap = Object.fromEntries(NODES.map((n) => [n.id, n]));

export function NeuralNetworkBg() {
  return (
    <svg
      viewBox="0 0 704 1024"
      xmlns="http://www.w3.org/2000/svg"
      className="absolute inset-0 w-full h-full"
      aria-hidden="true"
    >
      <defs>
        <filter id="glow-node" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="glow-line" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient id="node-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#81ecff" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#81ecff" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Edges */}
      {EDGES.map(([aId, bId, opacity]) => {
        const a = nodeMap[aId];
        const b = nodeMap[bId];
        const edgeKey = `${aId}-${bId}`;
        const isBright = BRIGHT_EDGES.has(edgeKey);
        return (
          <line
            key={edgeKey}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="#81ecff"
            strokeOpacity={isBright ? opacity * 1.8 : opacity}
            strokeWidth={isBright ? 1.2 : 0.8}
            filter={isBright ? "url(#glow-line)" : undefined}
          />
        );
      })}

      {/* Nodes */}
      {NODES.map((node) => {
        const isHighlighted = HIGHLIGHTED_NODES.has(node.id);
        return (
          <g key={node.id}>
            {isHighlighted && (
              <circle
                cx={node.x}
                cy={node.y}
                r={12}
                fill="url(#node-glow)"
                opacity={0.5}
              />
            )}
            <circle
              cx={node.x}
              cy={node.y}
              r={isHighlighted ? 3.5 : 2}
              fill="#81ecff"
              fillOpacity={isHighlighted ? 0.9 : 0.35}
              filter={isHighlighted ? "url(#glow-node)" : undefined}
            />
          </g>
        );
      })}
    </svg>
  );
}
