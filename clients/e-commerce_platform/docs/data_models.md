# Data Models - E-Commerce Platform

## Database Schema

### User
```python
class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: str = Field(default_factory=lambda: f"usr_{uuid4()}", primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    name: str
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
    
    # Relationships
    cart: "Cart" = Relationship(back_populates="user", sa_relationship_kwargs={"uselist": False})
    orders: List["Order"] = Relationship(back_populates="user")
    payment_methods: List["PaymentMethod"] = Relationship(back_populates="user")
    refresh_tokens: List["RefreshToken"] = Relationship(back_populates="user")
    password_reset_tokens: List["PasswordResetToken"] = Relationship(back_populates="user")
```

---

### RefreshToken
```python
class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    
    id: str = Field(default_factory=lambda: f"rt_{uuid4()}", primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    token: str = Field(unique=True, index=True)
    expires_at: datetime
    is_revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: "User" = Relationship(back_populates="refresh_tokens")
```

---

### PasswordResetToken
```python
class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"
    
    id: str = Field(default_factory=lambda: f"prt_{uuid4()}", primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    token: str = Field(unique=True, index=True)
    expires_at: datetime
    is_used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: "User" = Relationship(back_populates="password_reset_tokens")
```

---

### Product
```python
class Product(SQLModel, table=True):
    __tablename__ = "products"
    
    id: str = Field(default_factory=lambda: f"prod_{uuid4()}", primary_key=True)
    name: str
    description: str
    price: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    stock_quantity: int
    image_url: str | None
    category: str | None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
    
    # Relationships
    cart_items: List["CartItem"] = Relationship(back_populates="product")
    order_items: List["OrderItem"] = Relationship(back_populates="product")
```

---

### Cart
```python
class Cart(SQLModel, table=True):
    __tablename__ = "carts"
    
    id: str = Field(default_factory=lambda: f"cart_{uuid4()}", primary_key=True)
    user_id: str = Field(foreign_key="users.id", unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
    
    # Relationships
    user: "User" = Relationship(back_populates="cart")
    items: List["CartItem"] = Relationship(back_populates="cart")
```

---

### CartItem
```python
class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"
    
    id: str = Field(default_factory=lambda: f"ci_{uuid4()}", primary_key=True)
    cart_id: str = Field(foreign_key="carts.id", index=True)
    product_id: str = Field(foreign_key="products.id", index=True)
    quantity: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
    
    # Relationships
    cart: "Cart" = Relationship(back_populates="items")
    product: "Product" = Relationship(back_populates="cart_items")
```

---

### Order
```python
class Order(SQLModel, table=True):
    __tablename__ = "orders"
    
    id: str = Field(default_factory=lambda: f"ord_{uuid4()}", primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    payment_id: str | None = Field(foreign_key="payments.id", unique=True)
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    total_amount: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    shipping_address_street: str
    shipping_address_city: str
    shipping_address_state: str
    shipping_address_zip: str
    shipping_address_country: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
    
    # Relationships
    user: "User" = Relationship(back_populates="orders")
    payment: "Payment" = Relationship(back_populates="order")
    items: List["OrderItem"] = Relationship(back_populates="order")
```

---

### OrderItem
```python
class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"
    
    id: str = Field(default_factory=lambda: f"oi_{uuid4()}", primary_key=True)
    order_id: str = Field(foreign_key="orders.id", index=True)
    product_id: str = Field(foreign_key="products.id", index=True)
    quantity: int
    unit_price: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    subtotal: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    order: "Order" = Relationship(back_populates="items")
    product: "Product" = Relationship(back_populates="order_items")
```

---

### Payment
```python
class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    
    id: str = Field(default_factory=lambda: f"pay_{uuid4()}", primary_key=True)
    order_id: str | None = Field(foreign_key="orders.id", unique=True, index=True, nullable=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    amount: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    currency: str = Field(default="USD")
    status: PaymentStatus
    payment_method_type: PaymentMethodType
    payment_gateway_id: str | None  # ID from payment gateway (Stripe, etc.)
    card_brand: str | None
    card_last_four: str | None
    cardholder_name: str | None
    billing_address_street: str | None
    billing_address_city: str | None
    billing_address_state: str | None
    billing_address_zip: str | None
    billing_address_country: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    order: "Order" = Relationship(back_populates="payment")
    user: "User" = Relationship()
```

---

### PaymentMethod
```python
class PaymentMethod(SQLModel, table=True):
    __tablename__ = "payment_methods"
    
    id: str = Field(default_factory=lambda: f"pm_{uuid4()}", primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    payment_gateway_customer_id: str  # Stripe customer ID, etc.
    payment_gateway_payment_method_id: str  # Stripe payment method ID, etc.
    type: PaymentMethodType = Field(default=PaymentMethodType.CARD)
    card_brand: str | None
    card_last_four: str | None
    card_expiry_month: int | None
    card_expiry_year: int | None
    cardholder_name: str | None
    is_default: bool = Field(default=False)
    billing_address_street: str | None
    billing_address_city: str | None
    billing_address_state: str | None
    billing_address_zip: str | None
    billing_address_country: str | None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: "User" = Relationship(back_populates="payment_methods")
```

---

## Enum Types

### OrderStatus
```python
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
```

---

### PaymentStatus
```python
class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
```

---

### PaymentMethodType
```python
class PaymentMethodType(str, Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    DIGITAL_WALLET = "digital_wallet"
```

---

## Indexes

```sql
-- User indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_is_active ON users(is_active);

-- Refresh token indexes
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token ON refresh_tokens(token);
CREATE INDEX idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);

-- Password reset token indexes
CREATE INDEX idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX idx_password_reset_tokens_token ON password_reset_tokens(token);

-- Product indexes
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_is_active ON products(is_active);
CREATE INDEX idx_products_price ON products(price);

-- Cart indexes
CREATE INDEX idx_carts_user_id ON carts(user_id);

-- Cart item indexes
CREATE INDEX idx_cart_items_cart_id ON cart_items(cart_id);
CREATE INDEX idx_cart_items_product_id ON cart_items(product_id);

-- Order indexes
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);

-- Order item indexes
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);

-- Payment indexes
CREATE INDEX idx_payments_user_id ON payments(user_id);
CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_payments_created_at ON payments(created_at);

-- Payment method indexes
CREATE INDEX idx_payment_methods_user_id ON payment_methods(user_id);
CREATE INDEX idx_payment_methods_is_default ON payment_methods(is_default);
```

---

## ERD (Entity Relationship Diagram)

```
┌─────────────────┐       ┌─────────────────┐
│      User       │       │     Product     │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ email           │       │ name            │
│ password_hash   │       │ description     │
│ name            │       │ price           │
│ is_active       │       │ stock_quantity  │
│ created_at      │       │ image_url       │
│ updated_at      │       │ category        │
└────────┬────────┘       │ is_active       │
         │                └────────┬────────┘
         │                         │
         │ 1                       │ 1
         │ │                       │ │
         │ │                       │ │
    ┌────┴────┐               ┌────┴────┐
    │    1    │               │    *    │
    ▼         │               ▼         │
┌─────────────────┐       ┌─────────────────┐
│      Cart       │       │   CartItem      │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │◄──────│ id (PK)         │
│ user_id (FK)    │       │ cart_id (FK)    │
│ created_at      │       │ product_id (FK) │
│ updated_at      │       │ quantity        │
└─────────────────┘       │ created_at      │
                          │ updated_at      │
                          └─────────────────┘
         │
         │ 1
         │ │
    ┌────┴────┐
    │    *    │
    ▼
┌─────────────────┐       ┌─────────────────┐
│     Order       │       │    Payment      │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ user_id (FK)    │       │ order_id (FK)   │
│ payment_id (FK) │──────►│ user_id (FK)    │
│ status          │       │ amount          │
│ total_amount    │       │ currency        │
│ shipping_*      │       │ status          │
│ created_at      │       │ payment_method  │
│ updated_at      │       │ card_*          │
└────────┬────────┘       │ billing_*       │
         │                │ created_at      │
         │                └─────────────────┘
         │ 1
         │ │
    ┌────┴────┐
    │    *    │
    ▼
┌─────────────────┐
│   OrderItem     │
├─────────────────┤
│ id (PK)         │
│ order_id (FK)   │
│ product_id (FK) │
│ quantity        │
│ unit_price      │
│ subtotal        │
│ created_at      │
└─────────────────┘

┌─────────────────┐       ┌─────────────────────┐
│      User       │       │   PaymentMethod     │
└────────┬────────┘       ├─────────────────────┤
         │ 1              │ id (PK)             │
         │ │              │ user_id (FK)        │
    ┌────┴────┐           │ gateway_customer_id │
    │    *    │           │ gateway_method_id   │
    ▼         │           │ type                │
┌─────────────────┐       │ card_*              │
│  RefreshToken   │       │ is_default          │
├─────────────────┤       │ billing_*           │
│ id (PK)         │       │ created_at          │
│ user_id (FK)    │       └─────────────────────┘
│ token           │
│ expires_at      │
│ is_revoked      │       ┌─────────────────────┐
│ created_at      │       │ PasswordResetToken  │
└─────────────────┘       ├─────────────────────┤
                          │ id (PK)             │
                          │ user_id (FK)        │
                          │ token               │
                          │ expires_at          │
                          │ is_used             │
                          │ created_at          │
                          └─────────────────────┘
```
