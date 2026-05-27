# API Contract - E-Commerce Platform

## Base URL
```
/api/v1
```

## Authentication

### POST /auth/login
**Description:** Authenticate user with email and password

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securePassword123",
  "rememberMe": false
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "usr_123456",
    "email": "user@example.com",
    "name": "John Doe"
  }
}
```

**Response (401 Unauthorized):**
```json
{
  "error": "invalid_credentials",
  "message": "Invalid email or password"
}
```

---

### POST /auth/refresh
**Description:** Refresh access token using refresh token

**Request Body:**
```json
{
  "refresh_token": "dGhpcyBpcyBhIHJlZnJl..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "bmV3IHJlZnJlc2ggdG9r...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

### POST /auth/forgot-password
**Description:** Request password reset email

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 OK):**
```json
{
  "message": "Password reset email sent"
}
```

---

### POST /auth/reset-password
**Description:** Reset password with token

**Request Body:**
```json
{
  "token": "reset_token_abc123",
  "new_password": "newSecurePassword456"
}
```

**Response (200 OK):**
```json
{
  "message": "Password reset successful"
}
```

---

## Cart

### GET /cart
**Description:** Get current user's cart items

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "cart_789",
  "user_id": "usr_123456",
  "items": [
    {
      "id": "ci_001",
      "product_id": "prod_555",
      "product_name": "Wireless Headphones",
      "product_image": "https://...",
      "price": 79.99,
      "quantity": 2,
      "subtotal": 159.98
    }
  ],
  "total_items": 2,
  "total_price": 159.98,
  "updated_at": "2026-04-29T10:30:00Z"
}
```

---

### POST /cart/items
**Description:** Add item to cart

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "product_id": "prod_555",
  "quantity": 1
}
```

**Response (201 Created):**
```json
{
  "id": "ci_001",
  "product_id": "prod_555",
  "product_name": "Wireless Headphones",
  "price": 79.99,
  "quantity": 1,
  "subtotal": 79.99,
  "cart_total_items": 1,
  "cart_total_price": 79.99
}
```

**Response (400 Bad Request):**
```json
{
  "error": "invalid_product",
  "message": "Product does not exist or is out of stock"
}
```

---

### PUT /cart/items/:id
**Description:** Update item quantity in cart

**Headers:**
```
Authorization: Bearer <access_token>
```

**Path Parameters:**
- `id`: Cart item ID (e.g., `ci_001`)

**Request Body:**
```json
{
  "quantity": 3
}
```

**Response (200 OK):**
```json
{
  "id": "ci_001",
  "product_id": "prod_555",
  "product_name": "Wireless Headphones",
  "price": 79.99,
  "quantity": 3,
  "subtotal": 239.97,
  "cart_total_items": 3,
  "cart_total_price": 239.97
}
```

**Response (404 Not Found):**
```json
{
  "error": "cart_item_not_found",
  "message": "Cart item not found"
}
```

---

### DELETE /cart/items/:id
**Description:** Remove item from cart

**Headers:**
```
Authorization: Bearer <access_token>
```

**Path Parameters:**
- `id`: Cart item ID (e.g., `ci_001`)

**Response (200 OK):**
```json
{
  "message": "Item removed from cart",
  "cart_total_items": 0,
  "cart_total_price": 0
}
```

---

### DELETE /cart
**Description:** Clear entire cart

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "message": "Cart cleared"
}
```

---

## Payment

### POST /payments/checkout
**Description:** Process payment for cart items

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "card_number": "4242424242424242",
  "expiry_month": 12,
  "expiry_year": 2027,
  "cvv": "123",
  "cardholder_name": "John Doe",
  "save_card": false
}
```

**Response (200 OK):**
```json
{
  "id": "pay_abc123",
  "order_id": "ord_xyz789",
  "amount": 159.98,
  "currency": "USD",
  "status": "succeeded",
  "payment_method": "card",
  "last_four": "4242",
  "created_at": "2026-04-29T11:00:00Z"
}
```

**Response (402 Payment Required):**
```json
{
  "error": "payment_failed",
  "message": "Your card was declined",
  "decline_code": "insufficient_funds"
}
```

---

### GET /payments/history
**Description:** Get user's payment history

**Headers:**
```
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 10)

**Response (200 OK):**
```json
{
  "payments": [
    {
      "id": "pay_abc123",
      "order_id": "ord_xyz789",
      "amount": 159.98,
      "currency": "USD",
      "status": "succeeded",
      "payment_method": "card",
      "last_four": "4242",
      "created_at": "2026-04-29T11:00:00Z",
      "items_count": 2
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 10,
    "total_pages": 1,
    "total_items": 1
  }
}
```

---

### GET /payments/:id
**Description:** Get payment transaction details

**Headers:**
```
Authorization: Bearer <access_token>
```

**Path Parameters:**
- `id`: Payment ID (e.g., `pay_abc123`)

**Response (200 OK):**
```json
{
  "id": "pay_abc123",
  "order_id": "ord_xyz789",
  "amount": 159.98,
  "currency": "USD",
  "status": "succeeded",
  "payment_method": "card",
  "card_brand": "visa",
  "last_four": "4242",
  "cardholder_name": "John Doe",
  "billing_address": {
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "zip": "10001",
    "country": "US"
  },
  "items": [
    {
      "product_id": "prod_555",
      "product_name": "Wireless Headphones",
      "quantity": 2,
      "price": 79.99,
      "subtotal": 159.98
    }
  ],
  "created_at": "2026-04-29T11:00:00Z"
}
```

---

## Payment Methods

### GET /payment-methods
**Description:** Get user's saved payment methods

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "payment_methods": [
    {
      "id": "pm_card_001",
      "type": "card",
      "card_brand": "visa",
      "last_four": "4242",
      "expiry_month": 12,
      "expiry_year": 2027,
      "cardholder_name": "John Doe",
      "is_default": true,
      "created_at": "2026-04-15T09:00:00Z"
    }
  ]
}
```

---

### POST /payment-methods
**Description:** Save a new payment method

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "card_number": "4242424242424242",
  "expiry_month": 12,
  "expiry_year": 2027,
  "cvv": "123",
  "cardholder_name": "John Doe",
  "is_default": true
}
```

**Response (201 Created):**
```json
{
  "id": "pm_card_002",
  "type": "card",
  "card_brand": "visa",
  "last_four": "4242",
  "expiry_month": 12,
  "expiry_year": 2027,
  "cardholder_name": "John Doe",
  "is_default": true,
  "created_at": "2026-04-29T12:00:00Z"
}
```

---

### DELETE /payment-methods/:id
**Description:** Delete a saved payment method

**Headers:**
```
Authorization: Bearer <access_token>
```

**Path Parameters:**
- `id`: Payment method ID (e.g., `pm_card_001`)

**Response (200 OK):**
```json
{
  "message": "Payment method deleted"
}
```

---

## Error Responses

### Standard Error Format
```json
{
  "error": "error_code",
  "message": "Human readable message",
  "details": {}
}
```

### Common Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `validation_error` | Invalid request body |
| 400 | `invalid_product` | Product doesn't exist or out of stock |
| 401 | `unauthorized` | Missing or invalid token |
| 401 | `token_expired` | Access token has expired |
| 401 | `invalid_credentials` | Wrong email/password |
| 402 | `payment_failed` | Payment was declined |
| 403 | `forbidden` | User doesn't have permission |
| 404 | `not_found` | Resource doesn't exist |
| 404 | `cart_item_not_found` | Cart item not found |
| 409 | `conflict` | Resource conflict (e.g., duplicate) |
| 500 | `internal_error` | Server error |
