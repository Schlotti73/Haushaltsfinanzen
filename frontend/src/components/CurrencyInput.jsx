import { useState, useRef } from 'react'

function parseDE(str) {
  if (str == null || str === '') return null
  // Remove thousands separators (dots), replace comma with dot
  const cleaned = String(str).replace(/\./g, '').replace(',', '.')
  const n = parseFloat(cleaned)
  return isNaN(n) ? null : n
}

function formatDE(n) {
  if (n == null || n === '' || isNaN(Number(n))) return ''
  return new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n))
}

/**
 * Currency input with German formatting (1.234,56).
 * Props:
 *   value       – number or null/undefined
 *   onChange    – called with number (or null if empty)
 *   className   – forwarded to <input>
 *   required, min, placeholder, autoFocus, id, name
 */
export default function CurrencyInput({ value, onChange, className = 'input', ...rest }) {
  const [focused, setFocused] = useState(false)
  const [raw, setRaw] = useState('')
  const inputRef = useRef(null)

  const handleFocus = () => {
    // Show raw editable value: just the number with comma decimal
    const n = value != null && value !== '' ? Number(value) : null
    setRaw(n != null ? String(n).replace('.', ',') : '')
    setFocused(true)
  }

  const handleChange = (e) => {
    const v = e.target.value
    // Allow digits, comma, minus, dot (dot will be stripped as thousands sep)
    setRaw(v)
    const n = parseDE(v)
    onChange(n)
  }

  const handleBlur = () => {
    const n = parseDE(raw)
    onChange(n)
    setFocused(false)
  }

  const displayValue = focused ? raw : formatDE(value)

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode="decimal"
      className={`${className} text-right`}
      value={displayValue}
      onFocus={handleFocus}
      onChange={handleChange}
      onBlur={handleBlur}
      {...rest}
    />
  )
}
