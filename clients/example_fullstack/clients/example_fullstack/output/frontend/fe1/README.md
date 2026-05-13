# Frontend FE1 - Authentication & Routing

## Setup

### Installation

```bash
npm install
```

### Environment Variables

Copy `.env.example` to `.env` (or `.env.local`):

```bash
cp .env.example .env.local
```

Default configuration:
```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### Development

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### Testing

```bash
npm run test
```

### Build

```bash
npm run build
```

## Features

### Authentication
- **Register** (`/register`): User registration with email validation and password strength check
- **Login** (`/login`): User authentication with JWT token
- **Logout**: Clear auth state and redirect to login
- **Protected Routes**: Automatic redirect to login for unauthenticated users

### Tech Stack
- React 18 + TypeScript
- Vite
- TailwindCSS
- React Router v6
- axios (API client)
- zustand (state management)
- react-hook-form + zod (form validation)
- vitest + @testing-library/react (testing)

## Project Structure

```
src/
├── main.tsx                  # App entry point
├── App.tsx                   # App component
├── lib/
│   ├── api.ts                # Axios instance + interceptors
│   └── env.ts                # Environment config
├── stores/
│   └── auth-store.ts         # Zustand auth state
├── types/
│   ├── auth.ts               # Auth types
│   └── api-error.ts          # API error types
├── components/
│   ├── ui/                   # Base UI components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Label.tsx
│   │   ├── Toast.tsx
│   │   └── ErrorBoundary.tsx
│   └── layout/               # Layout components
│       ├── AuthLayout.tsx
│       └── AppLayout.tsx
├── routes/
│   ├── RegisterPage.tsx
│   ├── LoginPage.tsx
│   ├── DashboardPage.tsx
│   ├── ProtectedRoute.tsx
│   └── index.tsx
├── hooks/
│   └── useAuth.ts
└── styles/
    └── index.css
```

## User Stories

### US-001: User Registration
- Email validation (RFC 5322)
- Password validation (min 8 chars, letters + numbers)
- Password confirmation
- Handle EMAIL_EXISTS error (409)

### US-002: User Login
- Email + password authentication
- JWT token storage (localStorage)
- Auto-redirect to dashboard on success
- Handle 401 (invalid credentials) and 429 (rate limit)

### US-003: User Logout
- Logout button in topbar
- Clear auth state
- Redirect to login page
- Best-effort API call to invalidate token

## Security Notes

⚠️ **Current Implementation**: JWT tokens are stored in localStorage for MVP simplicity.

**Trade-offs**:
- Pros: Simple to implement, works with current backend
- Cons: Vulnerable to XSS attacks

**Production Recommendation**: Use httpOnly cookies for token storage (requires backend changes).

## Definition of Done

- [x] Project setup with Vite + React + TypeScript
- [x] TailwindCSS configured
- [x] Axios client with interceptors
- [x] Auth store with persist
- [x] Register page with validation
- [x] Login page with validation
- [x] Protected routes
- [x] Logout functionality
- [x] Error boundary
- [x] Toast notifications
- [x] Basic tests
