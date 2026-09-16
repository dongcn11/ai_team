/** Lớp gọi API mỏng: gom lỗi FastAPI về một dạng duy nhất cho UI dùng. */

export interface FieldErrors {
  [field: string]: string
}

export class ApiError extends Error {
  status: number
  /** Lỗi 422 gắn được vào đúng ô input. */
  fieldErrors: FieldErrors

  constructor(status: number, message: string, fieldErrors: FieldErrors = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

interface ValidationItem {
  loc?: (string | number)[]
  msg?: string
}

/**
 * FastAPI trả lỗi theo 2 dạng:
 *  - HTTPException  -> { detail: "chuỗi" }
 *  - Validation 422 -> { detail: [{ loc: ["body", "title"], msg: "..." }] }
 * Lỗi từ model_validator có loc = ["body"] (không thuộc ô nào) nên đẩy lên
 * thông báo chung thay vì gắn vào input.
 */
function parseError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail

  if (typeof detail === 'string') return new ApiError(status, detail)

  if (Array.isArray(detail)) {
    const fieldErrors: FieldErrors = {}
    const general: string[] = []
    for (const item of detail as ValidationItem[]) {
      const msg = (item.msg ?? 'Giá trị không hợp lệ').replace(/^Value error,\s*/, '')
      const loc = item.loc ?? []
      const field = loc.length > 1 ? String(loc[loc.length - 1]) : ''
      if (field) fieldErrors[field] = msg
      else general.push(msg)
    }
    const message = general.length
      ? general.join('. ')
      : 'Dữ liệu chưa hợp lệ, kiểm tra lại các ô được đánh dấu.'
    return new ApiError(status, message, fieldErrors)
  }

  return new ApiError(status, `Lỗi máy chủ (HTTP ${status})`)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Không kết nối được máy chủ. Backend đã chạy chưa?')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw parseError(res.status, body)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
