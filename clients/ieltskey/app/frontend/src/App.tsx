import { useState } from 'react'

import CourseForm from './components/CourseForm'
import CourseList from './components/CourseList'
import type { Course } from './types'

export default function App() {
  // Đổi số này là ép CourseList gọi lại API — rẻ hơn nhiều so với kéo state
  // danh sách lên đây rồi tự chèn item mới (dễ lệch với bộ lọc đang bật).
  const [reloadToken, setReloadToken] = useState(0)
  const [highlightId, setHighlightId] = useState<number | null>(null)

  function handleCreated(course: Course) {
    setHighlightId(course.id)
    setReloadToken(token => token + 1)
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-4">
          <h1 className="text-xl font-semibold text-slate-900">Ieltskey</h1>
          <p className="text-sm text-slate-500">Quản lý khóa học IELTS</p>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl items-start gap-6 px-6 py-8 lg:grid-cols-2">
        <CourseForm onCreated={handleCreated} />
        <CourseList reloadToken={reloadToken} highlightId={highlightId} />
      </main>
    </div>
  )
}
