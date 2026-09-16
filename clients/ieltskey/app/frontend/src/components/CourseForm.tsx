import { useState, type FormEvent, type ReactNode } from 'react'
import { ApiError, type FieldErrors } from '../api/client'
import { createCourse } from '../api/courses'
import { formatVnd } from '../lib/format'
import {
  BAND_OPTIONS,
  LEVEL_LABELS,
  SKILL_LABELS,
  type Course,
  type CourseCreate,
  type CourseLevel,
  type CourseSkill,
  type CourseStatus,
} from '../types'

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

interface FormState {
  title: string
  slug: string
  description: string
  level: CourseLevel
  skill: CourseSkill
  target_band: string
  duration_weeks: string
  sessions_per_week: string
  price_vnd: string
  max_students: string
  start_date: string
  status: CourseStatus
}

const EMPTY: FormState = {
  title: '',
  slug: '',
  description: '',
  level: 'band_6_5',
  skill: 'full',
  target_band: '',
  duration_weeks: '8',
  sessions_per_week: '3',
  price_vnd: '',
  max_students: '20',
  start_date: '',
  status: 'draft',
}

/** Kiểm tra ngay trên trình duyệt để người dùng không phải chờ round-trip.
 *  Backend vẫn kiểm tra lại y hệt — đây chỉ là lớp tiện lợi, không phải lớp chặn. */
function validate(f: FormState): FieldErrors {
  const e: FieldErrors = {}
  const title = f.title.trim().replace(/\s+/g, ' ')

  if (title.length < 3) e.title = 'Tên khóa học phải có ít nhất 3 ký tự'
  else if (title.length > 160) e.title = 'Tên khóa học tối đa 160 ký tự'

  const slug = f.slug.trim()
  if (slug && !SLUG_RE.test(slug))
    e.slug = 'Slug chỉ gồm chữ thường, số và dấu gạch ngang (vd: ielts-6-5-cap-toc)'

  const weeks = Number(f.duration_weeks)
  if (!Number.isInteger(weeks) || weeks < 1 || weeks > 104)
    e.duration_weeks = 'Số tuần phải là số nguyên từ 1 đến 104'

  const sessions = Number(f.sessions_per_week)
  if (!Number.isInteger(sessions) || sessions < 1 || sessions > 14)
    e.sessions_per_week = 'Số buổi/tuần phải là số nguyên từ 1 đến 14'

  const price = Number(f.price_vnd || 0)
  if (!Number.isInteger(price) || price < 0) e.price_vnd = 'Học phí phải là số nguyên không âm'

  const seats = Number(f.max_students)
  if (!Number.isInteger(seats) || seats < 1 || seats > 500)
    e.max_students = 'Sĩ số tối đa phải từ 1 đến 500'

  if (f.status === 'published') {
    if (!f.start_date) e.start_date = 'Khóa mở đăng ký phải có ngày khai giảng'
    if (price <= 0) e.price_vnd = 'Khóa mở đăng ký phải có học phí lớn hơn 0'
  }

  return e
}

const inputCls =
  'w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none ' +
  'focus:border-sky-500 focus:ring-2 focus:ring-sky-100 disabled:bg-slate-100'
const errorCls = 'border-rose-400 focus:border-rose-500 focus:ring-rose-100'

function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string
  htmlFor: string
  error?: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-rose-600">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  )
}

export default function CourseForm({ onCreated }: { onCreated: (course: Course) => void }) {
  const [form, setForm] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [banner, setBanner] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(prev => ({ ...prev, [key]: value }))
    // xóa lỗi của đúng ô vừa sửa, giữ nguyên lỗi các ô khác
    setErrors(prev => {
      if (!(key in prev)) return prev
      const next = { ...prev }
      delete next[key as string]
      return next
    })
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const found = validate(form)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      setBanner({ kind: 'err', text: 'Còn ô chưa hợp lệ, xem chi tiết bên dưới từng ô.' })
      return
    }

    setSaving(true)
    setBanner(null)
    try {
      const payload: CourseCreate = {
        title: form.title.trim().replace(/\s+/g, ' '),
        slug: form.slug.trim() || null,
        description: form.description.trim() || null,
        level: form.level,
        skill: form.skill,
        target_band: form.target_band ? Number(form.target_band) : null,
        duration_weeks: Number(form.duration_weeks),
        sessions_per_week: Number(form.sessions_per_week),
        price_vnd: Number(form.price_vnd || 0),
        max_students: Number(form.max_students),
        start_date: form.start_date || null,
        status: form.status,
      }
      const created = await createCourse(payload)
      setForm(EMPTY)
      setBanner({ kind: 'ok', text: `Đã tạo khóa "${created.title}" — slug: ${created.slug}` })
      onCreated(created)
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors)
        setBanner({ kind: 'err', text: err.message })
      } else {
        setBanner({ kind: 'err', text: 'Có lỗi không xác định khi tạo khóa học.' })
      }
    } finally {
      setSaving(false)
    }
  }

  const totalSessions = Number(form.duration_weeks) * Number(form.sessions_per_week)
  const price = Number(form.price_vnd || 0)

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
    >
      <h2 className="text-lg font-semibold text-slate-900">Tạo khóa học</h2>
      <p className="mt-1 text-sm text-slate-500">
        Khóa mới mặc định là bản nháp. Chọn “Đang mở đăng ký” khi đã chốt ngày khai giảng và học phí.
      </p>

      {banner && (
        <div
          role="status"
          className={
            'mt-4 rounded-md px-3 py-2 text-sm ' +
            (banner.kind === 'ok'
              ? 'bg-emerald-50 text-emerald-800'
              : 'bg-rose-50 text-rose-800')
          }
        >
          {banner.text}
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <Field
            label="Tên khóa học *"
            htmlFor="title"
            error={errors.title}
            hint="Ví dụ: Luyện thi IELTS 6.5 cấp tốc"
          >
            <input
              id="title"
              className={`${inputCls} ${errors.title ? errorCls : ''}`}
              value={form.title}
              onChange={e => set('title', e.target.value)}
              maxLength={160}
              disabled={saving}
            />
          </Field>
        </div>

        <Field
          label="Slug"
          htmlFor="slug"
          error={errors.slug}
          hint="Bỏ trống để hệ thống tự sinh từ tên khóa học"
        >
          <input
            id="slug"
            className={`${inputCls} ${errors.slug ? errorCls : ''}`}
            value={form.slug}
            onChange={e => set('slug', e.target.value)}
            placeholder="luyen-thi-ielts-6-5-cap-toc"
            disabled={saving}
          />
        </Field>

        <Field label="Trình độ đầu vào *" htmlFor="level" error={errors.level}>
          <select
            id="level"
            className={inputCls}
            value={form.level}
            onChange={e => set('level', e.target.value as CourseLevel)}
            disabled={saving}
          >
            {Object.entries(LEVEL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Kỹ năng tập trung" htmlFor="skill" error={errors.skill}>
          <select
            id="skill"
            className={inputCls}
            value={form.skill}
            onChange={e => set('skill', e.target.value as CourseSkill)}
            disabled={saving}
          >
            {Object.entries(SKILL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Band đầu ra mục tiêu" htmlFor="target_band" error={errors.target_band}>
          <select
            id="target_band"
            className={inputCls}
            value={form.target_band}
            onChange={e => set('target_band', e.target.value)}
            disabled={saving}
          >
            <option value="">— Không cam kết —</option>
            {BAND_OPTIONS.map(b => (
              <option key={b} value={b}>
                {b.toFixed(1)}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label="Số tuần *"
          htmlFor="duration_weeks"
          error={errors.duration_weeks}
          hint={
            Number.isFinite(totalSessions) && totalSessions > 0
              ? `Tổng ${totalSessions} buổi`
              : undefined
          }
        >
          <input
            id="duration_weeks"
            type="number"
            min={1}
            max={104}
            className={`${inputCls} ${errors.duration_weeks ? errorCls : ''}`}
            value={form.duration_weeks}
            onChange={e => set('duration_weeks', e.target.value)}
            disabled={saving}
          />
        </Field>

        <Field label="Số buổi / tuần *" htmlFor="sessions_per_week" error={errors.sessions_per_week}>
          <input
            id="sessions_per_week"
            type="number"
            min={1}
            max={14}
            className={`${inputCls} ${errors.sessions_per_week ? errorCls : ''}`}
            value={form.sessions_per_week}
            onChange={e => set('sessions_per_week', e.target.value)}
            disabled={saving}
          />
        </Field>

        <Field
          label="Học phí (VNĐ) *"
          htmlFor="price_vnd"
          error={errors.price_vnd}
          hint={price > 0 ? formatVnd(price) : 'Để 0 nếu là khóa miễn phí (chỉ lưu nháp được)'}
        >
          <input
            id="price_vnd"
            type="number"
            min={0}
            step={100000}
            className={`${inputCls} ${errors.price_vnd ? errorCls : ''}`}
            value={form.price_vnd}
            onChange={e => set('price_vnd', e.target.value)}
            placeholder="12000000"
            disabled={saving}
          />
        </Field>

        <Field label="Sĩ số tối đa *" htmlFor="max_students" error={errors.max_students}>
          <input
            id="max_students"
            type="number"
            min={1}
            max={500}
            className={`${inputCls} ${errors.max_students ? errorCls : ''}`}
            value={form.max_students}
            onChange={e => set('max_students', e.target.value)}
            disabled={saving}
          />
        </Field>

        <Field label="Ngày khai giảng" htmlFor="start_date" error={errors.start_date}>
          <input
            id="start_date"
            type="date"
            className={`${inputCls} ${errors.start_date ? errorCls : ''}`}
            value={form.start_date}
            onChange={e => set('start_date', e.target.value)}
            disabled={saving}
          />
        </Field>

        <Field label="Trạng thái" htmlFor="status" error={errors.status}>
          <select
            id="status"
            className={inputCls}
            value={form.status}
            onChange={e => set('status', e.target.value as CourseStatus)}
            disabled={saving}
          >
            <option value="draft">Bản nháp</option>
            <option value="published">Đang mở đăng ký</option>
          </select>
        </Field>

        <div className="md:col-span-2">
          <Field label="Mô tả" htmlFor="description" error={errors.description}>
            <textarea
              id="description"
              rows={4}
              maxLength={4000}
              className={`${inputCls} ${errors.description ? errorCls : ''}`}
              value={form.description}
              onChange={e => set('description', e.target.value)}
              placeholder="Lộ trình, giáo trình, đầu ra cam kết…"
              disabled={saving}
            />
          </Field>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white
                     hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {saving ? 'Đang lưu…' : 'Tạo khóa học'}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() => {
            setForm(EMPTY)
            setErrors({})
            setBanner(null)
          }}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
        >
          Xóa form
        </button>
      </div>
    </form>
  )
}
