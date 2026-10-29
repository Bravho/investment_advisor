export const money = (value = 0) =>
  new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB', minimumFractionDigits: 2 }).format(Number(value) || 0)

export const number = (value = 0, digits = 2) =>
  new Intl.NumberFormat('th-TH', { maximumFractionDigits: digits }).format(Number(value) || 0)

export const percent = (value = 0, digits = 2) => `${number(value, digits)}%`

export const shortDate = (value) => {
  if (!value) return '-'
  return new Intl.DateTimeFormat('th-TH', { day: '2-digit', month: 'short', year: '2-digit' }).format(new Date(value))
}

export const time = (value) => {
  if (!value) return '-'
  return new Intl.DateTimeFormat('th-TH', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok' }).format(new Date(value))
}

export const normalizeRisk = (value) => {
  const score = Number(value) || 0
  return score <= 1 ? score * 100 : score
}

export const valueOf = (object, keys, fallback = 0) => {
  for (const key of keys) if (object?.[key] !== undefined && object?.[key] !== null) return object[key]
  return fallback
}
