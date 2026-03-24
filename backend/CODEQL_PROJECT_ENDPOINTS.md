# CodeQL Project Management Endpoints

This document describes the FastAPI endpoints for managing CodeQL project configurations.

## Overview

These endpoints allow you to:
- Add new projects for CodeQL analysis
- List all configured projects
- Get details of a specific project
- Remove projects from the registry

All projects are persisted in `codeql_projects.json` in the backend directory.

## Endpoints

### POST /api/codeql/projects

Create a new CodeQL project configuration.

**Requirements:** 6.1, 6.4, 6.6

**Request Body:**
```json
{
  "name": "Backend API",
  "source_path": "/path/to/source/code",
  "language": "java",
  "database_path": "/path/to/codeql/database"
}
```

**Supported Languages:**
- java
- javascript
- typescript
- python
- csharp
- cpp
- go
- ruby

**Response (201 Created):**
```json
{
  "id": "uuid-generated",
  "name": "Backend API",
  "source_path": "/path/to/source/code",
  "language": "java",
  "database_path": "/path/to/codeql/database",
  "created_at": "2024-01-20T10:30:00",
  "last_analyzed": null
}
```

**Error Responses:**
- `400 Bad Request`: Source path does not exist or language not supported
- `422 Unprocessable Entity`: Missing required fields
- `500 Internal Server Error`: Failed to create project

**Example:**
```bash
curl -X POST http://localhost:8000/api/codeql/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Java Project",
    "source_path": "/home/user/projects/my-app",
    "language": "java",
    "database_path": "/home/user/codeql-dbs/my-app"
  }'
```

---

### GET /api/codeql/projects

List all configured CodeQL projects.

**Requirements:** 6.2

**Response (200 OK):**
```json
[
  {
    "id": "uuid-1",
    "name": "Backend API",
    "source_path": "/path/to/backend",
    "language": "java",
    "database_path": "/path/to/db/backend",
    "created_at": "2024-01-20T10:30:00",
    "last_analyzed": "2024-01-21T14:22:00"
  },
  {
    "id": "uuid-2",
    "name": "Frontend App",
    "source_path": "/path/to/frontend",
    "language": "typescript",
    "database_path": "/path/to/db/frontend",
    "created_at": "2024-01-20T11:00:00",
    "last_analyzed": null
  }
]
```

**Example:**
```bash
curl http://localhost:8000/api/codeql/projects
```

---

### GET /api/codeql/projects/{project_id}

Get details of a specific CodeQL project.

**Requirements:** 6.3

**Path Parameters:**
- `project_id` (string): UUID of the project

**Response (200 OK):**
```json
{
  "id": "uuid-1",
  "name": "Backend API",
  "source_path": "/path/to/backend",
  "language": "java",
  "database_path": "/path/to/db/backend",
  "created_at": "2024-01-20T10:30:00",
  "last_analyzed": "2024-01-21T14:22:00"
}
```

**Error Responses:**
- `404 Not Found`: Project does not exist
- `500 Internal Server Error`: Failed to retrieve project

**Example:**
```bash
curl http://localhost:8000/api/codeql/projects/uuid-1
```

---

### DELETE /api/codeql/projects/{project_id}

Remove a CodeQL project from the registry.

**Requirements:** 6.3

**Path Parameters:**
- `project_id` (string): UUID of the project to delete

**Response (204 No Content):**
No response body.

**Error Responses:**
- `404 Not Found`: Project does not exist
- `500 Internal Server Error`: Failed to delete project

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/codeql/projects/uuid-1
```

---

## Data Models

### CodeQLProjectCreateRequest

Request model for creating a new project.

**Fields:**
- `name` (string, required): Display name for the project
- `source_path` (string, required): Absolute path to source code
- `language` (string, required): Programming language
- `database_path` (string, required): Path where CodeQL database will be stored

### CodeQLProjectResponse

Response model for project data.

**Fields:**
- `id` (string): UUID generated for the project
- `name` (string): Display name
- `source_path` (string): Absolute path to source code
- `language` (string): Programming language
- `database_path` (string): Path to CodeQL database
- `created_at` (string): ISO 8601 timestamp of creation
- `last_analyzed` (string | null): ISO 8601 timestamp of last analysis

---

## Validation Rules

1. **Source Path Validation:**
   - Must exist on the filesystem
   - Validated before project creation

2. **Language Validation:**
   - Must be one of the supported languages
   - Case-insensitive (converted to lowercase)

3. **Required Fields:**
   - All fields in CodeQLProjectCreateRequest are required
   - FastAPI automatically validates presence

4. **ID Generation:**
   - UUIDs are automatically generated
   - Guaranteed to be unique

---

## Persistence

Projects are stored in `codeql_projects.json` with the following structure:

```json
{
  "projects": [
    {
      "id": "uuid-1",
      "name": "Backend API",
      "source_path": "/path/to/backend",
      "language": "java",
      "database_path": "/path/to/db/backend",
      "created_at": "2024-01-20T10:30:00",
      "last_analyzed": "2024-01-21T14:22:00"
    }
  ]
}
```

The file is automatically created if it doesn't exist and is updated on every project modification.

---

## Integration with Analysis Workflow

These endpoints are used by the CodeQL analysis workflow:

1. **Project Configuration:** Users add projects via POST /api/codeql/projects
2. **Project Selection:** Frontend lists projects via GET /api/codeql/projects
3. **Analysis Execution:** Orchestrator retrieves project details for analysis
4. **Timestamp Updates:** `last_analyzed` is updated after successful analysis

---

## Error Handling

All endpoints follow consistent error handling:

- **400 Bad Request:** Invalid input (path doesn't exist, unsupported language)
- **404 Not Found:** Resource not found (project ID doesn't exist)
- **422 Unprocessable Entity:** Validation error (missing required fields)
- **500 Internal Server Error:** Unexpected server error

Error responses include a `detail` field with a descriptive message:

```json
{
  "detail": "Source path does not exist: /invalid/path"
}
```

---

## Testing

### Manual Testing

Use the provided test script:

```bash
cd backend
python test_project_endpoints_manual.py
```

### Unit Testing

Run the pytest test suite:

```bash
cd backend
pytest test_codeql_project_endpoints.py -v
```

### Integration Testing

Test with a running server:

```bash
# Terminal 1: Start server
cd backend
python main.py

# Terminal 2: Test endpoints
curl -X POST http://localhost:8000/api/codeql/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","source_path":".","language":"python","database_path":"/tmp/test-db"}'

curl http://localhost:8000/api/codeql/projects
```

---

## Future Enhancements

Potential improvements for future versions:

1. **Batch Operations:** Add/delete multiple projects at once
2. **Project Search:** Filter projects by name, language, or last analyzed date
3. **Database Validation:** Check if database exists and is valid
4. **Project Templates:** Pre-configured settings for common project types
5. **Project Groups:** Organize projects into logical groups
6. **Import/Export:** Bulk import/export project configurations
7. **Project Statistics:** Show database size, analysis history, etc.

---

## Related Documentation

- [CodeQL Models](./codeql_models.py) - Data models and persistence layer
- [CodeQL Orchestrator](./codeql_orchestrator.py) - Analysis workflow coordination
- [Design Document](../.kiro/specs/autonomous-codeql-analysis/design.md) - System architecture
- [Requirements](../.kiro/specs/autonomous-codeql-analysis/requirements.md) - Detailed requirements
