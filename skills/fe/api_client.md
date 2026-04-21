# Skill: API Client (Axios)

## Setup axios instance
```typescript
// api/client.ts
import axios from "axios"

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
})

// Tự động đính token vào mọi request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token")
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Tự động redirect về login khi 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token")
      window.location.href = "/login"
    }
    return Promise.reject(err)
  }
)

export default api
```

## API functions — typed hoàn toàn
```typescript
// api/tasks.ts
import api from "./client"
import type { Task, TaskCreate, TaskUpdate, TaskFilters } from "../types"

export const tasksApi = {
  getAll: async (filters?: TaskFilters): Promise<Task[]> => {
    const params = new URLSearchParams()
    if (filters?.status)   params.append("status",   filters.status)
    if (filters?.priority) params.append("priority", filters.priority)
    const { data } = await api.get(`/api/tasks?${params}`)
    return data
  },

  create: async (task: TaskCreate): Promise<Task> => {
    const { data } = await api.post("/api/tasks", task)
    return data
  },

  update: async (id: string, updates: TaskUpdate): Promise<Task> => {
    const { data } = await api.patch(`/api/tasks/${id}`, updates)
    return data
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/api/tasks/${id}`)
  },
}
```

## TypeScript interfaces
```typescript
// types/index.ts
export type TaskStatus   = "todo" | "in-progress" | "done"
export type TaskPriority = "low" | "medium" | "high"

export interface Task {
  id:          string
  title:       string
  description: string
  status:      TaskStatus
  priority:    TaskPriority
  deadline:    string | null
  created_at:  string
}

export interface TaskCreate {
  title:       string
  description?: string
  priority?:   TaskPriority
  deadline?:   string
}
```
