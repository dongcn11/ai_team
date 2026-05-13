import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from './stores/auth-store';
import { api } from './lib/api';

function App() {
  const navigate = useNavigate();
  const { accessToken, logout } = useAuthStore();

  useEffect(() => {
    if (accessToken) {
      api.get('/auth/me').catch(() => {
        logout();
        navigate('/login');
      });
    }
  }, [accessToken, logout, navigate]);

  return null;
}

export default App;
