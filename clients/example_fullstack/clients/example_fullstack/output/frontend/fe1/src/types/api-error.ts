export interface ApiError {
  message: string;
  code?: string;
  fieldErrors?: Record<string, string>;
}

export interface ApiErrorResponse {
  detail: string;
  code?: string;
  field_errors?: Record<string, string>;
}
