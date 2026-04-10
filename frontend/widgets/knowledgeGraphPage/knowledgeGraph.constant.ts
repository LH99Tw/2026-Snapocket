import type { CategoryFilter, GraphEdge, GraphNode } from "./knowledgeGraph.type";

export const CANVAS_WIDTH = 1200;
export const CANVAS_HEIGHT = 1024;

export const GRAPH_NODES: GraphNode[] = [
  { id: "root", label: "All Resources", x: 540, y: 502, category: "root", size: "root" },
  { id: "assign1", label: "Physics Problem Set #4", x: 420, y: 307, category: "assignment", size: "primary" },
  { id: "assign2", label: "Lab Report Draft", x: 540, y: 204, category: "assignment", size: "secondary" },
  { id: "exam1", label: "Midterm Prep - Calculus", x: 780, y: 358, category: "exam", size: "primary" },
  { id: "exam2", label: "2023 Final Archive", x: 900, y: 256, category: "exam", size: "secondary" },
  { id: "class1", label: "Lecture: Quantum Intro", x: 660, y: 716, category: "class", size: "primary" },
  { id: "class2", label: "Schrödinger Slide Deck", x: 540, y: 870, category: "class", size: "secondary" },
  { id: "class3", label: "Reference Textbook", x: 780, y: 819, category: "class", size: "secondary" },
  { id: "summary1", label: "Week 1-4 Summary", x: 360, y: 614, category: "summary", size: "primary" },
  { id: "summary2", label: "Quick Review: Formulas", x: 240, y: 768, category: "summary", size: "secondary" },
  { id: "misc1", label: "Research Notes", x: 900, y: 563, category: "misc", size: "primary" },
  { id: "misc2", label: "Reading List", x: 1020, y: 665, category: "misc", size: "secondary" },
  { id: "misc3", label: "Old Assignments", x: 300, y: 204, category: "misc", size: "secondary" },
];

export const GRAPH_EDGES: GraphEdge[] = [
  { from: "root", to: "assign1" },
  { from: "root", to: "exam1" },
  { from: "root", to: "class1" },
  { from: "root", to: "summary1" },
  { from: "root", to: "misc1" },
  { from: "assign1", to: "assign2" },
  { from: "exam1", to: "exam2" },
  { from: "class1", to: "class2" },
  { from: "class1", to: "class3" },
  { from: "summary1", to: "summary2" },
  { from: "misc1", to: "misc2" },
  { from: "misc1", to: "misc3" },
];

export const CATEGORY_FILTERS: { id: CategoryFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "assignments", label: "Assignments" },
  { id: "exams", label: "Exams" },
  { id: "class-materials", label: "Class Materials" },
  { id: "summaries", label: "Summaries" },
];

export const NODE_DOT_SIZE: Record<string, number> = {
  root: 16,
  primary: 10,
  secondary: 8,
};

export const NODE_COLOR: Record<string, string> = {
  root: "#81ecff",
  assignment: "#81ecff",
  exam: "#ac89ff",
  class: "#81ecff",
  summary: "#fab0ff",
  misc: "#f8f1ff",
};

export const NODE_DOT_OPACITY: Record<string, number> = {
  root: 1,
  primary: 0.8,
  secondary: 0.6,
};
