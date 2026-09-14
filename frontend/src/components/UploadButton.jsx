import { useRef, useState } from 'react'
import { Icon } from './ui/Icon'
import { uploadDocument } from '../services/api'

// File upload button — POST /api/v1/documents (multipart).
// Returns document_id to parent; no client-side file processing.
export function UploadButton({ onDocumentUploaded, disabled = false }) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  // Was `useState(null)` — an array, not a ref object. React still set
  // `.current` on it (arrays are objects), so fileInputRef.current.click()
  // happened to work, but it fired "Unexpected ref object provided" console
  // errors on every render (visible on every page that mounts ChatPanel).
  const fileInputRef = useRef(null)

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    setError(null)
    try {
      const result = await uploadDocument(file)
      onDocumentUploaded?.(result)
    } catch (err) {
      setError(err?.message ?? 'Upload failed')
    } finally {
      setUploading(false)
      // Reset input so same file can be re-selected
      e.target.value = ''
    }
  }

  return (
    <div className="relative">
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={handleFileSelect}
        disabled={disabled || uploading}
        aria-label="Upload document"
      />
      <button
        type="button"
        className="btn-quiet btn text-txt-mid disabled:opacity-50"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled || uploading}
      >
        <Icon name="paperclip" size={15} />
        {uploading ? 'Uploading…' : 'Attach file'}
      </button>
      {error && (
        <div className="absolute bottom-full left-0 mb-2 px-2 py-1 text-xs bg-danger-soft text-danger rounded whitespace-nowrap">
          {error}
        </div>
      )}
    </div>
  )
}