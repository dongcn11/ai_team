export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export interface RegisterResponse {
  id: string;
  email: string;
  created_at: string;
}
