const VND = new Intl.NumberFormat('vi-VN')

export function formatVnd(value: number): string {
  return `${VND.format(value)} ₫`
}

/** "2026-09-15" -> "15/09/2026". Chuỗi rỗng/null trả về "—". */
export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}/${m}/${y}` : iso
}
