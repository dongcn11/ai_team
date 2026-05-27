# Acceptance Criteria - E-Commerce Platform

## Feature: Add to Cart

### US-001: Add products to cart
- **Given** I am browsing a product page
- **When** I click the "Add to Cart" button
- **Then** the product is added to my cart
- **And** I see a confirmation message
- **And** the cart icon shows the updated item count

### US-002: View cart items
- **Given** I have items in my cart
- **When** I navigate to the cart page
- **Then** I see all items with their names, prices, and quantities
- **And** I see the total price calculated correctly

### US-003: Update cart quantities
- **Given** I have items in my cart
- **When** I change the quantity of an item
- **Then** the item quantity is updated
- **And** the total price is recalculated

### US-004: Remove items from cart
- **Given** I have items in my cart
- **When** I click the remove button on an item
- **Then** the item is removed from the cart
- **And** the total price is updated

## Feature: Login

### US-005: Login with email and password
- **Given** I have a registered account
- **When** I enter my email and password on the login page
- **And** I click the "Login" button
- **Then** I am redirected to the homepage
- **And** I see my account information displayed

### US-006: Reset password
- **Given** I have a registered account but forgot my password
- **When** I click "Forgot Password" and enter my email
- **Then** I receive a password reset link via email
- **And** I can set a new password using the link

### US-007: Stay logged in
- **Given** I checked "Remember Me" during login
- **When** I close and reopen the browser
- **Then** I remain logged in to my account

### US-008: Login error messages
- **Given** I enter invalid login credentials
- **When** I attempt to log in
- **Then** I see a clear error message indicating the issue
- **And** I am not redirected to the homepage

## Feature: Payment

### US-009: Pay with credit/debit card
- **Given** I have items in my cart and am at checkout
- **When** I enter valid credit/debit card information
- **And** I click "Pay Now"
- **Then** the payment is processed securely
- **And** I am redirected to the order confirmation page

### US-010: Save payment methods
- **Given** I am completing a payment
- **When** I check "Save this card for future use"
- **Then** my card is securely saved to my profile
- **And** I can select it for future checkouts

### US-011: Payment confirmation
- **Given** I have completed a payment
- **When** the payment is successful
- **Then** I see an order confirmation page
- **And** I receive a confirmation email with order details

### US-012: View payment history
- **Given** I am logged into my account
- **When** I navigate to my payment history
- **Then** I see a list of all my past transactions
- **And** I can view details for each transaction

### US-013: Secure payment processing
- **Given** I am entering payment information
- **When** I submit my payment
- **Then** my data is encrypted using industry standards
- **And** no sensitive data is stored in plain text
- **And** the system is PCI-DSS compliant
