// Display formats from the API's column metadata (see backend/stats.py).
export function formatValue(value, format) {
  if (value === null || value === undefined || value === '') return '—'
  switch (format) {
    case 'int':
      return Number(value).toLocaleString('en-US')
    case 'rate3': {
      const s = Number(value).toFixed(3)
      return Math.abs(value) < 1 ? s.replace(/^(-?)0\./, '$1.') : s // .366, but 1.035 OPS
    }
    case 'dec2':
      return Number(value).toFixed(2)
    case 'pct':
      return `${(Number(value) * 100).toFixed(1)}%`
    case 'date':
      return formatDate(value)
    default:
      return String(value)
  }
}

export const isNumeric = (format) => ['int', 'rate3', 'dec2', 'ip', 'pct'].includes(format)

/** "1903-06-19" -> "June 19, 1903", without shifting the day by time zone. */
export function formatDate(iso) {
  if (!iso) return ''
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', dateStyle: 'long' })
}
