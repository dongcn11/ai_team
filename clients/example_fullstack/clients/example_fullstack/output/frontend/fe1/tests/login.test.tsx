import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { LoginPage } from '../src/routes/LoginPage';
import { ToastProvider } from '../src/components/ui/Toast';
import { useAuthStore } from '../src/stores/auth-store';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ accessToken: null, user: null });
  });

  const renderLoginPage = () => {
    return render(
      <BrowserRouter>
        <ToastProvider>
          <LoginPage />
        </ToastProvider>
      </BrowserRouter>
    );
  };

  it('should render login form', () => {
    renderLoginPage();
    
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/mật khẩu/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /đăng nhập/i })).toBeInTheDocument();
  });

  it('should show validation error for empty email', async () => {
    renderLoginPage();
    
    const submitButton = screen.getByRole('button', { name: /đăng nhập/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/email không hợp lệ/i)).toBeInTheDocument();
    });
  });

  it('should show validation error for empty password', async () => {
    renderLoginPage();
    
    const emailInput = screen.getByLabelText(/email/i);
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    
    const submitButton = screen.getByRole('button', { name: /đăng nhập/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/mật khẩu không được để trống/i)).toBeInTheDocument();
    });
  });

  it('should have link to register page', () => {
    renderLoginPage();
    
    const registerLink = screen.getByRole('link', { name: /đăng ký/i });
    expect(registerLink).toHaveAttribute('href', '/register');
  });
});
