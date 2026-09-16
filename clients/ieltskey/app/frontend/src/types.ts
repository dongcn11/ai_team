export type CourseLevel = 'foundation' | 'pre_ielts' | 'band_5_5' | 'band_6_5' | 'band_7_plus'
export type CourseSkill = 'full' | 'listening' | 'reading' | 'writing' | 'speaking'
export type CourseStatus = 'draft' | 'published' | 'archived'

export interface Course {
  id: number
  title: string
  slug: string
  description: string | null
  level: CourseLevel
  skill: CourseSkill
  target_band: number | null
  duration_weeks: number
  sessions_per_week: number
  total_sessions: number
  price_vnd: number
  max_students: number
  start_date: string | null
  status: CourseStatus
  created_at: string
  updated_at: string
}

/** Payload gửi lên POST /api/courses — khớp `schemas.CourseCreate` phía backend. */
export interface CourseCreate {
  title: string
  slug?: string | null
  description?: string | null
  level: CourseLevel
  skill: CourseSkill
  target_band?: number | null
  duration_weeks: number
  sessions_per_week: number
  price_vnd: number
  max_students: number
  start_date?: string | null
  status: CourseStatus
}

export interface CourseListResponse {
  items: Course[]
  total: number
  limit: number
  offset: number
}

export const LEVEL_LABELS: Record<CourseLevel, string> = {
  foundation: 'Mất gốc (Foundation)',
  pre_ielts: 'Pre-IELTS',
  band_5_5: 'Mục tiêu 5.5',
  band_6_5: 'Mục tiêu 6.5',
  band_7_plus: 'Mục tiêu 7.0+',
}

export const SKILL_LABELS: Record<CourseSkill, string> = {
  full: 'Cả 4 kỹ năng',
  listening: 'Listening',
  reading: 'Reading',
  writing: 'Writing',
  speaking: 'Speaking',
}

export const STATUS_LABELS: Record<CourseStatus, string> = {
  draft: 'Bản nháp',
  published: 'Đang mở đăng ký',
  archived: 'Đã đóng',
}

/** Band IELTS chỉ chấm theo bước 0.5 — backend cũng chặn giá trị lẻ. */
export const BAND_OPTIONS = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0]
