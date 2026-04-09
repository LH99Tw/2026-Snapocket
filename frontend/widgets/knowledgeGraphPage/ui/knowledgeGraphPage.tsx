"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { CategoryFilter, GraphNode, GraphEdge } from "../knowledgeGraph.type";
import { GRAPH_NODES, GRAPH_EDGES } from "../knowledgeGraph.constant";
import { getNodes } from "@/entities/graph";
import { computeNodePositions } from "../knowledgeGraph.utils";
import { SidebarNav, ToastStatus, type ToastItem } from "@/shared/ui";
import { UploadModal } from "@/features/upload";
import { TopHeader } from "./topHeader";
import { KnowledgeGraphCanvas } from "./knowledgeGraphCanvas";
import { GraphControls } from "./graphControls";
import { AiInputBar } from "./aiInputBar";

// 화면에서 두 프로토타입을 바로 확인할 수 있도록 목 토스트 초기값 설정
const INITIAL_TOASTS: ToastItem[] = [
  {
    id: "mock-1",
    fileName: "CS204_Lecture_Notes.pdf",
    status: "complete",
    analysisId: "mock-1",
  },
  {
    id: "mock-2",
    fileName: "Algorithm_Assignment3.pdf",
    status: "processing",
    analysisId: "mock-2",
  },
];

export function KnowledgeGraphPage() {
  const router = useRouter();
  const [activeFilter, setActiveFilter] = useState<CategoryFilter>("all");
  const [nodes, setNodes] = useState<GraphNode[]>(GRAPH_NODES);
  const [edges] = useState<GraphEdge[]>(GRAPH_EDGES);
  const [modalOpen, setModalOpen] = useState(false);
  const [toastItems, setToastItems] = useState<ToastItem[]>(INITIAL_TOASTS);
  const nextIdRef = useRef(100);
  const processingTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const controller = new AbortController();

    getNodes()
      .then((apiNodes) => {
        if (!controller.signal.aborted) {
          setNodes(computeNodePositions(apiNodes));
        }
      })
      .catch(() => {
        // no-op: keep constant graph on failure
      });

    return () => controller.abort();
  }, []);

  // mock-2 초기 processing → complete 자동 전환 (3.5초)
  useEffect(() => {
    const timer = setTimeout(() => {
      setToastItems((prev) =>
        prev.map((item) =>
          item.id === "mock-2" ? { ...item, status: "complete" } : item
        )
      );
    }, 3500);
    return () => clearTimeout(timer);
  }, []);

  const handleUpload = useCallback((file: File) => {
    const id = `upload-${nextIdRef.current++}`;
    const newItem: ToastItem = {
      id,
      fileName: file.name,
      status: "processing",
      analysisId: "mock-1", // 업로드된 파일은 mock-1 결과로 연결 (프로토타입)
    };

    setToastItems((prev) => [newItem, ...prev]);

    // 3.5초 뒤 complete로 전환
    const timer = setTimeout(() => {
      setToastItems((prev) =>
        prev.map((item) => (item.id === id ? { ...item, status: "complete" } : item))
      );
      processingTimersRef.current.delete(id);
    }, 3500);

    processingTimersRef.current.set(id, timer);
  }, []);

  const handleToastClick = useCallback(
    (item: ToastItem) => {
      if (item.status === "complete") {
        router.push(`/analysis/${item.analysisId}`);
      }
    },
    [router]
  );

  useEffect(() => {
    const timers = processingTimersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-snap-bg">
      <SidebarNav onUpload={() => setModalOpen(true)} />

      <main className="relative flex-1" style={{ marginLeft: 81 }}>
        <TopHeader activeFilter={activeFilter} onFilterChange={setActiveFilter} />

        <div className="absolute inset-0">
          <KnowledgeGraphCanvas activeFilter={activeFilter} nodes={nodes} edges={edges} />
        </div>

        <GraphControls />
        <AiInputBar />
        <ToastStatus items={toastItems} onItemClick={handleToastClick} />
      </main>

      <UploadModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onUpload={handleUpload}
      />
    </div>
  );
}
