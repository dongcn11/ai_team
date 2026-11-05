---
name: Laravel Blade Fullstack
description: Dùng khi dự án fullstack chạy Laravel + Blade (server-side render) — route, controller, FormRequest, Eloquent, migration, layout/component Blade, form + validate, auth, policy, Vite/Tailwind, feature test. Không áp dụng cho dự án FastAPI/React hay Laravel chỉ làm API.
---

# Skill: Laravel Blade Fullstack

> Chỉ áp dụng khi tech stack của dự án là **Laravel + Blade**. Nếu dự án là FastAPI/React thì bỏ qua skill này.
> Giả định Laravel 11+ (không còn `app/Http/Kernel.php`, middleware/exception cấu hình ở `bootstrap/app.php`), PHP 8.2+.

## Cấu trúc file chuẩn
```
app/
├── Http/Controllers/TaskController.php   ← mỏng: nhận request → gọi model/service → trả view/redirect
├── Http/Requests/StoreTaskRequest.php     ← validate + authorize
├── Models/Task.php                        ← $fillable, $casts, relation, scope
├── Policies/TaskPolicy.php                ← quyền theo từng bản ghi
└── View/Components/                       ← chỉ khi component cần logic PHP
database/migrations/xxxx_create_tasks_table.php
database/factories/TaskFactory.php
resources/views/
├── components/layouts/app.blade.php       ← layout chính (<x-layouts.app>)
├── components/{button,input,alert}.blade.php
└── tasks/{index,create,edit,show,_form}.blade.php
routes/web.php
tests/Feature/TaskTest.php
```

## Route
```php
// routes/web.php
use App\Http\Controllers\TaskController;

Route::middleware('auth')->group(function () {
    Route::resource('tasks', TaskController::class);   // index/create/store/show/edit/update/destroy
});
```
- Luôn đặt tên route, trong view/controller dùng `route('tasks.edit', $task)` — KHÔNG hard-code URL.
- Route model binding (`Task $task`) thay cho `Task::findOrFail($id)`.

## Migration + Model
```php
Schema::create('tasks', function (Blueprint $table) {
    $table->id();
    $table->foreignId('user_id')->constrained()->cascadeOnDelete();
    $table->string('title');
    $table->text('description')->nullable();
    $table->string('status')->default('todo')->index();
    $table->date('due_date')->nullable();
    $table->timestamps();
});
```
```php
class Task extends Model
{
    use HasFactory;

    protected $fillable = ['title', 'description', 'status', 'due_date'];   // KHÔNG đưa user_id vào

    protected function casts(): array
    {
        return ['due_date' => 'date'];
    }

    public function user(): BelongsTo { return $this->belongsTo(User::class); }

    public function scopeStatus(Builder $q, ?string $status): Builder
    {
        return $status ? $q->where('status', $status) : $q;
    }
}
```

## FormRequest
```php
class StoreTaskRequest extends FormRequest
{
    public function authorize(): bool { return true; }   // quyền theo bản ghi để Policy lo

    public function rules(): array
    {
        return [
            'title'       => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status'      => ['required', Rule::in(['todo', 'doing', 'done'])],
            'due_date'    => ['nullable', 'date', 'after_or_equal:today'],
        ];
    }

    public function attributes(): array
    {
        return ['title' => 'Tiêu đề', 'due_date' => 'Hạn chót'];   // tên field trong thông báo lỗi
    }
}
```

## Controller
```php
class TaskController extends Controller
{
    public function index(Request $request)
    {
        $tasks = $request->user()->tasks()
            ->status($request->query('status'))
            ->latest()
            ->paginate(15)
            ->withQueryString();                       // giữ filter khi sang trang

        return view('tasks.index', compact('tasks'));
    }

    public function create()
    {
        return view('tasks.create', ['task' => new Task()]);
    }

    public function store(StoreTaskRequest $request)
    {
        $request->user()->tasks()->create($request->validated());   // chỉ dùng validated()

        return redirect()->route('tasks.index')->with('success', 'Đã tạo task.');
    }

    public function edit(Task $task)
    {
        Gate::authorize('update', $task);
        return view('tasks.edit', compact('task'));
    }

    public function update(UpdateTaskRequest $request, Task $task)
    {
        Gate::authorize('update', $task);
        $task->update($request->validated());

        return redirect()->route('tasks.index')->with('success', 'Đã cập nhật.');
    }

    public function destroy(Task $task)
    {
        Gate::authorize('delete', $task);
        $task->delete();

        return back()->with('success', 'Đã xoá.');
    }
}
```
- POST/PUT/DELETE thành công → **redirect** (Post/Redirect/Get), không `return view()`.
- Logic nghiệp vụ dài hơn ~15 dòng → tách `app/Services/` hoặc Action class.

## Policy
```php
class TaskPolicy
{
    public function update(User $user, Task $task): bool { return $task->user_id === $user->id; }
    public function delete(User $user, Task $task): bool { return $task->user_id === $user->id; }
}
```
Laravel tự tìm `TaskPolicy` cho `Task`. Trong Blade dùng `@can('update', $task) … @endcan`.

## Layout bằng component
```blade
{{-- resources/views/components/layouts/app.blade.php --}}
@props(['title' => config('app.name')])
<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{{ $title }}</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="bg-gray-50 text-gray-900">
    @include('partials.nav')
    <main class="max-w-5xl mx-auto p-4">
        <x-alert />
        {{ $slot }}
    </main>
</body>
</html>
```
```blade
{{-- tasks/index.blade.php --}}
<x-layouts.app title="Danh sách task">
    <div class="flex justify-between items-center mb-4">
        <h1 class="text-xl font-semibold">Task</h1>
        <x-button :href="route('tasks.create')">Tạo task</x-button>
    </div>

    @forelse ($tasks as $task)
        <div class="bg-white border rounded-lg p-4 mb-2">
            <a href="{{ route('tasks.show', $task) }}" class="font-medium">{{ $task->title }}</a>
            <span class="text-sm text-gray-500">{{ $task->due_date?->format('d/m/Y') }}</span>
        </div>
    @empty
        <p class="text-gray-500">Chưa có task nào.</p>
    @endforelse

    {{ $tasks->links() }}
</x-layouts.app>
```

## Component Blade (anonymous)
```blade
{{-- components/input.blade.php --}}
@props(['name', 'label', 'type' => 'text', 'value' => null])
<div class="mb-4">
    <label for="{{ $name }}" class="block text-sm font-medium mb-1">{{ $label }}</label>
    <input id="{{ $name }}" name="{{ $name }}" type="{{ $type }}"
           value="{{ old($name, $value) }}"
           {{ $attributes->class([
               'w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500',
               'border-red-500' => $errors->has($name),
               'border-gray-300' => ! $errors->has($name),
           ]) }}>
    @error($name) <p class="text-sm text-red-600 mt-1">{{ $message }}</p> @enderror
</div>
```
```blade
{{-- components/alert.blade.php --}}
@if (session('success'))
    <div class="mb-4 p-3 rounded-lg bg-green-50 text-green-800">{{ session('success') }}</div>
@endif
```
- `$attributes->merge()/->class()` để caller thêm class/attr được.
- Component cần query DB hoặc logic phức tạp → class component (`php artisan make:component`), không viết `@php` dài trong view.

## Form create/edit dùng chung
```blade
{{-- tasks/_form.blade.php --}}
<form method="POST" action="{{ $task->exists ? route('tasks.update', $task) : route('tasks.store') }}">
    @csrf
    @if ($task->exists) @method('PUT') @endif

    <x-input name="title" label="Tiêu đề" :value="$task->title" required />

    <select name="status" class="...">
        @foreach (['todo' => 'Cần làm', 'doing' => 'Đang làm', 'done' => 'Xong'] as $value => $text)
            <option value="{{ $value }}" @selected(old('status', $task->status) === $value)>{{ $text }}</option>
        @endforeach
    </select>

    <button type="submit">{{ $task->exists ? 'Lưu' : 'Tạo' }}</button>
</form>
```
- Mọi form POST/PUT/PATCH/DELETE **phải có `@csrf`**; PUT/PATCH/DELETE thêm `@method`.
- Giữ dữ liệu khi validate lỗi bằng `old('field', $default)`; dùng `@selected`, `@checked`, `@disabled`.
- Nút xoá là một `<form method="POST">` + `@method('DELETE')`, có `onsubmit="return confirm('Xoá?')"`.

## Bảo mật — bắt buộc
- `{{ }}` tự escape. `{!! !!}` **chỉ** cho HTML đã sanitize hoặc do code tạo ra — không bao giờ cho input người dùng.
- Dữ liệu PHP → JS: `<script>const data = @json($items);</script>` (hoặc `Js::from()`), không nối chuỗi.
- Không dùng `$request->all()` để create/update — dùng `$request->validated()`; `$fillable` không chứa `user_id`, `role`, `is_admin`.
- Mọi truy cập theo id phải qua Policy/`Gate::authorize` hoặc query từ quan hệ của user (`$request->user()->tasks()`), tránh IDOR.
- Raw SQL chỉ với binding: `DB::select('... where id = ?', [$id])`.

## Hiệu năng
- Hiển thị quan hệ trong vòng lặp → eager load: `Task::with('user')->...`. Bật trong `AppServiceProvider::boot()`:
  `Model::preventLazyLoading(! app()->isProduction());`
- Danh sách luôn `paginate()`, không `->get()` toàn bảng.
- Đếm quan hệ: `withCount('comments')` thay cho `$task->comments->count()`.

## Frontend: Vite + Tailwind (+ Alpine khi cần)
- Asset qua `@vite([...])`, không link thẳng file trong `public/`. Dev: `npm run dev`; build: `npm run build`.
- Tương tác nhỏ (dropdown, modal, toggle) → Alpine.js (`x-data`, `x-show`), không dựng SPA.
- Gọi AJAX (fetch) phải gửi header `X-CSRF-TOKEN` lấy từ `<meta name="csrf-token">`.
- Class Tailwind theo skill `fe/tailwind_ui` (đổi `className` → `class`).

## Auth
- Dùng starter kit chính thức (Breeze/Blade) thay vì tự viết login/register/reset password.
- Lấy user: `$request->user()` trong controller, `@auth … @endauth` / `auth()->user()` trong view.

## Feature test
```php
// tests/Feature/TaskTest.php
uses(RefreshDatabase::class);

it('user tạo được task', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
        ->post(route('tasks.store'), ['title' => 'Viết test', 'status' => 'todo'])
        ->assertRedirect(route('tasks.index'))
        ->assertSessionHas('success');

    expect($user->tasks()->count())->toBe(1);
});

it('không sửa được task của người khác', function () {
    $task = Task::factory()->create();

    $this->actingAs(User::factory()->create())
        ->put(route('tasks.update', $task), ['title' => 'x', 'status' => 'done'])
        ->assertForbidden();
});

it('báo lỗi khi thiếu title', function () {
    $this->actingAs(User::factory()->create())
        ->post(route('tasks.store'), ['status' => 'todo'])
        ->assertSessionHasErrors('title');
});
```
Dự án dùng PHPUnit thì viết dạng class `extends TestCase` tương đương. Mỗi route mới tối thiểu: 1 case thành công, 1 case validate lỗi, 1 case không có quyền.

## Lệnh artisan hay dùng
```
php artisan make:model Task -mfc --policy --requests   # model + migration + factory + controller + policy + requests
php artisan make:controller TaskController --resource --model=Task
php artisan make:component Alert --view                # anonymous component
php artisan migrate        php artisan test        php artisan route:list
```

## Checklist trước khi bàn giao
- [ ] Route có tên, dùng `route()` ở mọi nơi
- [ ] Mọi form có `@csrf`; PUT/DELETE có `@method`
- [ ] Validate bằng FormRequest, lưu bằng `validated()`
- [ ] Có Policy cho bản ghi thuộc user
- [ ] Không `{!! !!}` với dữ liệu người dùng
- [ ] Danh sách có `paginate()`, quan hệ có eager load
- [ ] Lỗi validate hiện cạnh field, giữ `old()` input
- [ ] Flash message sau create/update/delete
- [ ] `php artisan test` xanh
