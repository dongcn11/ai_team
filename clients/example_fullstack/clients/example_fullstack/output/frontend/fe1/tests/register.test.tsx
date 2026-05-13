import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { RegisterPage } from '../src/routes/RegisterPage';
import { ToastProvider } from '../src/components/ui/Toast';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderRegisterPage = () => {
    return render(
      <BrowserRouter>
        <ToastProvider>
          <RegisterPage />
        </ToastProvider>
      </BrowserRouter>
    );
  };

  it('should render register form', () => {
    renderRegisterPage();
    
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/mật khẩu/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/xác nhận mật khẩu/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /đăng ký/i })).toBeInTheDocument();
  });

  it('should show validation error for invalid email', async () => {
    renderRegisterPage();
    
    const emailInput = screen.getByLabelText(/email/i);
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } });
    
    const submitButton = screen.getByRole('button', { name: /đăng ký/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/email không hợp lệ/i)).toBeInTheDocument();
    });
  });

  it('should show validation error for short password', async () => {
    renderRegisterPage();
    
    const emailInput = screen.getByLabelText(/email/i);
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    
    const passwordInput = screen.getByLabelText(/mật khẩu/i);
    fireEvent.change(passwordInput, { target: { value: 'short' } });
    
    const confirmInput = screen.getByLabelText(/xác nhận mật khẩu/i);
    fireEvent.change(confirmInput, { target: { value: 'short' } });
    
    const submitButton = screen.getByRole('button', { name: /đăng ký/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/tối thiểu 8 ký tự/i)).toBeInTheDocument();
    });
  });

  it('should show validation error for password mismatch', async () => {
    renderRegisterPage();
    
    const emailInput = screen.getByLabelText(/email/i);
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    
    const passwordInput = screen.getByLabelText(/mật khẩu/i);
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    
    const confirmInput = screen.getByLabelText(/xác nhận mật khẩu/i);
    fireEvent.change(confirmInput, { target: { value: 'password456' } });
    
    const submitButton = screen.getByRole('button', { name: /đăng ký/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/mật khẩu không khớp/i)).toBeInTheDocument();
    });
  });

  it('should have link to login page', () => {
    renderRegisterPage();
    
    const loginLink = screen.getByRole('link', { name: /đăng nhập/i });
    expect(loginLink).toHaveAttribute('href', '/login');
  });
});
