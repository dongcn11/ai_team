import { AppLayout } from '../components/layout/AppLayout';

export function DashboardPage() {
  return (
    <AppLayout>
      <div className="bg-white rounded-lg border p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-gray-900 mb-4">Dashboard</h2>
        <p className="text-gray-600">
          Chào mừng bạn đến với Task Management!
        </p>
        <p className="text-gray-600 mt-2">
          Tính năng quản lý task sẽ được cập nhật sớm.
        </p>
      </div>
    </AppLayout>
  );
}
