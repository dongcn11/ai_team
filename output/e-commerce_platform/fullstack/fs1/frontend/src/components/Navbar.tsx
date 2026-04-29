import { useAuth } from '../contexts/AuthContext'
import { ThemeToggle } from './ThemeToggle'

export function Navbar() {
  const { logout } = useAuth()

  return (
    <nav className="border-b border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Todo App</h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <button
              onClick={logout}
              className="rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}
