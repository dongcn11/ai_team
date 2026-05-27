# Data Models - Audiobook Project Initialization

## Database Schema

### 1. users
```sql
CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    email_verified_at TIMESTAMP NULL,
    password VARCHAR(255) NOT NULL,
    remember_token VARCHAR(100) NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 2. personal_access_tokens (Laravel Sanctum)
```sql
CREATE TABLE personal_access_tokens (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tokenable_type VARCHAR(255) NOT NULL,
    tokenable_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    token VARCHAR(64) NOT NULL UNIQUE,
    abilities TEXT NULL,
    last_used_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    
    INDEX idx_tokenable (tokenable_type, tokenable_id),
    INDEX idx_token (token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 3. projects
```sql
CREATE TABLE projects (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    status ENUM('draft', 'active', 'completed', 'archived') DEFAULT 'draft',
    deleted_at TIMESTAMP NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    
    CONSTRAINT fk_projects_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_deleted_at (deleted_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 4. project_settings
```sql
CREATE TABLE project_settings (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT UNSIGNED NOT NULL UNIQUE,
    voice_id VARCHAR(100) NOT NULL,
    voice_name VARCHAR(255) NULL,
    language VARCHAR(10) NOT NULL COMMENT 'ISO 639-1 language code',
    audio_format ENUM('mp3', 'wav', 'm4a') DEFAULT 'mp3',
    bitrate INT UNSIGNED DEFAULT 128 COMMENT 'Audio bitrate in kbps',
    sample_rate INT UNSIGNED DEFAULT 44100 COMMENT 'Sample rate in Hz',
    channels TINYINT UNSIGNED DEFAULT 2 COMMENT 'Audio channels (1=mono, 2=stereo)',
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    
    CONSTRAINT fk_settings_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    
    INDEX idx_voice_id (voice_id),
    INDEX idx_language (language)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 5. chapters
```sql
CREATE TABLE chapters (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    chapter_number INT UNSIGNED NOT NULL,
    content TEXT NULL,
    word_count INT UNSIGNED DEFAULT 0,
    status ENUM('draft', 'processing', 'completed', 'failed') DEFAULT 'draft',
    audio_file_path VARCHAR(500) NULL,
    audio_duration INT UNSIGNED NULL COMMENT 'Duration in seconds',
    order_number INT UNSIGNED NOT NULL,
    deleted_at TIMESTAMP NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    
    CONSTRAINT fk_chapters_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    
    INDEX idx_project_id (project_id),
    INDEX idx_chapter_number (project_id, chapter_number),
    INDEX idx_order (project_id, order_number),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 6. voices
```sql
CREATE TABLE voices (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    language VARCHAR(10) NOT NULL COMMENT 'ISO 639-1 language code',
    language_name VARCHAR(100) NOT NULL,
    gender ENUM('male', 'female', 'neutral') NOT NULL,
    provider VARCHAR(100) NOT NULL COMMENT 'Voice provider (e.g., google, aws, azure)',
    preview_url VARCHAR(500) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INT UNSIGNED DEFAULT 0,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    
    INDEX idx_language (language),
    INDEX idx_gender (gender),
    INDEX idx_active (is_active),
    INDEX idx_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7. project_activity_logs
```sql
CREATE TABLE project_activity_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    action VARCHAR(100) NOT NULL COMMENT 'e.g., created, updated, deleted, settings_changed',
    description TEXT NULL,
    metadata JSON NULL COMMENT 'Additional data about the action',
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMP NULL,
    
    CONSTRAINT fk_logs_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_logs_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_project_id (project_id),
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 8. cache (Redis can be used alternatively)
```sql
CREATE TABLE cache (
    key VARCHAR(255) PRIMARY KEY,
    value MEDIUMTEXT NOT NULL,
    expiration INT UNSIGNED NOT NULL,
    
    INDEX idx_expiration (expiration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 9. cache_locks
```sql
CREATE TABLE cache_locks (
    key VARCHAR(255) PRIMARY KEY,
    owner VARCHAR(255) NOT NULL,
    expiration INT UNSIGNED NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 10. jobs (for queue processing)
```sql
CREATE TABLE jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    queue VARCHAR(255) NOT NULL,
    payload LONGTEXT NOT NULL,
    available_at INT UNSIGNED NOT NULL,
    reserved_at INT UNSIGNED NULL,
    reserved_by VARCHAR(255) NULL,
    attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NULL,
    
    INDEX idx_queue (queue),
    INDEX idx_available_at (available_at),
    INDEX idx_reserved_at (reserved_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 11. failed_jobs
```sql
CREATE TABLE failed_jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    uuid VARCHAR(255) NOT NULL UNIQUE,
    connection TEXT NOT NULL,
    queue TEXT NOT NULL,
    payload LONGTEXT NOT NULL,
    exception LONGTEXT NOT NULL,
    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_uuid (uuid),
    INDEX idx_failed_at (failed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## Eloquent Model Relationships

### User Model
```php
class User extends Authenticatable
{
    public function projects(): HasMany
    {
        return $this->hasMany(Project::class);
    }
    
    public function activityLogs(): HasMany
    {
        return $this->hasMany(ProjectActivityLog::class);
    }
}
```

### Project Model
```php
class Project extends Model
{
    use SoftDeletes;
    
    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
    
    public function settings(): HasOne
    {
        return $this->hasOne(ProjectSetting::class);
    }
    
    public function chapters(): HasMany
    {
        return $this->hasMany(Chapter::class)->orderBy('order_number');
    }
    
    public function activityLogs(): HasMany
    {
        return $this->hasMany(ProjectActivityLog::class);
    }
}
```

### ProjectSetting Model
```php
class ProjectSetting extends Model
{
    public function project(): BelongsTo
    {
        return $this->belongsTo(Project::class);
    }
    
    public function voice(): BelongsTo
    {
        return $this->belongsTo(Voice::class, 'voice_id', 'id');
    }
}
```

### Chapter Model
```php
class Chapter extends Model
{
    use SoftDeletes;
    
    public function project(): BelongsTo
    {
        return $this->belongsTo(Project::class);
    }
}
```

### Voice Model
```php
class Voice extends Model
{
    public function projects(): HasMany
    {
        return $this->hasMany(ProjectSetting::class, 'voice_id', 'id');
    }
    
    public function scopeActive($query)
    {
        return $query->where('is_active', true);
    }
    
    public function scopeByLanguage($query, string $language)
    {
        return $query->where('language', $language);
    }
}
```

---

## Seed Data

### voices - Sample Data
```sql
INSERT INTO voices (id, name, language, language_name, gender, provider, preview_url, is_active, sort_order) VALUES
('vi-VN-HoaiMy', 'Hoai My', 'vi', 'Vietnamese', 'female', 'google', null, true, 1),
('vi-VN-NamMinh', 'Nam Minh', 'vi', 'Vietnamese', 'male', 'google', null, true, 2),
('en-US-Jenny', 'Jenny', 'en', 'English (US)', 'female', 'azure', null, true, 3),
('en-US-Guy', 'Guy', 'en', 'English (US)', 'male', 'azure', null, true, 4),
('ja-JP-Nanami', 'Nanami', 'ja', 'Japanese', 'female', 'azure', null, true, 5);
```

---

## Indexes Summary

| Table | Indexes |
|-------|---------|
| users | idx_email |
| projects | idx_user_id, idx_status, idx_deleted_at, idx_created_at |
| project_settings | idx_voice_id, idx_language |
| chapters | idx_project_id, idx_chapter_number, idx_order, idx_status |
| voices | idx_language, idx_gender, idx_active, idx_sort |
| project_activity_logs | idx_project_id, idx_user_id, idx_action, idx_created_at |
| jobs | idx_queue, idx_available_at, idx_reserved_at |

---

## Notes

1. **Soft Deletes**: Projects and chapters use soft deletes for data recovery
2. **Cascading Deletes**: All related data is deleted when a project is deleted
3. **Unique Constraints**: project_settings.project_id is unique (one-to-one)
4. **Enum Values**: Use ENUM for status fields to ensure data integrity
5. **Timestamps**: All tables use created_at and updated_at timestamps
6. **Character Set**: utf8mb4 for full Unicode support (including emojis)
7. **Foreign Keys**: All relationships have proper foreign key constraints
8. **Indexes**: Strategic indexes for common query patterns
