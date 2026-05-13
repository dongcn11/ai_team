import { type ReactNode } from 'react';
import { useAuthStore } from '../../stores/auth-store';
import { useToast } from '../ui/Toast';
import { api } from '../../lib/api';
import { useNavigate } from 'react-router-dom';

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const { user, logout: logoutStore } = useAuthStore();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout').catch(() => {
        // Best-effort, không cần await error
      });
    } finally {
      logoutStore();
      showToast('Đã đăng xuất', 'success');
      navigate('/login', { replace: true });
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Topbar */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <h1 className="text-xl font-bold text-gray-900">Task Management</h1>
            <div className="flex items-center space-x-4">
              {user && (
                <span className="text-sm text-gray-600">{user.email}</span>
              )}
              <button
                onClick={handleLogout}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm"
              >
                Đăng xuất
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
