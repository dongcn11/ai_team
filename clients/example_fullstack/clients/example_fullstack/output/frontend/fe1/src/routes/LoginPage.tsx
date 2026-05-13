import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import { useEffect, useRef } from 'react';
import { AuthLayout } from '../components/layout/AuthLayout';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { useToast } from '../components/ui/Toast';
import { api } from '../lib/api';
import { useAuth } from '../hooks/useAuth';
import type { ApiErrorResponse } from '../types/api-error';

const schema = z.object({
  email: z.string().email('Email không hợp lệ'),
  password: z.string().min(1, 'Mật khẩu không được để trống'),
});

type FormData = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { login } = useAuth();
  const emailInputRef = useRef<HTMLInputElement>(null);
  
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  useEffect(() => {
    emailInputRef.current?.focus();
  }, []);

  const onSubmit = async (data: FormData) => {
    try {
      const response = await api.post('/auth/login', {
        email: data.email,
        password: data.password,
      });
      
      const { access_token, user } = response.data;
      login(access_token, user);
      navigate('/dashboard');
    } catch (err) {
      const error = err as { response?: { data: ApiErrorResponse; status: number } };
      
      if (error.response?.status === 401) {
        showToast('Email hoặc mật khẩu không đúng', 'error');
      } else if (error.response?.status === 429) {
        showToast('Quá nhiều lần thử, vui lòng đợi vài phút', 'error');
      } else {
        showToast('Không kết nối được server', 'error');
      }
    }
  };

  return (
    <AuthLayout
      title="Đăng nhập"
      subtitle="Nhập thông tin để đăng nhập"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Input
          ref={emailInputRef}
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register('email')}
        />
        
        <Input
          label="Mật khẩu"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register('password')}
        />
        
        <Button
          type="submit"
          className="w-full"
          isLoading={isSubmitting}
        >
          Đăng nhập
        </Button>
        
        <p className="text-center text-sm text-gray-600">
          Chưa có tài khoản?{' '}
          <Link to="/register" className="text-blue-600 hover:underline">
            Đăng ký
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
