export type ApiNodeCategory =
  | "assignments"
  | "exams"
  | "class_materials"
  | "summaries"
  | "receipts"
  | "notices";

export interface ApiNode {
  id: string;
  title: string;
  category: ApiNodeCategory;
  tags: string[];
  created_at: string;
  connection_count: number;
}

export interface ApiEdge {
  source: string;
  target: string;
  weight: number;
}

export interface GraphSummaryData {
  node_count: number;
  document_count: number;
  tag_count: number;
  edge_count: number;
}

export interface SearchNodeResult {
  id: string;
  title: string;
  category: string;
  highlight: string;
}
