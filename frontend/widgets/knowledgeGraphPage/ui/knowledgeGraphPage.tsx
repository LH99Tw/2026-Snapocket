"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type { CategoryFilter, GraphNode, GraphEdge } from "../knowledgeGraph.type";
import { GRAPH_NODES, GRAPH_EDGES } from "../knowledgeGraph.constant";
import { getNodes } from "@/features/graph";
import { computeNodePositions } from "../knowledgeGraph.utils";
import { SidebarNav } from "./sidebarNav";
import { TopHeader } from "./topHeader";
import { KnowledgeGraphCanvas } from "./knowledgeGraphCanvas";
import { GraphControls } from "./graphControls";
import { AiInputBar } from "./aiInputBar";
import { ToastStatus } from "./toastStatus";

export function KnowledgeGraphPage() {
  const [activeFilter, setActiveFilter] = useState<CategoryFilter>("all");
  const [nodes, setNodes] = useState<GraphNode[]>(GRAPH_NODES);
  const [edges] = useState<GraphEdge[]>(GRAPH_EDGES);
  const [uploadToast, setUploadToast] = useState<{ visible: boolean; fileName: string }>({
    visible: false,
    fileName: "",
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const handleAddNew = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setUploadToast({ visible: true, fileName: file.name });
    toastTimerRef.current = setTimeout(() => {
      setUploadToast({ visible: false, fileName: "" });
    }, 3500);

    e.target.value = "";
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-snap-bg">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFileChange}
        aria-hidden="true"
      />

      <SidebarNav onAddNew={handleAddNew} />

      <main className="relative flex-1" style={{ marginLeft: 81 }}>
        <TopHeader activeFilter={activeFilter} onFilterChange={setActiveFilter} />

        <div className="absolute inset-0">
          <KnowledgeGraphCanvas activeFilter={activeFilter} nodes={nodes} edges={edges} />
        </div>

        <GraphControls />
        <AiInputBar />
        <ToastStatus visible={uploadToast.visible} fileName={uploadToast.fileName} />
      </main>
    </div>
  );
}
