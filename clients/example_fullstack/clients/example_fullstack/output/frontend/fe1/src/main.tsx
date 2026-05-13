import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { ToastProvider } from './components/ui/Toast';
import { router } from './routes';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </ErrorBoundary>
  </StrictMode>,
);
