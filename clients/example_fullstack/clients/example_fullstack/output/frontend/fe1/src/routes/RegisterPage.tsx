import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate, Link } from 'react-router-dom';
import { AuthLayout } from '../components/layout/AuthLayout';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { useToast } from '../components/ui/Toast';
import { api } from '../lib/api';
import type { ApiErrorResponse } from '../types/api-error';

const schema = z.object({
  email: z.string().email('Email không hợp lệ'),
  password: z
    .string()
    .min(8, 'Tối thiểu 8 ký tự')
    .refine(
      (v) => /[A-Za-z]/.test(v) && /\d/.test(v),
      'Phải có chữ và số'
    ),
  confirm: z.string(),
}).refine((data) => data.password === data.confirm, {
  path: ['confirm'],
  message: 'Mật khẩu không khớp',
});

type FormData = z.infer<typeof schema>;

export function RegisterPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
    clearErrors,
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    clearErrors();
    
    try {
      await api.post('/auth/register', {
        email: data.email,
        password: data.password,
      });
      
      showToast('Tạo tài khoản thành công', 'success');
      navigate('/login');
    } catch (err) {
      const error = err as { response?: { data: ApiErrorResponse; status: number } };
      
      if (error.response?.status === 409 && error.response?.data?.code === 'EMAIL_EXISTS') {
        setError('email', {
          type: 'server',
          message: 'Email đã được sử dụng',
        });
      } else if (error.response?.status === 400 || error.response?.status === 422) {
        showToast('Dữ liệu không hợp lệ', 'error');
      } else {
        showToast('Không kết nối được server', 'error');
      }
    }
  };

  return (
    <AuthLayout
      title="Đăng ký"
      subtitle="Tạo tài khoản mới để bắt đầu"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register('email')}
        />
        
        <Input
          label="Mật khẩu"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register('password')}
        />
        
        <Input
          label="Xác nhận mật khẩu"
          type="password"
          autoComplete="new-password"
          error={errors.confirm?.message}
          {...register('confirm')}
        />
        
        <Button
          type="submit"
          className="w-full"
          isLoading={isSubmitting}
        >
          Đăng ký
        </Button>
        
        <p className="text-center text-sm text-gray-600">
          Đã có tài khoản?{' '}
          <Link to="/login" className="text-blue-600 hover:underline">
            Đăng nhập
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
