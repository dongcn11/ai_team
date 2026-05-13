import { useCallback } from 'react';
import { useAuthStore } from '../stores/auth-store';
import type { User } from '../types/auth';

export function useAuth() {
  const { accessToken, user, setAuth, logout } = useAuthStore();

  const login = useCallback((token: string, userData: User) => {
    setAuth(token, userData);
  }, [setAuth]);

  const logoutUser = useCallback(async () => {
    logout();
  }, [logout]);

  return {
    accessToken,
    user,
    isAuthenticated: !!accessToken,
    login,
    logout: logoutUser,
  };
}
