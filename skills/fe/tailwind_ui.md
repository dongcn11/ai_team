# Skill: Tailwind CSS Patterns

## Nguyên tắc
- Dùng utility classes, không viết CSS custom trừ khi thật sự cần
- Responsive mobile-first: `sm:` `md:` `lg:`
- Dark mode dùng `dark:` prefix

## Component classes hay dùng

### Button
```tsx
// Primary
<button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 
                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
  Tạo task
</button>

// Secondary
<button className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg 
                   hover:bg-gray-50 transition-colors">
  Hủy
</button>

// Danger
<button className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700">
  Xóa
</button>
```

### Card
```tsx
<div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 
                dark:border-gray-700 p-4 shadow-sm hover:shadow-md transition-shadow">
```

### Input
```tsx
<input className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                  focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                  dark:bg-gray-700 dark:border-gray-600 dark:text-white" />
```

### Badge status
```tsx
const statusColors = {
  "todo":        "bg-gray-100 text-gray-700",
  "in-progress": "bg-blue-100 text-blue-700",
  "done":        "bg-green-100 text-green-700",
}

<span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[task.status]}`}>
  {task.status}
</span>
```

### Loading skeleton
```tsx
<div className="animate-pulse space-y-3">
  <div className="h-4 bg-gray-200 rounded w-3/4" />
  <div className="h-4 bg-gray-200 rounded w-1/2" />
</div>
```

## Layout responsive chuẩn
```tsx
// Grid responsive
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">

// Sidebar layout
<div className="flex min-h-screen">
  <aside className="w-64 hidden md:block">...</aside>
  <main className="flex-1 p-6">...</main>
</div>
```
