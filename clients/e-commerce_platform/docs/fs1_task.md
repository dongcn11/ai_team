# Fullstack Agent 1 (FS1) - Task Breakdown

## Sprint 1: Authentication & Cart Core

### Feature: Login

#### T-005-1: Design login page UI with email/password fields
- **User Story:** US-005
- **Estimate:** 4 hours
- **Definition of Done:** UI mockups approved

**Tasks:**
- [ ] Create login page layout with TailwindCSS
- [ ] Design email input field with icon
- [ ] Design password input field with show/hide toggle
- [ ] Design "Remember Me" checkbox
- [ ] Design login button with loading state
- [ ] Create responsive design for mobile/desktop
- [ ] Get design approval from team

**Files to Create:**
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/components/auth/LoginForm.tsx`

---

#### T-005-2: Implement login form component with validation
- **User Story:** US-005
- **Estimate:** 6 hours
- **Definition of Done:** Form validates email format and required fields

**Tasks:**
- [ ] Create form state management with React hooks
- [ ] Implement email validation (regex pattern)
- [ ] Implement password required validation
- [ ] Add real-time validation on blur
- [ ] Add submit handler with form data
- [ ] Handle form submission loading state
- [ ] Add accessibility attributes (ARIA labels)

**Files to Create:**
- `frontend/src/components/auth/LoginForm.tsx`
- `frontend/src/validations/authValidation.ts`

---

#### T-005-3: Create authentication API endpoint
- **User Story:** US-005
- **Estimate:** 8 hours
- **Definition of Done:** Endpoint accepts credentials and returns JWT token

**Tasks:**
- [ ] Define User SQLModel schema
- [ ] Create password hashing utility (bcrypt)
- [ ] Implement JWT token generation (access + refresh)
- [ ] Create POST /api/v1/auth/login endpoint
- [ ] Validate email and password
- [ ] Return user data with tokens
- [ ] Add rate limiting for brute force protection

**Files to Create:**
- `backend/models/user.py`
- `backend/api/endpoints/auth.py`
- `backend/core/security.py`
- `backend/core/jwt.py`

---

#### T-005-4: Implement user session management
- **User Story:** US-005
- **Estimate:** 6 hours
- **Definition of Done:** Session persists during browser session

**Tasks:**
- [ ] Create RefreshToken SQLModel schema
- [ ] Implement token storage in database
- [ ] Create token refresh endpoint POST /api/v1/auth/refresh
- [ ] Implement token revocation on logout
- [ ] Add middleware for JWT verification
- [ ] Create dependency for protected routes

**Files to Create:**
- `backend/models/refresh_token.py`
- `backend/api/dependencies.py`
- `backend/api/endpoints/auth.py` (update)

---

#### T-005-5: Add redirect logic to homepage after login
- **User Story:** US-005
- **Estimate:** 2 hours
- **Definition of Done:** User redirected to homepage on successful login

**Tasks:**
- [ ] Create auth context/store for user state
- [ ] Implement login success handler
- [ ] Add redirect to homepage (/) on success
- [ ] Store auth tokens in httpOnly cookies or localStorage
- [ ] Handle redirect from protected pages

**Files to Create:**
- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/hooks/useAuth.ts`

---

#### T-008-1: Design error message components
- **User Story:** US-008
- **Estimate:** 2 hours
- **Definition of Done:** Error UI components created

**Tasks:**
- [ ] Create Alert/Toast component for errors
- [ ] Design inline field error messages
- [ ] Create error state illustrations
- [ ] Style error text with TailwindCSS
- [ ] Add animation for error display

**Files to Create:**
- `frontend/src/components/ui/Alert.tsx`
- `frontend/src/components/ui/ErrorMessage.tsx`

---

#### T-008-2: Implement invalid credentials error handling
- **User Story:** US-008
- **Estimate:** 4 hours
- **Definition of Done:** Clear error shown for wrong email/password

**Tasks:**
- [ ] Handle 401 response from login endpoint
- [ ] Display user-friendly error message
- [ ] Clear form fields on error (optional)
- [ ] Add error to form state
- [ ] Log failed login attempts

**Files to Update:**
- `frontend/src/components/auth/LoginForm.tsx`
- `backend/api/endpoints/auth.py`

---

#### T-008-3: Implement network/server error handling
- **User Story:** US-008
- **Estimate:** 4 hours
- **Definition of Done:** User-friendly messages for server errors

**Tasks:**
- [ ] Handle 500 server errors
- [ ] Handle network/connection errors
- [ ] Handle timeout errors
- [ ] Create error message mapping
- [ ] Add retry option for transient errors
- [ ] Display maintenance messages

**Files to Create:**
- `frontend/src/utils/errorHandler.ts`
- `frontend/src/components/ui/ErrorBoundary.tsx`

---

### Feature: Add to Cart

#### T-001-1: Design cart data model and state management
- **User Story:** US-001
- **Estimate:** 4 hours
- **Definition of Done:** Cart schema defined and state store created

**Tasks:**
- [ ] Define Cart and CartItem SQLModel schemas
- [ ] Create cart state management (Zustand/Context)
- [ ] Implement cart item interface/types
- [ ] Define cart actions (add, update, remove)
- [ ] Create cart selectors for components

**Files to Create:**
- `backend/models/cart.py`
- `frontend/src/stores/cartStore.ts`
- `frontend/src/types/cart.ts`

---

#### T-001-2: Implement "Add to Cart" button component
- **User Story:** US-001
- **Estimate:** 4 hours
- **Definition of Done:** Button displays on product pages

**Tasks:**
- [ ] Create AddToCartButton component
- [ ] Add quantity selector (default: 1)
- [ ] Implement click handler
- [ ] Add loading state during API call
- [ ] Disable button when out of stock
- [ ] Style button with TailwindCSS

**Files to Create:**
- `frontend/src/components/product/AddToCartButton.tsx`
- `frontend/src/components/product/ProductCard.tsx`

---

#### T-001-3: Create cart API endpoint for adding items
- **User Story:** US-001
- **Estimate:** 6 hours
- **Definition of Done:** POST /cart/items endpoint working

**Tasks:**
- [ ] Create POST /api/v1/cart/items endpoint
- [ ] Validate product exists and in stock
- [ ] Check if item already in cart (update quantity)
- [ ] Create new cart item if not exists
- [ ] Return updated cart with totals
- [ ] Add authentication requirement

**Files to Create:**
- `backend/api/endpoints/cart.py`
- `backend/schemas/cart.py`

---

#### T-001-4: Implement cart counter in navigation
- **User Story:** US-001
- **Estimate:** 3 hours
- **Definition of Done:** Cart icon shows item count badge

**Tasks:**
- [ ] Create Navigation component with cart icon
- [ ] Add badge showing total item count
- [ ] Fetch cart count on mount
- [ ] Update badge on cart changes
- [ ] Add link to cart page
- [ ] Make responsive for mobile

**Files to Create:**
- `frontend/src/components/layout/Navigation.tsx`
- `frontend/src/components/layout/CartIcon.tsx`

---

#### T-001-5: Add toast notification for cart additions
- **User Story:** US-001
- **Estimate:** 3 hours
- **Definition of Done:** Confirmation toast appears on add

**Tasks:**
- [ ] Create toast notification system
- [ ] Design success toast for cart addition
- [ ] Trigger toast on successful add
- [ ] Include product name and quantity
- [ ] Add "View Cart" action button
- [ ] Auto-dismiss after 3 seconds

**Files to Create:**
- `frontend/src/components/ui/Toast.tsx`
- `frontend/src/hooks/useToast.ts`

---

#### T-002-1: Design cart page layout
- **User Story:** US-002
- **Estimate:** 4 hours
- **Definition of Done:** Cart page UI mockup approved

**Tasks:**
- [ ] Design cart page structure
- [ ] Create cart items list layout
- [ ] Design order summary sidebar
- [ ] Design empty cart state
- [ ] Create checkout button
- [ ] Make responsive design

**Files to Create:**
- `frontend/src/pages/CartPage.tsx`

---

#### T-002-2: Implement cart page with item listing
- **User Story:** US-002
- **Estimate:** 6 hours
- **Definition of Done:** All cart items displayed with details

**Tasks:**
- [ ] Fetch cart items on page load
- [ ] Display product image, name, price
- [ ] Show quantity for each item
- [ ] Display subtotal per item
- [ ] Handle empty cart state
- [ ] Add loading skeleton

**Files to Create:**
- `frontend/src/pages/CartPage.tsx`
- `frontend/src/components/cart/CartItem.tsx`
- `frontend/src/components/cart/CartSummary.tsx`

---

#### T-002-3: Create GET /cart API endpoint
- **User Story:** US-002
- **Estimate:** 4 hours
- **Definition of Done:** Returns cart items with prices and quantities

**Tasks:**
- [ ] Create GET /api/v1/cart endpoint
- [ ] Fetch cart with all items
- [ ] Join product data (name, price, image)
- [ ] Calculate subtotals and total
- [ ] Return formatted cart response
- [ ] Add authentication requirement

**Files to Create:**
- `backend/api/endpoints/cart.py` (update)
- `backend/schemas/cart.py` (update)

---

#### T-002-4: Implement total price calculation
- **User Story:** US-002
- **Estimate:** 3 hours
- **Definition of Done:** Total calculated correctly including all items

**Tasks:**
- [ ] Calculate subtotal for each item (price × quantity)
- [ ] Sum all subtotals for cart total
- [ ] Display total in cart summary
- [ ] Handle decimal precision (2 decimal places)
- [ ] Format currency display

**Files to Update:**
- `frontend/src/components/cart/CartSummary.tsx`
- `backend/api/endpoints/cart.py`

---

## Sprint 1 Summary for FS1

| Feature | Tasks | Total Hours |
|---------|-------|-------------|
| Login | 8 tasks | 36 hours |
| Add to Cart | 9 tasks | 37 hours |
| **Total** | **17 tasks** | **73 hours** |

---

## Sprint 3: Cart Enhancements & Login Enhancements

### Feature: Cart Enhancements

#### T-004-1: Design remove item UI (trash icon/button)
- **User Story:** US-004
- **Estimate:** 2 hours
- **Definition of Done:** Remove button design approved

**Tasks:**
- [ ] Design trash/remove icon button
- [ ] Add hover state and confirmation
- [ ] Position button on cart item
- [ ] Style with TailwindCSS
- [ ] Ensure mobile-friendly size

**Files to Update:**
- `frontend/src/components/cart/CartItem.tsx`

---

#### T-004-2: Implement remove item functionality
- **User Story:** US-004
- **Estimate:** 4 hours
- **Definition of Done:** Click removes item from cart

**Tasks:**
- [ ] Add click handler to remove button
- [ ] Call DELETE API endpoint
- [ ] Update cart state on success
- [ ] Show loading state during removal
- [ ] Handle removal error
- [ ] Show empty cart if last item removed

**Files to Update:**
- `frontend/src/components/cart/CartItem.tsx`
- `frontend/src/stores/cartStore.ts`

---

#### T-004-3: Create DELETE /cart/items/:id endpoint
- **User Story:** US-004
- **Estimate:** 4 hours
- **Definition of Done:** Endpoint removes item and returns updated cart

**Tasks:**
- [ ] Create DELETE /api/v1/cart/items/:id endpoint
- [ ] Verify cart item ownership
- [ ] Remove item from database
- [ ] Return updated cart totals
- [ ] Handle not found error

**Files to Update:**
- `backend/api/endpoints/cart.py`

---

#### T-004-4: Add undo toast for accidental removals
- **User Story:** US-004
- **Estimate:** 3 hours
- **Definition of Done:** Temporary undo option appears after removal

**Tasks:**
- [ ] Create undo toast component
- [ ] Store removed item temporarily
- [ ] Add undo action to restore item
- [ ] Auto-dismiss after 5 seconds
- [ ] Handle undo API call

**Files to Create:**
- `frontend/src/components/ui/UndoToast.tsx`

---

#### T-003-1: Design quantity selector component
- **UserStory:** US-003
- **Estimate:** 3 hours
- **Definition of Done:** +/- buttons or dropdown design approved

**Tasks:**
- [ ] Design +/- button component
- [ ] Add input field for direct quantity entry
- [ ] Style with TailwindCSS
- [ ] Add disabled state for min/max
- [ ] Ensure mobile-friendly

**Files to Create:**
- `frontend/src/components/ui/QuantitySelector.tsx`

---

#### T-003-2: Implement quantity update UI
- **User Story:** US-003
- **Estimate:** 4 hours
- **Definition of Done:** User can change quantity in cart

**Tasks:**
- [ ] Integrate QuantitySelector in CartItem
- [ ] Handle increment/decrement
- [ ] Debounce rapid changes
- [ ] Show loading state during update
- [ ] Prevent quantity > stock

**Files to Update:**
- `frontend/src/components/cart/CartItem.tsx`

---

#### T-003-3: Create PUT /cart/items/:id endpoint
- **User Story:** US-003
- **Estimate:** 4 hours
- **Definition of Done:** Endpoint updates quantity

**Tasks:**
- [ ] Create PUT /api/v1/cart/items/:id endpoint
- [ ] Validate quantity (min: 1, max: stock)
- [ ] Update quantity in database
- [ ] Return updated cart item and totals
- [ ] Handle not found and validation errors

**Files to Update:**
- `backend/api/endpoints/cart.py`

---

#### T-003-4: Implement real-time total recalculation
- **User Story:** US-003
- **Estimate:** 3 hours
- **Definition of Done:** Total updates when quantity changes

**Tasks:**
- [ ] Update cart totals on quantity change
- [ ] Recalculate in state management
- [ ] Update UI with new totals
- [ ] Ensure currency formatting

**Files to Update:**
- `frontend/src/stores/cartStore.ts`
- `frontend/src/components/cart/CartSummary.tsx`

---

### Feature: Login Enhancements (Sprint 3)

#### T-006-1 to T-006-6: Password Reset Flow
- **User Story:** US-006
- **Total Estimate:** 24 hours

#### T-007-1 to T-007-3: Remember Me Feature
- **User Story:** US-007
- **Total Estimate:** 14 hours

---

## Sprint 3 Summary for FS1

| Feature | Tasks | Total Hours |
|---------|-------|-------------|
| Cart Enhancements | 8 tasks | 27 hours |
| Login Enhancements | 9 tasks | 34 hours |
| **Total** | **17 tasks** | **61 hours** |

---

## Files Structure

### Backend
```
backend/
├── models/
│   ├── __init__.py
│   ├── user.py
│   ├── refresh_token.py
│   ├── password_reset_token.py
│   ├── product.py
│   ├── cart.py
│   ├── order.py
│   └── payment.py
├── schemas/
│   ├── __init__.py
│   ├── auth.py
│   ├── cart.py
│   ├── order.py
│   └── payment.py
├── api/
│   ├── __init__.py
│   ├── endpoints/
│   │   ├── auth.py
│   │   ├── cart.py
│   │   ├── orders.py
│   │   └── payments.py
│   └── dependencies.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── security.py
│   └── jwt.py
├── database.py
└── main.py
```

### Frontend
```
frontend/
├── src/
│   ├── components/
│   │   ├── auth/
│   │   │   ├── LoginForm.tsx
│   │   │   └── ForgotPasswordForm.tsx
│   │   ├── cart/
│   │   │   ├── CartItem.tsx
│   │   │   ├── CartSummary.tsx
│   │   │   └── CartPage.tsx
│   │   ├── product/
│   │   │   ├── ProductCard.tsx
│   │   │   └── AddToCartButton.tsx
│   │   ├── layout/
│   │   │   ├── Navigation.tsx
│   │   │   └── CartIcon.tsx
│   │   └── ui/
│   │       ├── Alert.tsx
│   │       ├── ErrorMessage.tsx
│   │       ├── Toast.tsx
│   │       ├── QuantitySelector.tsx
│   │       └── ErrorBoundary.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── CartPage.tsx
│   │   └── HomePage.tsx
│   ├── contexts/
│   │   └── AuthContext.tsx
│   ├── stores/
│   │   └── cartStore.ts
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   └── useToast.ts
│   ├── validations/
│   │   └── authValidation.ts
│   ├── utils/
│   │   ├── errorHandler.ts
│   │   └── api.ts
│   ├── types/
│   │   ├── cart.ts
│   │   ├── auth.ts
│   │   └── user.ts
│   ├── App.tsx
│   └── main.tsx
└── package.json
```

---

## API Endpoints for FS1

### Sprint 1
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/auth/login | User login |
| POST | /api/v1/auth/refresh | Refresh token |
| GET | /api/v1/cart | Get cart items |
| POST | /api/v1/cart/items | Add item to cart |

### Sprint 3 (Cart Enhancements)
| Method | Endpoint | Description |
|--------|----------|-------------|
| PUT | /api/v1/cart/items/:id | Update item quantity |
| DELETE | /api/v1/cart/items/:id | Remove item from cart |

### Sprint 3 (Login Enhancements)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/auth/forgot-password | Request password reset |
| POST | /api/v1/auth/reset-password | Reset password with token |
