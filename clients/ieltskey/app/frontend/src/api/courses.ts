import { apiFetch } from './client'
import type { Course, CourseCreate, CourseListResponse, CourseSkill, CourseStatus } from '../types'

export function createCourse(payload: CourseCreate): Promise<Course> {
  return apiFetch<Course>('/api/courses', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export interface CourseFilters {
  q?: string
  status?: CourseStatus | ''
  skill?: CourseSkill | ''
  limit?: number
  offset?: number
}

export function listCourses(filters: CourseFilters = {}): Promise<CourseListResponse> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return apiFetch<CourseListResponse>(`/api/courses${qs ? `?${qs}` : ''}`)
}

export function getCourse(id: number): Promise<Course> {
  return apiFetch<Course>(`/api/courses/${id}`)
}
