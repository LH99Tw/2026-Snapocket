export type NodeCategory = "assignment" | "exam" | "class" | "summary" | "misc" | "root";

export type NodeSize = "root" | "primary" | "secondary";

export interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
  category: NodeCategory;
  size: NodeSize;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export type CategoryFilter = "all" | "assignments" | "exams" | "class-materials" | "summaries";
