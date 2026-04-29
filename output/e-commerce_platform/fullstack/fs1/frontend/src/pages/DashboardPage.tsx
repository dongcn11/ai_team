import { useState, useEffect } from 'react'
import { Layout } from '../components/Layout'
import { TaskList } from '../components/TaskList'
import { taskService, Task, TaskStatus, TaskCreate } from '../services/taskService'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../hooks/useToast'

export function DashboardPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newPriority, setNewPriority] = useState<'low' | 'medium' | 'high'>('medium')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const { accessToken } = useAuth()
  const { showToast } = useToast()

  const fetchTasks = async () => {
    if (!accessToken) return
    try {
      setIsLoading(true)
      setError(null)
      const data = await taskService.getTasks(accessToken)
      setTasks(data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load tasks'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchTasks()
  }, [accessToken])

  const handleAddTask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!accessToken || !newTitle.trim()) return
    try {
      setIsSubmitting(true)
      const taskData: TaskCreate = {
        title: newTitle.trim(),
        description: newDescription.trim() || undefined,
        priority: newPriority,
      }
      const created = await taskService.createTask(accessToken, taskData)
      setTasks((prev) => [created, ...prev])
      setNewTitle('')
      setNewDescription('')
      setNewPriority('medium')
      setShowAddForm(false)
      showToast('Task created successfully', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create task'
      showToast(message, 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleStatusChange = async (id: string, status: TaskStatus) => {
    if (!accessToken) return
    try {
      const updated = await taskService.updateTaskStatus(accessToken, id, status)
      setTasks((prev) => prev.map((t) => (t.id === id ? updated : t)))
      showToast('Task updated', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update task'
      showToast(message, 'error')
    }
  }

  const handleDelete = async (id: string) => {
    if (!accessToken) return
    try {
      await taskService.deleteTask(accessToken, id)
      setTasks((prev) => prev.filter((t) => t.id !== id))
      showToast('Task deleted', 'success')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete task'
      showToast(message, 'error')
    }
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">My Tasks</h2>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            + Add Task
          </button>
        </div>

        {showAddForm && (
          <form onSubmit={handleAddTask} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="space-y-3">
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Task title"
                required
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              />
              <textarea
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Description (optional)"
                rows={2}
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
              />
              <div className="flex items-center justify-between">
                <select
                  value={newPriority}
                  onChange={(e) => setNewPriority(e.target.value as 'low' | 'medium' | 'high')}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="low">Low Priority</option>
                  <option value="medium">Medium Priority</option>
                  <option value="high">High Priority</option>
                </select>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowAddForm(false)}
                    className="rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting || !newTitle.trim()}
                    className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isSubmitting ? 'Adding...' : 'Add Task'}
                  </button>
                </div>
              </div>
            </div>
          </form>
        )}

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}

        <TaskList
          tasks={tasks}
          isLoading={isLoading}
          onStatusChange={handleStatusChange}
          onDelete={handleDelete}
        />
      </div>
    </Layout>
  )
}
