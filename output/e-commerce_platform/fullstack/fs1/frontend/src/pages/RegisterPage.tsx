import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { RegisterForm } from '../components/RegisterForm'
import { authService } from '../services/authService'

export function RegisterPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const handleRegister = async (username: string, email: string, password: string) => {
    try {
      setIsLoading(true)
      setError(null)
      await authService.register({ username, email, password })
      navigate('/login')
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
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Create Account</h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Sign up to get started</p>
        </div>

        <div className="rounded-lg bg-white p-8 shadow dark:bg-gray-800">
          <RegisterForm onSubmit={handleRegister} isLoading={isLoading} error={error} />

          <p className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-blue-600 hover:text-blue-500">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
