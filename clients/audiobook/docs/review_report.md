# Code Review Report

## Tổng quan
Code được review thuộc FS1 Agent (frontend) với 4 file JavaScript implement các tính năng khởi tạo project audiobook. Code có cấu trúc rõ ràng, tuân thủ phần lớn API contract, tuy nhiên còn một số vấn đề về error handling, security và UX cần cải thiện.

---

## FE Agent 1 (fullstack/fs1/) — needs-fix

### ✅ Điểm tốt

1. **Code organization**
   - Mỗi class đảm nhận một responsibility rõ ràng (DashboardPage, ProjectCreatePage, ProjectSettings, ProjectValidator)
   - Tên class và method dễ hiểu, theo đúng convention `camelCase`
   - Có tách riêng validator class để reuse

2. **API Contract compliance**
   - Đúng base URL `/api/v1`
   - Đúng HTTP methods (GET, POST, PUT)
   - Request/response schema khớp với contract
   - Authentication header đúng format `Bearer {token}`

3. **Input validation**
   - ProjectValidator validate đầy đủ các field theo contract
   - Check độ dài name (255 chars), description (1000 chars)
   - Validate ISO 639-1 language code format
   - Validate audio_format enum values

4. **Error display**
   - Có hiển thị lỗi từ server response
   - Clear errors trước khi submit mới

### ⚠️ Cần sửa

#### [severity: high] Security - Token storage
**Vấn đề:** Token được lưu trong `localStorage` và expose qua JavaScript
```javascript
localStorage.getItem('token')
```
**Rủi ro:** XSS attack có thể đánh cắp token
**Gợi ý fix:** Dùng httpOnly cookie thay vì localStorage, hoặc ít nhất implement token rotation và short expiry

---

#### [severity: high] Error Handling - Missing HTTP status check
**Vấn đề:** Code không check HTTP status code trước khi parse JSON
```javascript
const response = await fetch('/api/v1/projects', {...});
const data = await response.json(); // Có thể fail nếu response không phải JSON
```
**Rủi ro:** Nếu server trả về 401/403/500 với HTML error page, `response.json()` sẽ throw exception
**Gợi ý fix:**
```javascript
if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new ApiError(error.message, response.status);
}
```

---

#### [severity: high] Error Handling - No network error handling for voices
**Vấn đề:** Các function `loadVoices()` catch error nhưng chỉ log console, không inform user
```javascript
catch (error) {
    console.error('Error loading voices:', error);
}
```
**Rủi ro:** User không biết voice list failed to load, có thể submit form với voice không hợp lệ
**Gợi ý fix:** Hiển thị error message trong voice select dropdown hoặc disable submit button

---

#### [severity: medium] Security - XSS vulnerability despite escapeHtml
**Vấn đề:** `escapeHtml()` được dùng nhưng chỉ sau khi đã render template string
```javascript
this.projectsContainer.innerHTML = this.projects.map(project => `
    <h3>${this.escapeHtml(project.name)}</h3>
`).join('');
```
**Rủi ro:** Nếu project.name chứa script tag, nó đã được inject vào template string trước khi escape
**Gợi ý fix:** Escape data TRƯỚC khi insert vào template, hoặc dùng `textContent` thay vì `innerHTML`

---

#### [severity: medium] Error Handling - Generic error messages
**Vấn đề:** Error messages quá chung chung, không helpful cho user
```javascript
this.showNotification('Failed to save settings', 'error');
alert('Failed to load projects');
```
**Gợi ý fix:** Phân biệt các loại lỗi:
- 401 → "Phiên đăng nhập hết hạn, vui lòng đăng nhập lại"
- 403 → "Bạn không có quyền truy cập project này"
- 404 → "Project không tồn tại"
- 500 → "Lỗi server, vui lòng thử lại sau"

---

#### [severity: medium] UX - No loading state for voices dropdown
**Vấn đề:** Khi đang fetch voices, dropdown không hiển thị loading state
**Gợi ý fix:** Disable dropdown và hiển thị "Loading..." option trong khi fetch

---

#### [severity: medium] Code Quality - Duplicate code
**Vấn đề:** `escapeHtml()` method được duplicate trong cả 4 class
**Gợi ý fix:** Tạo utility module chung `utils/security.js`

---

#### [severity: low] Code Quality - Magic strings
**Vấn đề:** API endpoints hardcode trong nhiều file
```javascript
fetch('/api/v1/projects')
fetch(`/api/v1/projects/${this.projectId}`)
```
**Gợi ý fix:** Tạo constants file hoặc API service layer
```javascript
// config/api.js
export const API_ENDPOINTS = {
    PROJECTS: '/api/v1/projects',
    VOICES: '/api/v1/voices',
    PROJECT_SETTINGS: (id) => `/api/v1/projects/${id}/settings`
};
```

---

#### [severity: low] Code Quality - Missing JSDoc
**Vấn đề:** Không có docstring cho public methods
**Gợi ý fix:**
```javascript
/**
 * Load danh sách voices từ API
 * @param {string} language - ISO 639-1 language code filter
 * @returns {Promise<void>}
 */
async loadVoices(language) { ... }
```

---

#### [severity: low] Error Handling - No retry mechanism
**Vấn đề:** Network errors không có retry logic
**Gợi ý fix:** Implement exponential backoff cho failed requests

---

#### [severity: low] UX - Alert instead of toast notification
**Vấn đề:** Dùng `alert()` block UI và không professional
```javascript
alert(`${type.toUpperCase()}: ${message}`);
```
**Gợi ý fix:** Dùng toast notification component không block UI

---

#### [severity: low] Code Quality - Form errors container check
**Vấn đề:** Check `if (!this.errorsContainer) return` có thể hide bugs nếu container missing
**Gợi ý fix:** Log warning hoặc throw error trong development mode

---

## BE ↔ FE Integration

### Đánh giá sự nhất quán

| Aspect | Status | Notes |
|--------|--------|-------|
| API Endpoints | ✅ Pass | FE gọi đúng URL và method như contract |
| Request Schema | ✅ Pass | JSON payload khớp với contract |
| Response Schema | ✅ Pass | FE expect đúng structure `success.data.*` |
| Error Response | ⚠️ Partial | FE không handle đầy đủ các HTTP status codes (401, 403, 404) |
| Authentication | ✅ Pass | Bearer token đúng format |
| Validation | ✅ Pass | Client-side validation khớp server validation rules |

### Missing Endpoints trong FE code
Theo API contract, còn các endpoints chưa thấy implement trong FS1:
- `GET /api/v1/projects/{id}` - Get project details (chỉ dùng trong ProjectSettings)
- `PUT /api/v1/projects/{id}` - Update project info
- `DELETE /api/v1/projects/{id}` - Delete project
- `POST /api/v1/projects/validate` - Pre-validation endpoint

---

## Kết luận

### Tổng số vấn đề: 12
- **High:** 3 (Security token storage, HTTP status check, network error handling)
- **Medium:** 4 (XSS vulnerability, generic errors, loading state, duplicate code)
- **Low:** 5 (Magic strings, missing JSDoc, no retry, alert UX, error container check)

### Sẵn sàng ship: **No - Cần sửa trước**

### Priority fixes trước khi ship:
1. **[HIGH]** Fix token storage security (dùng httpOnly cookie hoặc implement secure storage)
2. **[HIGH]** Add HTTP status code checking before parsing JSON response
3. **[HIGH]** Handle network errors properly với user-friendly messages
4. **[MEDIUM]** Fix XSS vulnerability bằng cách escape trước khi insert vào template
5. **[MEDIUM]** Implement proper error messages phân biệt theo status code

### Khuyến nghị:
- Tạo API service layer để centralize error handling và endpoint management
- Implement global interceptors cho authentication và error handling
- Thêm unit tests cho validator và các edge cases
- Consider dùng modern fetch wrapper như Axios để giảm boilerplate code
