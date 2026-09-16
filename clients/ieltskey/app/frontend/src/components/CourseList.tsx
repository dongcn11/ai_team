import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { listCourses } from '../api/courses'
import { formatDate, formatVnd } from '../lib/format'
import {
  LEVEL_LABELS,
  SKILL_LABELS,
  STATUS_LABELS,
  type Course,
  type CourseListResponse,
  type CourseSkill,
  type CourseStatus,
} from '../types'

const PAGE_SIZE = 10

const STATUS_BADGE: Record<CourseStatus, string> = {
  draft: 'bg-slate-100 text-slate-600',
  published: 'bg-emerald-100 text-emerald-800',
  archived: 'bg-amber-100 text-amber-800',
}

const selectCls =
  'rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm outline-none ' +
  'focus:border-sky-500 focus:ring-2 focus:ring-sky-100'

function CourseRow({ course, highlighted }: { course: Course; highlighted: boolean }) {
  return (
    <li
      className={
        'rounded-lg border px-4 py-3 transition-colors ' +
        (highlighted ? 'border-sky-400 bg-sky-50' : 'border-slate-200 bg-white')
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-medium text-slate-900">{course.title}</h3>
          <p className="truncate text-xs text-slate-400">/{course.slug}</p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[course.status]}`}
        >
          {STATUS_LABELS[course.status]}
        </span>
      </div>

      {course.description && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600">{course.description}</p>
      )}

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600 sm:grid-cols-4">
        <div>
          <dt className="text-slate-400">Trình độ</dt>
          <dd>{LEVEL_LABELS[course.level]}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Kỹ năng</dt>
          <dd>{SKILL_LABELS[course.skill]}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Thời lượng</dt>
          <dd>
            {course.duration_weeks} tuần · {course.total_sessions} buổi
          </dd>
        </div>
        <div>
          <dt className="text-slate-400">Học phí</dt>
          <dd>{course.price_vnd > 0 ? formatVnd(course.price_vnd) : 'Miễn phí'}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Khai giảng</dt>
          <dd>{formatDate(course.start_date)}</dd>
        </div>
        <div>
          <dt className="text-slate-400">Sĩ số</dt>
          <dd>{course.max_students} học viên</dd>
        </div>
        <div>
          <dt className="text-slate-400">Band mục tiêu</dt>
          <dd>{course.target_band !== null ? course.target_band.toFixed(1) : '—'}</dd>
        </div>
      </dl>
    </li>
  )
}

export default function CourseList({
  reloadToken,
  highlightId,
}: {
  /** Tăng lên mỗi lần có khóa mới được tạo để danh sách tải lại. */
  reloadToken: number
  highlightId: number | null
}) {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<CourseStatus | ''>('')
  const [skillFilter, setSkillFilter] = useState<CourseSkill | ''>('')
  const [offset, setOffset] = useState(0)

  const [data, setData] = useState<CourseListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Gõ tới đâu gọi API tới đó thì quá tốn; chờ người dùng ngừng gõ 300ms.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])

  // Khóa vừa tạo nằm đầu danh sách nên phải quay về trang 1 mới thấy.
  // Khi đang ở trang 1 sẵn thì setState bail-out, không có request thừa.
  useEffect(() => {
    setOffset(0)
  }, [reloadToken])

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    listCourses({
      q: debouncedSearch,
      status: statusFilter,
      skill: skillFilter,
      limit: PAGE_SIZE,
      offset,
    })
      .then(res => {
        if (cancelled) return
        setData(res)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Không tải được danh sách khóa học.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [debouncedSearch, statusFilter, skillFilter, offset, reloadToken])

  const total = data?.total ?? 0
  const items = data?.items ?? []
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-900">Danh sách khóa học</h2>
        <span className="text-sm text-slate-500">{total} khóa</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <input
          aria-label="Tìm theo tên khóa học"
          className="min-w-[12rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm
                     outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          placeholder="Tìm theo tên khóa học…"
          value={search}
          onChange={e => {
            setSearch(e.target.value)
            setOffset(0)
          }}
        />
        <select
          aria-label="Lọc theo trạng thái"
          className={selectCls}
          value={statusFilter}
          onChange={e => {
            setStatusFilter(e.target.value as CourseStatus | '')
            setOffset(0)
          }}
        >
          <option value="">Mọi trạng thái</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Lọc theo kỹ năng"
          className={selectCls}
          value={skillFilter}
          onChange={e => {
            setSkillFilter(e.target.value as CourseSkill | '')
            setOffset(0)
          }}
        >
          <option value="">Mọi kỹ năng</option>
          {Object.entries(SKILL_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div role="alert" className="mt-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </div>
      )}

      {/* Giữ danh sách cũ mờ đi khi đang tải lại, tránh nhảy layout mỗi lần gõ. */}
      <div className={loading ? 'opacity-50 transition-opacity' : 'transition-opacity'}>
        {items.length === 0 && !loading && !error ? (
          <p className="mt-6 text-sm text-slate-500">
            {debouncedSearch || statusFilter || skillFilter
              ? 'Không có khóa học nào khớp bộ lọc.'
              : 'Chưa có khóa học nào. Tạo khóa đầu tiên ở form bên cạnh.'}
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {items.map(course => (
              <CourseRow key={course.id} course={course} highlighted={course.id === highlightId} />
            ))}
          </ul>
        )}
      </div>

      {pageCount > 1 && (
        <div className="mt-5 flex items-center justify-between text-sm">
          <button
            type="button"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700
                       hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            ← Trước
          </button>
          <span className="text-slate-500">
            Trang {page}/{pageCount}
          </span>
          <button
            type="button"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700
                       hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300"
            disabled={page >= pageCount || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Sau →
          </button>
        </div>
      )}
    </section>
  )
}
