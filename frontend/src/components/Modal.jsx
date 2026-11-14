import { useEffect, useRef } from 'react'

export default function Modal({ onClose, title, maxWidth = 'max-w-md', children, footer }) {
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onCloseRef.current() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div
        className={`bg-white rounded-lg shadow-xl w-full ${maxWidth} max-h-[90vh] flex flex-col`}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b shrink-0">
          <h3 className="font-semibold">{title}</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>
        <div className="p-5 space-y-3 overflow-y-auto">
          {children}
        </div>
        {footer && (
          <div className="px-5 py-4 border-t shrink-0 space-y-2">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
