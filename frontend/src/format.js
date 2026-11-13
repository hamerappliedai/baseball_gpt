// Display formats from the API's column metadata (see backend/stats.py).
export function formatValue(value, format) {
  if (value === null || value === undefined) return '—'
  switch (format) {
    case 'int':
      return Number(value).toLocaleString('en-US')
    case 'rate3': {
      const s = Number(value).toFixed(3)
      return Math.abs(value) < 1 ? s.replace(/^(-?)0\./, '$1.') : s // .366, but 1.035 OPS
    }
    case 'dec2':
      return Number(value).toFixed(2)
    default:
      return String(value)
  }
}

export const isNumeric = (format) => ['int', 'rate3', 'dec2', 'ip'].includes(format)
