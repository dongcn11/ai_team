# Skill: React Patterns

## Cấu trúc file chuẩn
```
frontend/src/
├── api/
│   └── client.ts         ← axios instance + API functions
├── hooks/
│   ├── useAuth.ts        ← auth state, login, logout
│   └── useTasks.ts       ← tasks CRUD hooks
├── components/
│   ├── TaskCard.tsx      ← 1 task item
│   ├── TaskList.tsx      ← danh sách tasks
│   └── TaskForm.tsx      ← form tạo/sửa task
├── pages/
│   ├── LoginPage.tsx
│   ├── RegisterPage.tsx
│   └── TasksPage.tsx
├── types/
│   └── index.ts          ← TypeScript interfaces
└── App.tsx               ← routing
```

## Component pattern chuẩn
```tsx
// Luôn dùng TypeScript interface cho props
interface TaskCardProps {
  task: Task
  onDelete: (id: string) => void
  onStatusChange: (id: string, status: TaskStatus) => void
}

// Functional component với explicit return type
export const TaskCard: React.FC<TaskCardProps> = ({ task, onDelete, onStatusChange }) => {
  return (
    <div className="bg-white rounded-lg border p-4 shadow-sm">
      <h3 className="font-medium text-gray-900">{task.title}</h3>
      <p className="text-sm text-gray-500 mt-1">{task.description}</p>
    </div>
  )
}
```

## Custom hooks pattern
```tsx
// hooks/useTasks.ts
export const useTasks = () => {
  const [tasks, setTasks]   = useState<Task[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  const fetchTasks = useCallback(async (filters?: TaskFilters) => {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getTasks(filters)
      setTasks(data)
    } catch (err) {
      setError("Không thể tải danh sách task")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTasks() }, [fetchTasks])

  return { tasks, loading, error, fetchTasks }
}
```

## Routing với React Router
```tsx
// App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"

function App() {
  const { user } = useAuth()
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login"    element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/tasks"    element={user ? <TasksPage /> : <Navigate to="/login" />} />
        <Route path="/"         element={<Navigate to="/tasks" />} />
      </Routes>
    </BrowserRouter>
  )
}
```
