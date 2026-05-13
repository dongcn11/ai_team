import { type ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../stores/auth-store';

interface ProtectedRouteProps {
  children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const token = useAuthStore((state) => state.accessToken);
  
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}
