import Select from 'react-select'

const BASE_STYLES = {
  control: (base, { isFocused }) => ({
    ...base,
    minHeight: '34px',
    fontSize: '0.875rem',
    backgroundColor: 'var(--flaeche)',
    borderColor: isFocused ? '#3b82f6' : 'var(--grau-300)',
    borderRadius: '0.375rem',
    boxShadow: isFocused ? '0 0 0 1px #3b82f6' : '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    '&:hover': { borderColor: isFocused ? '#3b82f6' : 'var(--grau-300)' },
  }),
  valueContainer: (base) => ({ ...base, padding: '1px 8px' }),
  input: (base) => ({ ...base, margin: 0, padding: 0, color: 'var(--grau-900)' }),
  indicatorSeparator: () => ({ display: 'none' }),
  clearIndicator: (base) => ({ ...base, padding: '2px 4px', color: 'var(--grau-400)', '&:hover': { color: 'var(--grau-500)' } }),
  dropdownIndicator: (base) => ({ ...base, padding: '2px 4px', color: 'var(--grau-400)' }),
  option: (base, { isSelected, isFocused }) => ({
    ...base,
    fontSize: '0.875rem',
    padding: '5px 12px',
    backgroundColor: isSelected ? '#2563eb' : isFocused ? 'var(--grau-100)' : 'var(--flaeche)',
    color: isSelected ? '#ffffff' : 'var(--grau-900)',
    cursor: 'pointer',
  }),
  placeholder: (base) => ({ ...base, color: 'var(--grau-400)', fontSize: '0.875rem' }),
  singleValue: (base) => ({ ...base, fontSize: '0.875rem', color: 'var(--grau-900)' }),
  menuPortal: (base) => ({ ...base, zIndex: 60 }),
}

// Im Menue nur der eigene Name, eingerueckt nach Ebene; im geschlossenen Feld
// der volle Pfad, damit gleichnamige Kategorien aus verschiedenen Zweigen
// (z. B. "Strom EG" in zwei Gebaeuden) unterscheidbar bleiben.
const formatOptionLabel = ({ label, pfad, ebene }, { context }) => {
  if (context === 'value') return <span>{pfad || label}</span>
  return (
    <span style={{ paddingLeft: `${ebene}rem`, fontWeight: ebene === 0 ? 600 : 400 }}>
      {label}
    </span>
  )
}

// Sucht im vollen Pfad, nicht nur im Namen: "wester strom" findet
// "Nebenkosten / Musterweg 1 / Strom EG"
const filterNachPfad = (option, suche) => {
  if (!suche) return true
  const heu = `${option.data.pfad ?? ''} ${option.data.label ?? ''}`.toLowerCase()
  return suche.toLowerCase().split(/\s+/).filter(Boolean).every(w => heu.includes(w))
}

export default function KategorieSelect({
  kategorien,
  value,
  onChange,
  placeholder = '– keine –',
  isClearable = true,
  className,
  menuAlign = 'left',
  rowBg,
}) {
  const bgColor = rowBg === 'bg-gray-50' ? 'var(--grau-50)' : 'var(--flaeche)'
  const styles = {
    ...BASE_STYLES,
    control: (base, { isFocused }) => ({
      ...BASE_STYLES.control(base, { isFocused }),
      backgroundColor: bgColor,
    }),
    menu: (base) => ({
      ...base,
      backgroundColor: 'var(--flaeche)',
      zIndex: 50,
      borderRadius: '0.375rem',
      boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
      border: '1px solid var(--grau-200)',
      minWidth: '180px',
      width: 'max-content',
      ...(menuAlign === 'right' ? { right: 0, left: 'auto' } : { left: 0, right: 'auto' }),
    }),
  }

  const options = kategorien.map(k => ({
    value: k.id,
    label: k.name,
    // ebene/pfad liefert /kategorien/flach; Fallback fuer Aufrufer, die eine
    // selbst zusammengestellte Liste uebergeben
    ebene: k.ebene ?? (k.uebergeordnet_id ? 1 : 0),
    pfad: k.pfad ?? k.name,
  }))

  const numVal = value !== '' && value != null ? Number(value) : null
  const selected = numVal != null ? (options.find(o => o.value === numVal) ?? null) : null

  return (
    <Select
      className={className}
      options={options}
      value={selected}
      onChange={opt => onChange(opt ? opt.value : null)}
      formatOptionLabel={formatOptionLabel}
      filterOption={filterNachPfad}
      placeholder={placeholder}
      isClearable={isClearable}
      styles={styles}
      menuPortalTarget={document.body}
      noOptionsMessage={() => 'Keine Kategorien'}
    />
  )
}
