const BASE_URL = '/api'

export type TaskStatus = 'todo' | 'in-progress' | 'done'
export type TaskPriority = 'low' | 'medium' | 'high'

export interface Task {
  id: string
  user_id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  deadline: string | null
  created_at: string
  updated_at: string
}

export interface TaskCreate {
  title: string
  description?: string
  priority?: TaskPriority
  deadline?: string
}

export interface TaskUpdate {
  title?: string
  description?: string
  priority?: TaskPriority
  deadline?: string
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || 'Request failed')
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

function authHeaders(token: string) {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

export const taskService = {
  async getTasks(
    token: string,
    filters?: { status?: TaskStatus; priority?: TaskPriority; search?: string }
  ): Promise<Task[]> {
    const params = new URLSearchParams()
    if (filters?.status) params.set('status', filters.status)
    if (filters?.priority) params.set('priority', filters.priority)
    if (filters?.search) params.set('search', filters.search)
    const res = await fetch(`${BASE_URL}/tasks?${params}`, {
      headers: authHeaders(token),
    })
    return handleResponse<Task[]>(res)
  },

  async getTask(token: string, id: string): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${id}`, {
      headers: authHeaders(token),
    })
    return handleResponse<Task>(res)
  },

  async createTask(token: string, data: TaskCreate): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks`, {
      method: 'POST',
      headers: authHeaders(token),
      body: JSON.stringify(data),
    })
    return handleResponse<Task>(res)
  },

  async updateTask(token: string, id: string, data: TaskUpdate): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${id}`, {
      method: 'PUT',
      headers: authHeaders(token),
      body: JSON.stringify(data),
    })
    return handleResponse<Task>(res)
  },

  async deleteTask(token: string, id: string): Promise<void> {
    const res = await fetch(`${BASE_URL}/tasks/${id}`, {
      method: 'DELETE',
      headers: authHeaders(token),
    })
    return handleResponse<void>(res)
  },

  async updateTaskStatus(token: string, id: string, status: TaskStatus): Promise<Task> {
    const res = await fetch(`${BASE_URL}/tasks/${id}/status`, {
      method: 'PATCH',
      headers: authHeaders(token),
      body: JSON.stringify({ status }),
    })
    return handleResponse<Task>(res)
  },
}
