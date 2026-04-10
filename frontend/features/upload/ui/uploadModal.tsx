'use client'

import { useState, useRef, useCallback } from 'react'

interface UploadModalProps {
  open: boolean
  onClose: () => void
  onUpload: (file: File) => void
}

export function UploadModal({ open, onClose, onUpload }: UploadModalProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) setSelectedFile(file)
  }, [])

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) setSelectedFile(file)
    },
    [],
  )

  // TODO: [API] uploadDocument(file) 호출 후 반환된 document_id를 상위로 전달해야 함.
  //   현재는 File 객체만 onUpload로 넘기고 실제 업로드는 하지 않음.
  //   연결 방식: const { document_id } = await uploadDocument(file, true)
  //   → onUpload(file, document_id) 형태로 시그니처 변경 필요.
  //   업로드 중 로딩 상태 및 오류 처리도 여기서 담당.
  const handleStartAnalysis = useCallback(() => {
    const file =
      selectedFile ??
      new File([], 'sample_document.pdf', { type: 'application/pdf' })
    onUpload(file)
    setSelectedFile(null)
    onClose()
  }, [selectedFile, onUpload, onClose])

  const handleClose = useCallback(() => {
    setSelectedFile(null)
    onClose()
  }, [onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(12,14,17,0.75)' }}
      onClick={handleClose}
    >
      <div
        className="relative flex flex-col rounded-xl overflow-hidden"
        style={{
          width: 672,
          background: 'rgba(23,26,29,0.95)',
          border: '1px solid rgba(70,72,75,0.1)',
          backdropFilter: 'blur(16px)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-8 pt-8 pb-6">
          <div>
            <h2
              className="font-manrope font-extrabold text-2xl"
              style={{ color: '#f9f9fd', letterSpacing: '-0.6px' }}
            >
              Upload Sources
            </h2>
            <p className="font-inter text-sm mt-1" style={{ color: '#aaabaf' }}>
              Feed your knowledge vault with new data assets.
            </p>
          </div>
          <button
            onClick={handleClose}
            className="mt-1 flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
            aria-label="Close modal"
          >
            <img src="/close.svg" alt="Close 아이콘" />
          </button>
        </div>

        {/* Content */}
        <div className="px-8 flex flex-col gap-4">
          {/* Drag & Drop Zone */}
          <div
            className="relative flex flex-col items-center justify-center rounded-xl gap-5 cursor-pointer transition-colors"
            style={{
              minHeight: 330,
              background: isDragging
                ? 'rgba(129,236,255,0.07)'
                : 'rgba(17,20,23,0.3)',
              border: `1px solid ${isDragging ? 'rgba(129,236,255,0.35)' : 'rgba(70,72,75,0.3)'}`,
            }}
            onDragOver={(e) => {
              e.preventDefault()
              setIsDragging(true)
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileChange}
              accept=".pdf,.jpg,.jpeg,.png,.mp4"
            />

            {/* Upload icon circle */}
            <div
              className="flex h-20 w-20 items-center justify-center rounded-full"
              style={{ background: 'rgba(129,236,255,0.1)' }}
            >
              <img src="/upload.svg" alt="Upload 아이콘" />
            </div>

            <div className="flex flex-col items-center gap-1 text-center">
              <p
                className="font-manrope font-semibold text-lg"
                style={{ color: '#f9f9fd' }}
              >
                {selectedFile
                  ? selectedFile.name
                  : 'Drop files here or click to browse'}
              </p>
              <p
                className="font-inter text-xs tracking-widest"
                style={{ color: '#aaabaf' }}
              >
                Support for PDF, JPG, PNG, or MP4
              </p>
            </div>

            <button
              className="rounded-full px-8 py-3 font-inter font-bold text-base transition-colors"
              style={{
                background: '#23262a',
                border: '1px solid rgba(129,236,255,0.2)',
                color: '#81ecff',
              }}
              onClick={(e) => {
                e.stopPropagation()
                fileInputRef.current?.click()
              }}
            >
              Select Files
            </button>
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-end gap-2 px-8 py-6 mt-4"
          style={{ background: 'rgba(35,38,42,0.3)' }}
        >
          <button
            onClick={handleClose}
            className="font-inter font-semibold text-base px-6 py-2.5 rounded-full transition-colors cursor-pointer"
            style={{ color: '#aaabaf' }}
          >
            Cancel
          </button>
          <button
            onClick={handleStartAnalysis}
            className="font-inter font-bold text-base rounded-full px-8 py-3 transition-opacity hover:opacity-90 cursor-pointer"
            style={{
              background: 'linear-gradient(90deg, #81ecff 0%, #00d4ec 100%)',
              color: '#003840',
            }}
          >
            Start Analysis
          </button>
        </div>
      </div>
    </div>
  )
}
