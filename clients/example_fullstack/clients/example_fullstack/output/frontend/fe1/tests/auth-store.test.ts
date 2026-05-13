import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '../src/stores/auth-store';
import type { User } from '../src/types/auth';

describe('Auth Store', () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: null, user: null });
  });

  it('should initialize with null auth state', () => {
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
  });

  it('should set auth state correctly', () => {
    const mockUser: User = {
      id: 'test-id',
      email: 'test@example.com',
      created_at: '2026-05-13T08:30:00Z',
    };
    const mockToken = 'test-token';

    useAuthStore.getState().setAuth(mockToken, mockUser);

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe(mockToken);
    expect(state.user).toEqual(mockUser);
  });

  it('should logout and clear auth state', () => {
    const mockUser: User = {
      id: 'test-id',
      email: 'test@example.com',
      created_at: '2026-05-13T08:30:00Z',
    };
    const mockToken = 'test-token';

    useAuthStore.getState().setAuth(mockToken, mockUser);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
  });
});
