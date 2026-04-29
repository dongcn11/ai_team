import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LoginForm } from '../components/LoginForm'
import { authService } from '../services/authService'
import { useAuth } from '../contexts/AuthContext'

export function LoginPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const { login } = useAuth()

  const handleLogin = async (email: string, password: string) => {
    try {
      setIsLoading(true)
      setError(null)
      const tokens = await authService.login(email, password)
      login(tokens.access_token, tokens.refresh_token)
      navigate('/dashboard')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An error occurred'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-900">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Todo App</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Sign in to your account</p>
        </div>

        <div className="rounded-lg bg-white p-8 shadow dark:bg-gray-800">
          <LoginForm onSubmit={handleLogin} isLoading={isLoading} error={error} />

          <p className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
            Don't have an account?{' '}
            <Link to="/register" className="font-medium text-blue-600 hover:text-blue-500">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
