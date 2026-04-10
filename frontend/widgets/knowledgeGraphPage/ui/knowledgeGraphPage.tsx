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

// TODO: [Mock] 백엔드 연결 후 INITIAL_TOASTS 제거. 초기값은 빈 배열([])로 변경.
//   업로드 완료 toast는 handleUpload에서 실제 API 응답 후 추가되어야 함.
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

  // TODO: [Mock] INITIAL_TOASTS 제거 시 이 useEffect도 함께 삭제
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

  // TODO: [API] 실제 업로드 흐름으로 교체:
  //   1. uploadDocument(file) 호출 → document_id 획득
  //   2. toast를 "processing" 상태로 추가 (analysisId = document_id)
  //   3. fetchAnalysisStatus(document_id) 폴링으로 "analyzed" 확인 후 status → "complete"
  //   현재는 타이머로 3.5초 후 complete 처리하는 목업 동작.
  const handleUpload = useCallback((file: File) => {
    const id = `upload-${nextIdRef.current++}`;
    const newItem: ToastItem = {
      id,
      fileName: file.name,
      status: "processing",
      analysisId: "mock-1", // TODO: [Mock] uploadDocument 반환 document_id로 교체
    };

    setToastItems((prev) => [newItem, ...prev]);

    // TODO: [Mock] 아래 타이머 제거 후 fetchAnalysisStatus 폴링으로 대체
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
