interface ToastStatusProps {
  visible: boolean;
  fileName: string;
}

export function ToastStatus({ visible, fileName }: ToastStatusProps) {
  if (!visible) return null;

  return (
    <div
      className="absolute bottom-8 left-6 z-10 w-[240px] px-4 py-3 flex flex-col gap-2"
      style={{
        background: "rgba(35,38,42,0.95)",
        border: "1px solid rgba(129,236,255,0.15)",
        borderRadius: 12,
      }}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full" style={{ background: "#81ecff" }} />
          <span className="font-inter text-snap-white" style={{ fontSize: 12, fontWeight: 500 }}>
            File Uploaded
          </span>
        </div>
        <span className="font-inter text-snap-muted" style={{ fontSize: 10 }}>✓</span>
      </div>

      <div
        className="h-1 w-full overflow-hidden rounded-full"
        style={{ background: "#171a1d" }}
      >
        <div
          className="h-full w-full rounded-full"
          style={{
            background: "linear-gradient(90deg, #81ecff 0%, #ac89ff 100%)",
          }}
        />
      </div>

      <span
        className="font-inter text-snap-muted truncate"
        style={{ fontSize: 10 }}
        title={fileName}
      >
        {fileName}
      </span>
    </div>
  );
}
