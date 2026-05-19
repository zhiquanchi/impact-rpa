# Go Backend Specification for Remote Config Sync

This document provides technical instructions for implementing the Go-based backend for the RPA configuration synchronization service.

## 1. System Overview
The service acts as a simple JSON storage for user configurations, keyed by a machine hardware fingerprint (`UID`).

## 2. API Endpoints

### 2.1 Get Configuration (Pull)
*   **Method:** `GET`
*   **Path:** `/api/sync/:uid`
*   **Success Response (200 OK):**
    ```json
    {
      "settings": { ... },
      "templates_data": { ... },
      "updated_at": "2023-10-27T10:00:00Z"
    }
    ```
*   **Error Response (404 Not Found):** If no data exists for the given UID.

### 2.2 Update Configuration (Push)
*   **Method:** `POST`
*   **Path:** `/api/sync/:uid`
*   **Request Body:**
    ```json
    {
      "settings": { ... },       // Optional: Only sent if settings changed
      "templates_data": { ... }  // Optional: Only sent if templates changed
    }
    ```
*   **Implementation Note:** Use "Upsert" logic. If the UID exists, merge/update the fields; if not, create a new record.
*   **Success Response (200 OK):** `{"status": "success"}`

## 3. Recommended Go Implementation (Gin + SQLite)

### 3.1 Data Model
```go
type UserSync struct {
    UID           string `gorm:"primaryKey"`
    Settings      string `gorm:"type:text"` // Store as JSON string
    TemplatesData string `gorm:"type:text"` // Store as JSON string
    UpdatedAt     time.Time
}
```

### 3.2 Key Dependencies
*   **Framework:** `github.com/gin-gonic/gin`
*   **ORM:** `github.com/go-gorm/gorm`
*   **Database:** `github.com/go-gorm/sqlite`

### 3.3 Core Logic Example
```go
// Upsert Logic
var config UserSync
db.FirstOrCreate(&config, UserSync{UID: uid})

if input.Settings != nil {
    config.Settings = string(input.Settings)
}
if input.TemplatesData != nil {
    config.TemplatesData = string(input.TemplatesData)
}
config.UpdatedAt = time.Now()
db.Save(&config)
```

## 4. Security Recommendations
1.  **CORS:** Enable CORS if the client might ever be a browser (not needed for Python CLI).
2.  **Rate Limiting:** Implement simple rate limiting per UID to prevent abuse.
3.  **Validation:** Ensure incoming data is valid JSON before saving.

## 5. Deployment
*   The application should be compiled into a single static binary for Linux/Windows.
*   The `sync.db` (SQLite) should be stored in a persistent volume.
