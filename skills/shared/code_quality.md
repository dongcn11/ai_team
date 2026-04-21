# Skill: Code Quality

## Nguyên tắc chung
- Viết code như người khác sẽ maintain, không phải chỉ cho máy chạy
- Mỗi function làm đúng 1 việc, tên hàm mô tả rõ việc đó
- Không để magic number — dùng constant có tên
- Xóa code thừa, comment thừa trước khi hoàn thành

## Naming Convention
- **Python**: `snake_case` cho function/variable, `PascalCase` cho class
- **TypeScript**: `camelCase` cho function/variable, `PascalCase` cho class/component
- Tên boolean bắt đầu bằng `is_`, `has_`, `can_`
- Tên list/array dùng số nhiều: `users`, `tasks`, không phải `user_list`

## Comment
- Comment giải thích **tại sao**, không phải **cái gì**
- Docstring cho mọi public function:
  ```python
  def create_task(user_id: str, title: str) -> Task:
      """Tạo task mới cho user. Raise ValueError nếu title rỗng."""
  ```

## File size
- 1 file tối đa 300 dòng — nếu dài hơn thì tách module
- 1 function tối đa 40 dòng — nếu dài hơn thì tách helper

## Không được làm
- Không hardcode URL, password, secret key trong code
- Không dùng `print()` để debug trong production code — dùng `logging`
- Không để `TODO` hoặc `FIXME` chưa giải quyết khi submit
- Không catch exception rồi bỏ qua im lặng (`except: pass`)
