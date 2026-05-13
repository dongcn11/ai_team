import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '../types/auth';

interface AuthState {
  accessToken: string | null;
  user: User | null;
  setAuth: (accessToken: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,
      setAuth: (accessToken, user) => set({ accessToken, user }),
      logout: () => set({ accessToken: null, user: null }),
    }),
    {
      name: 'auth',
    },
  ),
);
