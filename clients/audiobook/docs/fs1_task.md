# FS1 Tasks - Audiobook Project Initialization

## Full Stack Developer 1 - Task Breakdown

---

## US-001: Create New Audiobook Project (5 points)

### Backend Tasks

#### 1.1 Create ProjectController
**File:** `app/Http/Controllers/Api/V1/ProjectController.php`

**Methods:**
- `store()` - Create new project
- `index()` - List user projects
- `show()` - Get project details
- `update()` - Update project info
- `destroy()` - Delete project

**Implementation:**
```php
<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Http\Requests\Project\CreateProjectRequest;
use App\Http\Requests\Project\UpdateProjectRequest;
use App\Http\Resources\ProjectResource;
use App\Http\Resources\ProjectCollection;
use App\Models\Project;
use App\Models\ProjectSetting;
use App\Services\ProjectService;
use Illuminate\Http\JsonResponse;

class ProjectController extends Controller
{
    public function __construct(
        private ProjectService $projectService
    ) {}
    
    public function index(): JsonResponse
    {
        $projects = $this->projectService->getUserProjects(
            auth()->user(),
            request()->only(['page', 'per_page', 'sort_by', 'sort_order', 'status'])
        );
        
        return response()->json([
            'success' => true,
            'data' => $projects
        ]);
    }
    
    public function store(CreateProjectRequest $request): JsonResponse
    {
        $project = $this->projectService->createProject(
            auth()->user(),
            $request->validated()
        );
        
        return response()->json([
            'success' => true,
            'data' => [
                'project' => new ProjectResource($project),
                'settings' => $project->settings
            ],
            'message' => 'Project created successfully'
        ], 201);
    }
    
    public function show(Project $project): JsonResponse
    {
        $this->authorize('view', $project);
        
        return response()->json([
            'success' => true,
            'data' => [
                'project' => new ProjectResource($project),
                'settings' => $project->settings,
                'statistics' => $this->projectService->getProjectStatistics($project)
            ]
        ]);
    }
    
    public function update(UpdateProjectRequest $request, Project $project): JsonResponse
    {
        $this->authorize('update', $project);
        
        $project = $this->projectService->updateProject($project, $request->validated());
        
        return response()->json([
            'success' => true,
            'data' => new ProjectResource($project),
            'message' => 'Project updated successfully'
        ]);
    }
    
    public function destroy(Project $project): JsonResponse
    {
        $this->authorize('delete', $project);
        
        $this->projectService->deleteProject($project);
        
        return response()->json([
            'success' => true,
            'message' => 'Project deleted successfully'
        ]);
    }
}
```

---

#### 1.2 Create Form Requests
**Files:**
- `app/Http/Requests/Project/CreateProjectRequest.php`
- `app/Http/Requests/Project/UpdateProjectRequest.php`
- `app/Http/Requests/Project/UpdateProjectSettingsRequest.php`

**CreateProjectRequest.php:**
```php
<?php

namespace App\Http\Requests\Project;

use Illuminate\Foundation\Http\FormRequest;

class CreateProjectRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }
    
    public function rules(): array
    {
        return [
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:1000'],
            'settings' => ['required', 'array'],
            'settings.voice_id' => ['required', 'string', 'exists:voices,id'],
            'settings.language' => ['required', 'string', 'size:2'],
            'settings.audio_format' => ['required', 'string', 'in:mp3,wav,m4a'],
            'settings.bitrate' => ['nullable', 'integer', 'min:64', 'max:320'],
        ];
    }
    
    public function messages(): array
    {
        return [
            'name.required' => 'Project name is required',
            'name.max' => 'Project name must not exceed 255 characters',
            'settings.voice_id.required' => 'Voice selection is required',
            'settings.voice_id.exists' => 'Selected voice is invalid',
            'settings.language.required' => 'Language is required',
            'settings.language.size' => 'Language code must be 2 characters',
            'settings.audio_format.in' => 'Invalid audio format',
            'settings.bitrate.min' => 'Bitrate must be at least 64 kbps',
            'settings.bitrate.max' => 'Bitrate must not exceed 320 kbps',
        ];
    }
}
```

---

#### 1.3 Create ProjectService
**File:** `app/Services/ProjectService.php`

```php
<?php

namespace App\Services;

use App\Models\Project;
use App\Models\ProjectSetting;
use App\Models\ProjectActivityLog;
use App\Models\User;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Pagination\LengthAwarePaginator;

class ProjectService
{
    public function getUserProjects(User $user, array $filters = []): LengthAwarePaginator
    {
        $query = Project::with('settings')
            ->where('user_id', $user->id)
            ->withCount('chapters');
        
        // Apply filters
        if (isset($filters['status']) && $filters['status'] !== 'all') {
            $query->where('status', $filters['status']);
        }
        
        // Apply sorting
        $sortBy = $filters['sort_by'] ?? 'created_at';
        $sortOrder = $filters['sort_order'] ?? 'desc';
        $query->orderBy($sortBy, $sortOrder);
        
        return $query->paginate($filters['per_page'] ?? 15);
    }
    
    public function createProject(User $user, array $data): Project
    {
        return \DB::transaction(function () use ($user, $data) {
            $project = Project::create([
                'user_id' => $user->id,
                'name' => $data['name'],
                'description' => $data['description'] ?? null,
                'status' => 'draft',
            ]);
            
            ProjectSetting::create([
                'project_id' => $project->id,
                'voice_id' => $data['settings']['voice_id'],
                'voice_name' => $this->getVoiceName($data['settings']['voice_id']),
                'language' => $data['settings']['language'],
                'audio_format' => $data['settings']['audio_format'],
                'bitrate' => $data['settings']['bitrate'] ?? 128,
            ]);
            
            $this->logActivity($project, $user, 'created', 'Project created');
            
            return $project->fresh(['settings']);
        });
    }
    
    public function updateProject(Project $project, array $data): Project
    {
        $project->update([
            'name' => $data['name'],
            'description' => $data['description'] ?? null,
        ]);
        
        $this->logActivity($project, auth()->user(), 'updated', 'Project info updated');
        
        return $project;
    }
    
    public function updateSettings(Project $project, array $data): ProjectSetting
    {
        $settings = $project->settings;
        
        $settings->update([
            'voice_id' => $data['voice_id'],
            'voice_name' => $this->getVoiceName($data['voice_id']),
            'language' => $data['language'],
            'audio_format' => $data['audio_format'],
            'bitrate' => $data['bitrate'] ?? 128,
        ]);
        
        $this->logActivity($project, auth()->user(), 'settings_changed', 'Project settings updated');
        
        return $settings->fresh();
    }
    
    public function deleteProject(Project $project): void
    {
        $this->logActivity($project, auth()->user(), 'deleted', 'Project deleted');
        
        $project->delete();
    }
    
    public function getProjectStatistics(Project $project): array
    {
        return [
            'chapters_count' => $project->chapters()->count(),
            'total_words' => $project->chapters()->sum('word_count'),
            'estimated_duration' => $this->calculateEstimatedDuration($project),
        ];
    }
    
    private function getVoiceName(string $voiceId): ?string
    {
        return \App\Models\Voice::find($voiceId)?->name;
    }
    
    private function calculateEstimatedDuration(Project $project): string
    {
        $totalWords = $project->chapters()->sum('word_count');
        $averageWordsPerMinute = 150;
        $minutes = ceil($totalWords / $averageWordsPerMinute);
        
        if ($minutes < 60) {
            return "{$minutes} min";
        }
        
        $hours = floor($minutes / 60);
        $remainingMinutes = $minutes % 60;
        
        return "{$hours}h {$remainingMinutes}m";
    }
    
    private function logActivity(
        Project $project,
        User $user,
        string $action,
        string $description,
        array $metadata = []
    ): void {
        ProjectActivityLog::create([
            'project_id' => $project->id,
            'user_id' => $user->id,
            'action' => $action,
            'description' => $description,
            'metadata' => $metadata,
            'ip_address' => request()->ip(),
            'user_agent' => request()->userAgent(),
        ]);
    }
}
```

---

#### 1.4 Create API Resources
**Files:**
- `app/Http/Resources/ProjectResource.php`
- `app/Http/Resources/ProjectCollection.php`

**ProjectResource.php:**
```php
<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class ProjectResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'description' => $this->description,
            'status' => $this->status,
            'chapters_count' => $this->whenCounted('chapters'),
            'created_at' => $this->created_at->toIso8601String(),
            'updated_at' => $this->updated_at->toIso8601String(),
        ];
    }
}
```

---

#### 1.5 Create Policy
**File:** `app/Policies/ProjectPolicy.php`

```php
<?php

namespace App\Policies;

use App\Models\Project;
use App\Models\User;

class ProjectPolicy
{
    public function view(User $user, Project $project): bool
    {
        return $user->id === $project->user_id;
    }
    
    public function update(User $user, Project $project): bool
    {
        return $user->id === $project->user_id;
    }
    
    public function delete(User $user, Project $project): bool
    {
        return $user->id === $project->user_id;
    }
}
```

---

#### 1.6 Define API Routes
**File:** `routes/api.php`

```php
<?php

use App\Http\Controllers\Api\V1\ProjectController;
use Illuminate\Support\Facades\Route;

Route::middleware(['auth:sanctum'])->group(function () {
    Route::prefix('v1')->group(function () {
        Route::apiResource('projects', ProjectController::class);
        Route::put('projects/{project}/settings', [ProjectController::class, 'updateSettings']);
    });
});
```

---

### Frontend Tasks

#### 1.7 Create Dashboard Component
**File:** `public/assets/js/pages/dashboard.js`

```javascript
class DashboardPage {
    constructor() {
        this.projectsContainer = document.getElementById('projects-list');
        this.createProjectBtn = document.getElementById('create-project-btn');
        this.projects = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadProjects();
    }
    
    bindEvents() {
        this.createProjectBtn?.addEventListener('click', () => {
            this.navigateToCreateProject();
        });
    }
    
    async loadProjects() {
        try {
            const response = await fetch('/api/v1/projects', {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Accept': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.projects = data.data.projects;
                this.renderProjects();
            }
        } catch (error) {
            console.error('Error loading projects:', error);
            this.showError('Failed to load projects');
        }
    }
    
    renderProjects() {
        if (this.projects.length === 0) {
            this.projectsContainer.innerHTML = `
                <div class="empty-state">
                    <p>No projects yet. Create your first audiobook project!</p>
                </div>
            `;
            return;
        }
        
        this.projectsContainer.innerHTML = this.projects.map(project => `
            <div class="project-card" data-project-id="${project.id}">
                <h3>${this.escapeHtml(project.name)}</h3>
                <p class="description">${this.escapeHtml(project.description || 'No description')}</p>
                <div class="project-meta">
                    <span class="status status-${project.status}">${project.status}</span>
                    <span class="chapters">${project.chapters_count || 0} chapters</span>
                </div>
                <div class="project-actions">
                    <button class="btn btn-primary" onclick="window.location.href='/projects/${project.id}'">
                        Open
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    navigateToCreateProject() {
        window.location.href = '/projects/create';
    }
    
    showError(message) {
        // Implement error display
        alert(message);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new DashboardPage();
});
```

---

#### 1.8 Create Project Creation Form UI
**File:** `public/assets/js/pages/project-create.js`

```javascript
class ProjectCreatePage {
    constructor() {
        this.form = document.getElementById('project-form');
        this.nameInput = document.getElementById('project-name');
        this.descriptionInput = document.getElementById('project-description');
        this.voiceSelect = document.getElementById('voice-select');
        this.languageSelect = document.getElementById('language-select');
        this.formatSelect = document.getElementById('audio-format');
        this.bitrateInput = document.getElementById('bitrate');
        this.submitBtn = document.getElementById('submit-btn');
        this.errorsContainer = document.getElementById('form-errors');
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadVoices();
    }
    
    bindEvents() {
        this.form?.addEventListener('submit', (e) => this.handleSubmit(e));
        this.languageSelect?.addEventListener('change', () => this.loadVoices());
    }
    
    async loadVoices() {
        const language = this.languageSelect?.value || 'all';
        
        try {
            const response = await fetch(`/api/v1/voices?language=${language}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Accept': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success && this.voiceSelect) {
                this.voiceSelect.innerHTML = data.data.voices.map(voice => `
                    <option value="${voice.id}">${voice.name} (${voice.gender})</option>
                `).join('');
            }
        } catch (error) {
            console.error('Error loading voices:', error);
        }
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        this.clearErrors();
        
        const formData = {
            name: this.nameInput.value.trim(),
            description: this.descriptionInput.value.trim(),
            settings: {
                voice_id: this.voiceSelect.value,
                language: this.languageSelect.value,
                audio_format: this.formatSelect.value,
                bitrate: parseInt(this.bitrateInput.value) || 128
            }
        };
        
        try {
            this.setSubmitting(true);
            
            const response = await fetch('/api/v1/projects', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Accept': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                this.showSuccess('Project created successfully!');
                setTimeout(() => {
                    window.location.href = `/projects/${data.data.project.id}`;
                }, 1000);
            } else {
                this.displayErrors(data.errors);
            }
        } catch (error) {
            console.error('Error creating project:', error);
            this.showError('Failed to create project. Please try again.');
        } finally {
            this.setSubmitting(false);
        }
    }
    
    displayErrors(errors) {
        if (!this.errorsContainer) return;
        
        const errorMessages = Object.values(errors).flat();
        this.errorsContainer.innerHTML = errorMessages
            .map(msg => `<div class="error-message">${this.escapeHtml(msg)}</div>`)
            .join('');
        this.errorsContainer.style.display = 'block';
    }
    
    clearErrors() {
        if (this.errorsContainer) {
            this.errorsContainer.innerHTML = '';
            this.errorsContainer.style.display = 'none';
        }
    }
    
    setSubmitting(isSubmitting) {
        if (this.submitBtn) {
            this.submitBtn.disabled = isSubmitting;
            this.submitBtn.textContent = isSubmitting ? 'Creating...' : 'Create Project';
        }
    }
    
    showSuccess(message) {
        // Implement success notification
        alert(message);
    }
    
    showError(message) {
        alert(message);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    new ProjectCreatePage();
});
```

---

#### 1.9 Create CSS Styles
**File:** `public/assets/css/project.css`

```css
/* Project Card Styles */
.project-card {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
    transition: box-shadow 0.2s ease;
}

.project-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.project-card h3 {
    margin: 0 0 8px 0;
    color: #333;
    font-size: 18px;
}

.project-card .description {
    color: #666;
    font-size: 14px;
    margin-bottom: 12px;
}

.project-meta {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
}

.status {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
}

.status-draft {
    background: #fff3cd;
    color: #856404;
}

.status-active {
    background: #d4edda;
    color: #155724;
}

.status-completed {
    background: #cce5ff;
    color: #004085;
}

.status-archived {
    background: #e2e3e5;
    color: #383d41;
}

/* Form Styles */
.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
    color: #333;
}

.form-control {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
    transition: border-color 0.2s;
}

.form-control:focus {
    outline: none;
    border-color: #007bff;
    box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
}

.error-message {
    background: #f8d7da;
    color: #721c24;
    padding: 8px 12px;
    border-radius: 4px;
    margin-bottom: 8px;
    font-size: 14px;
}

.btn {
    padding: 10px 20px;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.2s;
}

.btn-primary {
    background: #007bff;
    color: #fff;
}

.btn-primary:hover {
    background: #0056b3;
}

.btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

/* Empty State */
.empty-state {
    text-align: center;
    padding: 40px 20px;
    color: #666;
}
```

---

### Test Tasks

#### 1.10 Write Unit Tests
**File:** `tests/Feature/Api/ProjectControllerTest.php`

```php
<?php

namespace Tests\Feature\Api;

use App\Models\Project;
use App\Models\ProjectSetting;
use App\Models\User;
use App\Models\Voice;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ProjectControllerTest extends TestCase
{
    use RefreshDatabase;
    
    public function test_user_can_create_project(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        Voice::factory()->create(['id' => 'voice-123']);
        
        $response = $this->postJson('/api/v1/projects', [
            'name' => 'My Audiobook',
            'description' => 'Test project',
            'settings' => [
                'voice_id' => 'voice-123',
                'language' => 'en',
                'audio_format' => 'mp3',
                'bitrate' => 128,
            ]
        ]);
        
        $response->assertStatus(201)
            ->assertJson([
                'success' => true,
                'message' => 'Project created successfully'
            ]);
        
        $this->assertDatabaseHas('projects', [
            'name' => 'My Audiobook',
            'user_id' => $user->id
        ]);
    }
    
    public function test_project_creation_requires_name(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        $response = $this->postJson('/api/v1/projects', [
            'description' => 'Test project',
            'settings' => [
                'voice_id' => 'voice-123',
                'language' => 'en',
                'audio_format' => 'mp3',
            ]
        ]);
        
        $response->assertStatus(422)
            ->assertJsonValidationErrors('name');
    }
    
    public function test_user_can_get_projects_list(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        Project::factory()->count(3)->create(['user_id' => $user->id]);
        
        $response = $this->getJson('/api/v1/projects');
        
        $response->assertStatus(200)
            ->assertJson([
                'success' => true
            ])
            ->assertJsonPath('data.projects', fn($projects) => count($projects) === 3);
    }
    
    public function test_user_can_only_see_own_projects(): void
    {
        $user1 = User::factory()->create();
        $user2 = User::factory()->create();
        Sanctum::actingAs($user1);
        
        Project::factory()->create(['user_id' => $user1->id]);
        Project::factory()->create(['user_id' => $user2->id]);
        
        $response = $this->getJson('/api/v1/projects');
        
        $response->assertStatus(200)
            ->assertJsonPath('data.projects', fn($projects) => count($projects) === 1);
    }
    
    public function test_user_can_view_project_details(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        $project = Project::factory()->create(['user_id' => $user->id]);
        ProjectSetting::factory()->create(['project_id' => $project->id]);
        
        $response = $this->getJson("/api/v1/projects/{$project->id}");
        
        $response->assertStatus(200)
            ->assertJson([
                'success' => true,
                'data' => [
                    'project' => [
                        'id' => $project->id,
                        'name' => $project->name
                    ]
                ]
            ]);
    }
    
    public function test_user_cannot_view_others_project(): void
    {
        $user = User::factory()->create();
        $otherUser = User::factory()->create();
        Sanctum::actingAs($user);
        
        $project = Project::factory()->create(['user_id' => $otherUser->id]);
        
        $response = $this->getJson("/api/v1/projects/{$project->id}");
        
        $response->assertStatus(403);
    }
    
    public function test_user_can_update_project(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        $project = Project::factory()->create(['user_id' => $user->id]);
        
        $response = $this->putJson("/api/v1/projects/{$project->id}", [
            'name' => 'Updated Name',
            'description' => 'Updated description'
        ]);
        
        $response->assertStatus(200)
            ->assertJson([
                'success' => true,
                'data' => [
                    'name' => 'Updated Name',
                    'description' => 'Updated description'
                ]
            ]);
    }
    
    public function test_user_can_delete_project(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        $project = Project::factory()->create(['user_id' => $user->id]);
        
        $response = $this->deleteJson("/api/v1/projects/{$project->id}");
        
        $response->assertStatus(200)
            ->assertJson([
                'success' => true,
                'message' => 'Project deleted successfully'
            ]);
        
        $this->assertSoftDeleted('projects', ['id' => $project->id]);
    }
}
```

---

## US-003: Configure Project Settings (5 points)

### Backend Tasks

#### 3.1 Create Settings Controller Method
**File:** `app/Http/Controllers/Api/V1/ProjectController.php`

Add method:
```php
public function updateSettings(UpdateProjectSettingsRequest $request, Project $project): JsonResponse
{
    $this->authorize('update', $project);
    
    $settings = $this->projectService->updateSettings($project, $request->validated());
    
    return response()->json([
        'success' => true,
        'data' => $settings,
        'message' => 'Settings updated successfully'
    ]);
}
```

---

#### 3.2 Create Settings Validation
**File:** `app/Http/Requests/Project/UpdateProjectSettingsRequest.php`

```php
<?php

namespace App\Http\Requests\Project;

use Illuminate\Foundation\Http\FormRequest;

class UpdateProjectSettingsRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }
    
    public function rules(): array
    {
        return [
            'voice_id' => ['required', 'string', 'exists:voices,id'],
            'language' => ['required', 'string', 'size:2'],
            'audio_format' => ['required', 'string', 'in:mp3,wav,m4a'],
            'bitrate' => ['nullable', 'integer', 'min:64', 'max:320'],
        ];
    }
}
```

---

### Frontend Tasks

#### 3.3 Create Settings Component
**File:** `public/assets/js/components/project-settings.js`

```javascript
class ProjectSettings {
    constructor(projectId) {
        this.projectId = projectId;
        this.form = document.getElementById('settings-form');
        this.voiceSelect = document.getElementById('settings-voice');
        this.languageSelect = document.getElementById('settings-language');
        this.formatSelect = document.getElementById('settings-format');
        this.bitrateInput = document.getElementById('settings-bitrate');
        this.saveBtn = document.getElementById('save-settings-btn');
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadSettings();
        this.loadVoices();
    }
    
    bindEvents() {
        this.form?.addEventListener('submit', (e) => this.handleSave(e));
        this.languageSelect?.addEventListener('change', () => this.loadVoices());
    }
    
    async loadSettings() {
        try {
            const response = await fetch(`/api/v1/projects/${this.projectId}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Accept': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success && data.data.settings) {
                const settings = data.data.settings;
                this.voiceSelect.value = settings.voice_id;
                this.languageSelect.value = settings.language;
                this.formatSelect.value = settings.audio_format;
                this.bitrateInput.value = settings.bitrate;
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }
    
    async loadVoices() {
        const language = this.languageSelect?.value || 'all';
        
        try {
            const response = await fetch(`/api/v1/voices?language=${language}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Accept': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success && this.voiceSelect) {
                this.voiceSelect.innerHTML = data.data.voices.map(voice => `
                    <option value="${voice.id}">${voice.name} (${voice.gender})</option>
                `).join('');
            }
        } catch (error) {
            console.error('Error loading voices:', error);
        }
    }
    
    async handleSave(e) {
        e.preventDefault();
        
        const settingsData = {
            voice_id: this.voiceSelect.value,
            language: this.languageSelect.value,
            audio_format: this.formatSelect.value,
            bitrate: parseInt(this.bitrateInput.value) || 128
        };
        
        try {
            this.saveBtn.disabled = true;
            this.saveBtn.textContent = 'Saving...';
            
            const response = await fetch(`/api/v1/projects/${this.projectId}/settings`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Accept': 'application/json'
                },
                body: JSON.stringify(settingsData)
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showNotification('Settings saved successfully', 'success');
            } else {
                this.showNotification('Failed to save settings', 'error');
            }
        } catch (error) {
            console.error('Error saving settings:', error);
            this.showNotification('Failed to save settings', 'error');
        } finally {
            this.saveBtn.disabled = false;
            this.saveBtn.textContent = 'Save Settings';
        }
    }
    
    showNotification(message, type) {
        // Implement notification system
        alert(`${type.toUpperCase()}: ${message}`);
    }
}

// Export for use in project detail page
window.ProjectSettings = ProjectSettings;
```

---

#### 3.4 Write Settings Tests
**File:** `tests/Feature/Api/ProjectSettingsTest.php`

```php
<?php

namespace Tests\Feature\Api;

use App\Models\Project;
use App\Models\ProjectSetting;
use App\Models\User;
use App\Models\Voice;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ProjectSettingsTest extends TestCase
{
    use RefreshDatabase;
    
    public function test_user_can_update_project_settings(): void
    {
        $user = User::factory()->create();
        Sanctum::actingAs($user);
        
        $project = Project::factory()->create(['user_id' => $user->id]);
        ProjectSetting::factory()->create(['project_id' => $project->id]);
        Voice::factory()->create(['id' => 'new-voice']);
        
        $response = $this->putJson("/api/v1/projects/{$project->id}/settings", [
            'voice_id' => 'new-voice',
            'language' => 'vi',
            'audio_format' => 'wav',
            'bitrate' => 256
        ]);
        
        $response->assertStatus(200)
            ->assertJson([
                'success' => true,
                'message' => 'Settings updated successfully'
            ]);
        
        $this->assertDatabaseHas('project_settings', [
            'project_id' => $project->id,
            'voice_id' => 'new-voice',
            'audio_format' => 'wav'
        ]);
    }
}
```

---

## US-005: Validate Project Inputs (3 points)

### Backend Tasks

#### 5.1 Create Validation Endpoint
**File:** `app/Http/Controllers/Api/V1/ProjectController.php`

Add method:
```php
public function validate(CreateProjectRequest $request): JsonResponse
{
    return response()->json([
        'success' => true,
        'data' => [
            'valid' => true,
            'errors' => []
        ]
    ]);
}
```

---

#### 5.2 Add Custom Validation Rules
**File:** `app/Rules/ValidVoiceId.php`

```php
<?php

namespace App\Rules;

use Closure;
use Illuminate\Contracts\Validation\ValidationRule;
use App\Models\Voice;

class ValidVoiceId implements ValidationRule
{
    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        $voice = Voice::find($value);
        
        if (!$voice) {
            $fail('The selected voice is invalid.');
            return;
        }
        
        if (!$voice->is_active) {
            $fail('The selected voice is no longer available.');
        }
    }
}
```

---

### Frontend Tasks

#### 5.3 Create Client-side Validation
**File:** `public/assets/js/validators/project-validator.js`

```javascript
class ProjectValidator {
    constructor() {
        this.errors = {};
    }
    
    validateProjectForm(data) {
        this.errors = {};
        
        this.validateName(data.name);
        this.validateDescription(data.description);
        this.validateSettings(data.settings);
        
        return {
            isValid: Object.keys(this.errors).length === 0,
            errors: this.errors
        };
    }
    
    validateName(name) {
        if (!name || name.trim() === '') {
            this.errors.name = ['Project name is required'];
            return;
        }
        
        if (name.length > 255) {
            this.errors.name = ['Project name must not exceed 255 characters'];
        }
        
        if (name.length < 3) {
            this.errors.name = ['Project name must be at least 3 characters'];
        }
    }
    
    validateDescription(description) {
        if (description && description.length > 1000) {
            this.errors.description = ['Description must not exceed 1000 characters'];
        }
    }
    
    validateSettings(settings) {
        if (!settings) {
            this.errors.settings = ['Settings are required'];
            return;
        }
        
        if (!settings.voice_id) {
            this.errors['settings.voice_id'] = ['Voice selection is required'];
        }
        
        if (!settings.language) {
            this.errors['settings.language'] = ['Language is required'];
        } else if (!/^[a-z]{2}$/.test(settings.language)) {
            this.errors['settings.language'] = ['Language must be a valid ISO 639-1 code'];
        }
        
        if (!settings.audio_format) {
            this.errors['settings.audio_format'] = ['Audio format is required'];
        } else if (!['mp3', 'wav', 'm4a'].includes(settings.audio_format)) {
            this.errors['settings.audio_format'] = ['Invalid audio format'];
        }
        
        if (settings.bitrate && (settings.bitrate < 64 || settings.bitrate > 320)) {
            this.errors['settings.bitrate'] = ['Bitrate must be between 64 and 320 kbps'];
        }
    }
    
    displayErrors(errorsContainer) {
        if (!errorsContainer) return;
        
        const allErrors = Object.values(this.errors).flat();
        
        if (allErrors.length === 0) {
            errorsContainer.style.display = 'none';
            return;
        }
        
        errorsContainer.innerHTML = allErrors
            .map(error => `<div class="error-message">${this.escapeHtml(error)}</div>`)
            .join('');
        errorsContainer.style.display = 'block';
    }
    
    clearErrors(errorsContainer) {
        if (errorsContainer) {
            errorsContainer.innerHTML = '';
            errorsContainer.style.display = 'none';
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export for use
window.ProjectValidator = ProjectValidator;
```

---

#### 5.4 Write Validation Tests
**File:** `tests/Unit/Validation/ProjectValidationTest.php`

```php
<?php

namespace Tests\Unit\Validation;

use App\Http\Requests\Project\CreateProjectRequest;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ProjectValidationTest extends TestCase
{
    use RefreshDatabase;
    
    public function test_name_is_required(): void
    {
        $response = $this->postJson('/api/v1/projects/validate', [
            'description' => 'Test',
            'settings' => [
                'voice_id' => 'voice-1',
                'language' => 'en',
                'audio_format' => 'mp3'
            ]
        ]);
        
        $response->assertStatus(422)
            ->assertJsonValidationErrors('name');
    }
    
    public function test_name_max_length(): void
    {
        $response = $this->postJson('/api/v1/projects/validate', [
            'name' => str_repeat('a', 256),
            'settings' => [
                'voice_id' => 'voice-1',
                'language' => 'en',
                'audio_format' => 'mp3'
            ]
        ]);
        
        $response->assertStatus(422)
            ->assertJsonValidationErrors('name');
    }
    
    public function test_voice_id_is_required(): void
    {
        $response = $this->postJson('/api/v1/projects/validate', [
            'name' => 'Test Project',
            'settings' => [
                'language' => 'en',
                'audio_format' => 'mp3'
            ]
        ]);
        
        $response->assertStatus(422)
            ->assertJsonValidationErrors('settings.voice_id');
    }
    
    public function test_language_must_be_valid(): void
    {
        $response = $this->postJson('/api/v1/projects/validate', [
            'name' => 'Test Project',
            'settings' => [
                'voice_id' => 'voice-1',
                'language' => 'invalid',
                'audio_format' => 'mp3'
            ]
        ]);
        
        $response->assertStatus(422)
            ->assertJsonValidationErrors('settings.language');
    }
    
    public function test_audio_format_must_be_valid(): void
    {
        $response = $this->postJson('/api/v1/projects/validate', [
            'name' => 'Test Project',
            'settings' => [
                'voice_id' => 'voice-1',
                'language' => 'en',
                'audio_format' => 'flac'
            ]
        ]);
        
        $response->assertStatus(422)
            ->assertJsonValidationErrors('settings.audio_format');
    }
}
```

---

## Definition of Done Checklist

### For Each User Story:
- [ ] Backend API endpoint implemented
- [ ] Frontend component created
- [ ] Form validation (client & server-side)
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing
- [ ] Error handling implemented
- [ ] Code reviewed
- [ ] Documentation updated

### Code Quality:
- [ ] PSR-12 coding standards followed
- [ ] No code duplication
- [ ] Proper error messages
- [ ] Logging implemented where needed
- [ ] Security best practices followed

### Testing:
- [ ] Unit tests coverage > 80%
- [ ] Feature tests for all endpoints
- [ ] Edge cases tested
- [ ] Validation rules tested

---

## Estimated Time Breakdown

| Task | Estimated Hours |
|------|----------------|
| US-001: Backend | 8 hours |
| US-001: Frontend | 6 hours |
| US-001: Tests | 4 hours |
| US-003: Backend | 4 hours |
| US-003: Frontend | 4 hours |
| US-003: Tests | 2 hours |
| US-005: Backend | 3 hours |
| US-005: Frontend | 3 hours |
| US-005: Tests | 3 hours |
| **Total** | **37 hours** |

---

## Files to Create/Modify

### Backend Files:
1. `app/Http/Controllers/Api/V1/ProjectController.php` (new)
2. `app/Http/Requests/Project/CreateProjectRequest.php` (new)
3. `app/Http/Requests/Project/UpdateProjectRequest.php` (new)
4. `app/Http/Requests/Project/UpdateProjectSettingsRequest.php` (new)
5. `app/Services/ProjectService.php` (new)
6. `app/Http/Resources/ProjectResource.php` (new)
7. `app/Http/Resources/ProjectCollection.php` (new)
8. `app/Policies/ProjectPolicy.php` (new)
9. `app/Rules/ValidVoiceId.php` (new)
10. `routes/api.php` (modify)
11. Database migrations (new)

### Frontend Files:
1. `public/assets/js/pages/dashboard.js` (new)
2. `public/assets/js/pages/project-create.js` (new)
3. `public/assets/js/components/project-settings.js` (new)
4. `public/assets/js/validators/project-validator.js` (new)
5. `public/assets/css/project.css` (new)
6. `resources/views/dashboard.blade.php` (new)
7. `resources/views/projects/create.blade.php` (new)
8. `resources/views/projects/show.blade.php` (new)

### Test Files:
1. `tests/Feature/Api/ProjectControllerTest.php` (new)
2. `tests/Feature/Api/ProjectSettingsTest.php` (new)
3. `tests/Unit/Validation/ProjectValidationTest.php` (new)
