# API Contract - Audiobook Project Initialization

## Base URL
```
/api/v1
```

## Authentication
All endpoints require authentication using Laravel Sanctum tokens.
```
Authorization: Bearer {token}
```

---

## Endpoints

### 1. Create New Project

**Endpoint:** `POST /api/v1/projects`

**Description:** Create a new audiobook project

**Request Schema:**
```json
{
  "name": "string (required, max: 255)",
  "description": "string (nullable, max: 1000)",
  "settings": {
    "voice_id": "string (required)",
    "language": "string (required, ISO 639-1)",
    "audio_format": "string (required, enum: ['mp3', 'wav', 'm4a'])",
    "bitrate": "integer (optional, default: 128)"
  }
}
```

**Response Schema (201 Created):**
```json
{
  "success": true,
  "data": {
    "project": {
      "id": "integer",
      "name": "string",
      "description": "string|null",
      "user_id": "integer",
      "status": "string",
      "created_at": "datetime",
      "updated_at": "datetime"
    },
    "settings": {
      "id": "integer",
      "project_id": "integer",
      "voice_id": "string",
      "language": "string",
      "audio_format": "string",
      "bitrate": "integer"
    }
  },
  "message": "Project created successfully"
}
```

**Response Schema (422 Validation Error):**
```json
{
  "success": false,
  "errors": {
    "name": ["The name field is required.", "The name must not exceed 255 characters."],
    "settings.voice_id": ["The voice id field is required."]
  }
}
```

---

### 2. Get User Projects

**Endpoint:** `GET /api/v1/projects`

**Description:** Retrieve list of projects for authenticated user

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | integer | 1 | Page number for pagination |
| per_page | integer | 15 | Items per page (max: 50) |
| sort_by | string | created_at | Sort field (name, created_at, updated_at) |
| sort_order | string | desc | Sort order (asc, desc) |
| status | string | all | Filter by status (draft, active, completed, archived) |

**Response Schema (200 OK):**
```json
{
  "success": true,
  "data": {
    "projects": [
      {
        "id": "integer",
        "name": "string",
        "description": "string|null",
        "status": "string",
        "created_at": "datetime",
        "updated_at": "datetime",
        "chapters_count": "integer",
        "total_duration": "string|null"
      }
    ],
    "pagination": {
      "current_page": "integer",
      "last_page": "integer",
      "per_page": "integer",
      "total": "integer"
    }
  }
}
```

---

### 3. Get Project Details

**Endpoint:** `GET /api/v1/projects/{id}`

**Description:** Get detailed information about a specific project

**Response Schema (200 OK):**
```json
{
  "success": true,
  "data": {
    "project": {
      "id": "integer",
      "name": "string",
      "description": "string|null",
      "user_id": "integer",
      "status": "string",
      "created_at": "datetime",
      "updated_at": "datetime"
    },
    "settings": {
      "id": "integer",
      "project_id": "integer",
      "voice_id": "string",
      "voice_name": "string",
      "language": "string",
      "audio_format": "string",
      "bitrate": "integer"
    },
    "statistics": {
      "chapters_count": "integer",
      "total_words": "integer",
      "estimated_duration": "string"
    }
  }
}
```

**Response Schema (404 Not Found):**
```json
{
  "success": false,
  "message": "Project not found"
}
```

---

### 4. Update Project Info

**Endpoint:** `PUT /api/v1/projects/{id}`

**Description:** Update project name and description

**Request Schema:**
```json
{
  "name": "string (required, max: 255)",
  "description": "string (nullable, max: 1000)"
}
```

**Response Schema (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "integer",
    "name": "string",
    "description": "string|null",
    "updated_at": "datetime"
  },
  "message": "Project updated successfully"
}
```

---

### 5. Update Project Settings

**Endpoint:** `PUT /api/v1/projects/{id}/settings`

**Description:** Update project configuration settings

**Request Schema:**
```json
{
  "voice_id": "string (required)",
  "language": "string (required, ISO 639-1)",
  "audio_format": "string (required, enum: ['mp3', 'wav', 'm4a'])",
  "bitrate": "integer (optional, default: 128)"
}
```

**Response Schema (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "integer",
    "project_id": "integer",
    "voice_id": "string",
    "language": "string",
    "audio_format": "string",
    "bitrate": "integer",
    "updated_at": "datetime"
  },
  "message": "Settings updated successfully"
}
```

---

### 6. Delete Project

**Endpoint:** `DELETE /api/v1/projects/{id}`

**Description:** Soft delete a project

**Response Schema (200 OK):**
```json
{
  "success": true,
  "message": "Project deleted successfully"
}
```

---

### 7. Get Available Voices

**Endpoint:** `GET /api/v1/voices`

**Description:** Get list of available voices for audiobook generation

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| language | string | all | Filter by language (ISO 639-1) |
| gender | string | all | Filter by gender (male, female, any) |

**Response Schema (200 OK):**
```json
{
  "success": true,
  "data": {
    "voices": [
      {
        "id": "string",
        "name": "string",
        "language": "string",
        "language_name": "string",
        "gender": "string",
        "preview_url": "string|null"
      }
    ]
  }
}
```

---

### 8. Validate Project Data

**Endpoint:** `POST /api/v1/projects/validate`

**Description:** Validate project data before creation

**Request Schema:**
```json
{
  "name": "string (required)",
  "description": "string (nullable)",
  "settings": {
    "voice_id": "string",
    "language": "string",
    "audio_format": "string",
    "bitrate": "integer"
  }
}
```

**Response Schema (200 OK):**
```json
{
  "success": true,
  "data": {
    "valid": "boolean",
    "errors": {}
  }
}
```

---

## Error Responses

### Standard Error Format
```json
{
  "success": false,
  "message": "string",
  "errors": {}
}
```

### HTTP Status Codes
| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

---

## Rate Limiting
- API requests: 60 requests/minute per user
- Project creation: 10 projects/hour per user
