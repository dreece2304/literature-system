# Literature Database API Reference

Complete API documentation for the literature-database service running on port 8001.

## 🌐 Service Information

- **Base URL**: `http://localhost:8001` (development) | `http://api-gateway/literature-database` (production)
- **API Version**: `v1`
- **API Docs**: `http://localhost:8001/docs` (Swagger UI)
- **OpenAPI Schema**: `http://localhost:8001/openapi.json`
- **Service Port**: `8001`

## 🔧 Core Endpoints

### Health Check

**GET** `/health`

Service health and status check.

```bash
curl http://localhost:8001/health
```

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "service": "literature-database",
  "version": "1.0.0",
  "timestamp": "2025-01-09T10:30:00Z",
  "database": {
    "status": "connected",
    "papers_count": 323,
    "collections_count": 8,
    "events": {
      "status": "connected",
      "redis_url": "redis://localhost:6379",
      "enabled": true
    }
  },
  "search_index": {
    "status": "ready",
    "documents_indexed": 323,
    "last_updated": "2025-01-09T09:15:00Z"
  }
}
```

---

## 📚 Papers API

### List Papers

**GET** `/api/v1/papers`

List papers with pagination and optional filtering.

**Query Parameters:**
- `skip` (int, default=0): Number of items to skip
- `limit` (int, default=20, max=100): Number of items per page
- `author` (string): Filter by author name
- `tag` (string): Filter by tag name  
- `year` (int): Filter by publication year
- `journal` (string): Filter by journal name
- `collection` (string): Filter by collection name

**Example Request:**
```bash
curl "http://localhost:8001/api/v1/papers?limit=5&year=2023&author=Smith"
```

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": 1,
      "title": "Advanced Materials for Energy Storage",
      "abstract": "This paper explores novel materials for battery applications...",
      "year": 2023,
      "doi": "10.1038/s41586-023-05678-9",
      "arxiv_id": null,
      "pubmed_id": null,
      "journal": "Nature",
      "volume": "615",
      "issue": "7950",
      "pages": "123-130",
      "publisher": "Nature Publishing Group",
      "rating": 5,
      "read_status": "read",
      "file_path": "/data/pdfs/2023/smith_advanced_materials.pdf",
      "file_hash": "a1b2c3d4e5f6...",
      "zotero_key": "ABC123DEF",
      "zotero_version": 42,
      "date_added": "2025-01-08T14:30:00Z",
      "date_modified": "2025-01-09T09:15:00Z",
      "date_read": "2025-01-08T16:45:00Z",
      "word_count": 8750,
      "authors": [
        {
          "id": 1,
          "name": "John Smith",
          "orcid": "0000-0000-0000-0001",
          "email": "j.smith@university.edu",
          "affiliation": "University Research Center"
        }
      ],
      "tags": [
        {
          "id": 1,
          "name": "Materials Science",
          "category": "field",
          "color": "#FF6B6B"
        }
      ],
      "collections": [
        {
          "id": 1,
          "name": "Energy Storage Research",
          "description": "Papers related to battery and energy storage",
          "parent_id": null,
          "zotero_key": "COL123"
        }
      ]
    }
  ],
  "total": 323,
  "skip": 0,
  "limit": 5,
  "has_next": true
}
```

### Get Single Paper

**GET** `/api/v1/papers/{id}`

Retrieve a specific paper by ID.

**Path Parameters:**
- `id` (int): Paper ID

**Example Request:**
```bash
curl http://localhost:8001/api/v1/papers/1
```

**Response** `200 OK`:
```json
{
  "id": 1,
  "title": "Advanced Materials for Energy Storage",
  // ... (same structure as list papers)
}
```

**Error Response** `404 Not Found`:
```json
{
  "detail": "Paper not found"
}
```

### Create Paper

**POST** `/api/v1/papers`

Create a new paper entry.

**Request Body:**
```json
{
  "title": "New Research Paper Title",
  "abstract": "Abstract text here...",
  "year": 2024,
  "doi": "10.1000/xyz123",
  "arxiv_id": "2024.01234v1",
  "pubmed_id": "38123456",
  "journal": "Journal of Advanced Research",
  "volume": "15",
  "issue": "3",
  "pages": "45-67",
  "publisher": "Academic Press",
  "rating": 4,
  "read_status": "unread",
  "file_path": "/data/pdfs/new_paper.pdf",
  "authors": ["Jane Doe", "John Smith"],
  "tags": ["Machine Learning", "Data Analysis"],
  "collections": ["AI Research"]
}
```

**Response** `201 Created`:
```json
{
  "id": 324,
  "title": "New Research Paper Title",
  // ... (full paper object)
}
```

**Error Response** `400 Bad Request`:
```json
{
  "detail": "Paper with DOI 10.1000/xyz123 already exists"
}
```

### Update Paper

**PUT** `/api/v1/papers/{id}`

Update an existing paper.

**Path Parameters:**
- `id` (int): Paper ID

**Request Body** (partial update supported):
```json
{
  "rating": 5,
  "read_status": "read",
  "date_read": "2025-01-09T15:30:00Z",
  "tags": ["Machine Learning", "Deep Learning", "Computer Vision"]
}
```

**Response** `200 OK`:
```json
{
  "id": 1,
  "title": "Advanced Materials for Energy Storage",
  // ... (updated paper object)
}
```

### Delete Paper

**DELETE** `/api/v1/papers/{id}`

Delete a paper and associated files.

**Path Parameters:**
- `id` (int): Paper ID

**Response** `204 No Content`

**Error Response** `404 Not Found`:
```json
{
  "detail": "Paper not found"
}
```

---

## 🔍 Search API

### Full-Text Search

**POST** `/api/v1/search`

Perform full-text search across papers.

**Request Body:**
```json
{
  "query": "machine learning neural networks",
  "limit": 20,
  "filters": {
    "year": 2023,
    "journal": "Nature",
    "author": "Smith"
  }
}
```

**Response** `200 OK`:
```json
{
  "query": "machine learning neural networks",
  "total_results": 15,
  "papers": [
    {
      "id": 42,
      "title": "Deep Neural Networks for Pattern Recognition",
      "abstract": "This study presents novel approaches...",
      // ... (full paper objects)
      "search_score": 0.95,
      "search_highlights": [
        "...applications of <em>machine learning</em> in modern...",
        "...using <em>neural networks</em> for classification..."
      ]
    }
  ],
  "facets": {
    "years": {"2023": 8, "2022": 5, "2021": 2},
    "journals": {"Nature": 4, "Science": 3, "Cell": 2},
    "tags": {"Machine Learning": 12, "AI": 8, "Computer Vision": 5}
  },
  "suggestions": ["machine learning algorithms", "deep neural networks"],
  "query_time_ms": 45
}
```

### Search Suggestions

**GET** `/api/v1/search/suggestions`

Get search query suggestions.

**Query Parameters:**
- `q` (string): Partial query text
- `field` (string, default="title"): Field to search for suggestions

**Example Request:**
```bash
curl "http://localhost:8001/api/v1/search/suggestions?q=machine&field=title"
```

**Response** `200 OK`:
```json
{
  "suggestions": [
    "machine learning",
    "machine vision",
    "machine intelligence"
  ]
}
```

---

## 🔄 Synchronization API

### Zotero Sync

**POST** `/api/v1/sync/zotero`

Trigger synchronization with Zotero library.

**Request Body** (optional):
```json
{
  "force_full_sync": false,
  "sync_attachments": true,
  "collection_keys": ["ABC123", "DEF456"]
}
```

**Response** `202 Accepted`:
```json
{
  "sync_id": "sync_20250109_103045",
  "status": "started",
  "message": "Zotero synchronization initiated",
  "estimated_duration_minutes": 5
}
```

### Sync Status

**GET** `/api/v1/sync/zotero/{sync_id}`

Check status of ongoing or completed sync.

**Path Parameters:**
- `sync_id` (string): Sync operation ID

**Response** `200 OK`:
```json
{
  "sync_id": "sync_20250109_103045",
  "status": "completed",
  "started_at": "2025-01-09T10:30:45Z",
  "completed_at": "2025-01-09T10:35:12Z",
  "duration_seconds": 267,
  "results": {
    "papers_processed": 15,
    "papers_added": 3,
    "papers_updated": 7,
    "papers_unchanged": 5,
    "attachments_linked": 12,
    "errors": 0
  },
  "log_messages": [
    "Starting Zotero sync...",
    "Connected to Zotero library",
    "Processing 15 items",
    "Sync completed successfully"
  ]
}
```

---

## 📁 Collections API

### List Collections

**GET** `/api/v1/collections`

List all collections with hierarchy.

**Response** `200 OK`:
```json
{
  "collections": [
    {
      "id": 1,
      "name": "Energy Storage Research",
      "description": "Papers related to battery and energy storage",
      "parent_id": null,
      "zotero_key": "COL123",
      "paper_count": 45,
      "children": [
        {
          "id": 2,
          "name": "Lithium-ion Batteries",
          "description": "Specific to Li-ion technology",
          "parent_id": 1,
          "zotero_key": "COL456",
          "paper_count": 23,
          "children": []
        }
      ]
    }
  ]
}
```

### Get Collection Papers

**GET** `/api/v1/collections/{id}/papers`

Get papers in a specific collection.

**Path Parameters:**
- `id` (int): Collection ID

**Query Parameters:**
- `skip` (int, default=0): Number of items to skip
- `limit` (int, default=20): Number of items per page

**Response** `200 OK`:
```json
{
  "collection": {
    "id": 1,
    "name": "Energy Storage Research",
    "description": "Papers related to battery and energy storage"
  },
  "papers": [
    // ... (array of paper objects)
  ],
  "total": 45,
  "skip": 0,
  "limit": 20
}
```

---

## 📊 Statistics API

### Service Statistics

**GET** `/api/v1/stats`

Get comprehensive service statistics.

**Response** `200 OK`:
```json
{
  "database": {
    "papers": 323,
    "authors": 1247,
    "tags": 89,
    "collections": 12,
    "notes": 156,
    "citations": 2341
  },
  "content": {
    "papers_with_pdfs": 289,
    "pdf_coverage_percent": 89.5,
    "total_word_count": 2847562,
    "average_words_per_paper": 8815
  },
  "activity": {
    "papers_added_last_week": 5,
    "papers_read_last_week": 12,
    "last_sync": "2025-01-08T14:30:00Z",
    "most_active_collections": [
      {"name": "Machine Learning", "papers": 67},
      {"name": "Materials Science", "papers": 54}
    ]
  },
  "search_index": {
    "status": "healthy",
    "documents_indexed": 323,
    "index_size_mb": 145,
    "last_updated": "2025-01-09T09:15:00Z"
  }
}
```

---

## 🔐 Authentication & Headers

### Required Headers

```http
Content-Type: application/json
Accept: application/json
```

### Authentication (Future)

The service currently runs without authentication in development. In production with API Gateway:

```http
Authorization: Bearer <jwt_token>
X-API-Key: <api_key>
```

---

## 📡 Event Schemas (WebSockets)

### Connection

**WebSocket**: `ws://localhost:8001/ws/events`

### Event Types

#### Paper Events

**Paper Created:**
```json
{
  "event_type": "paper.created",
  "timestamp": "2025-01-09T10:30:00Z",
  "data": {
    "paper_id": 324,
    "title": "New Research Paper",
    "created_by": "user_123"
  }
}
```

**Paper Updated:**
```json
{
  "event_type": "paper.updated",
  "timestamp": "2025-01-09T10:30:00Z",
  "data": {
    "paper_id": 42,
    "title": "Updated Paper Title",
    "changes": ["title", "rating", "tags"],
    "updated_by": "user_123"
  }
}
```

#### Sync Events

**Sync Started:**
```json
{
  "event_type": "sync.started",
  "timestamp": "2025-01-09T10:30:00Z",
  "data": {
    "sync_id": "sync_20250109_103045",
    "sync_type": "zotero",
    "initiated_by": "user_123"
  }
}
```

**Sync Progress:**
```json
{
  "event_type": "sync.progress",
  "timestamp": "2025-01-09T10:32:15Z",
  "data": {
    "sync_id": "sync_20250109_103045",
    "progress_percent": 65,
    "items_processed": 195,
    "items_total": 300,
    "current_item": "Processing: Advanced AI Methods"
  }
}
```

#### Search Events

**Search Performed:**
```json
{
  "event_type": "search.performed",
  "timestamp": "2025-01-09T10:30:00Z",
  "data": {
    "query": "machine learning",
    "results_count": 23,
    "query_time_ms": 45,
    "user_id": "user_123"
  }
}
```

---

## 🚦 Error Handling

### Standard Error Format

```json
{
  "detail": "Detailed error message",
  "error_code": "PAPER_NOT_FOUND",
  "timestamp": "2025-01-09T10:30:00Z",
  "request_id": "req_123456789"
}
```

### HTTP Status Codes

- **200 OK**: Successful GET/PUT
- **201 Created**: Successful POST
- **204 No Content**: Successful DELETE
- **400 Bad Request**: Invalid request data
- **401 Unauthorized**: Authentication required
- **403 Forbidden**: Access denied
- **404 Not Found**: Resource not found
- **409 Conflict**: Resource conflict (e.g., duplicate DOI)
- **422 Unprocessable Entity**: Validation error
- **500 Internal Server Error**: Server error
- **503 Service Unavailable**: Service temporarily unavailable

### Validation Errors

```json
{
  "detail": "Validation error",
  "errors": [
    {
      "field": "title",
      "message": "Title is required and must be at least 3 characters",
      "code": "FIELD_REQUIRED"
    },
    {
      "field": "year",
      "message": "Year must be between 1800 and 2030",
      "code": "VALUE_OUT_OF_RANGE"
    }
  ]
}
```

---

## 📡 Event Publishing

The literature-database service publishes real-time events to Redis channels for cross-service integration and monitoring.

### Configuration

Events are published to Redis using the `REDIS_URL` environment variable:

```bash
# Set Redis connection (defaults to redis://localhost:6379)
export REDIS_URL=redis://localhost:6379

# Start Redis server
redis-server
```

### Event Structure

All events follow a consistent structure:

```json
{
  "event_type": "paper.added",
  "timestamp": "2025-01-09T10:30:00Z",
  "service": "literature-database",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "paper_id": 123,
  "paper_title": "Advanced Materials Research",
  "metadata": {
    "doi": "10.1000/xyz123",
    "year": 2024,
    "journal": "Nature Materials"
  }
}
```

### Published Events

#### Paper Events

**paper.added** - Published when a new paper is created
```json
{
  "event_type": "paper.added",
  "timestamp": "2025-01-09T10:30:00Z",
  "service": "literature-database",
  "event_id": "uuid",
  "paper_id": 324,
  "paper_title": "New Research Paper",
  "metadata": {
    "doi": "10.1000/xyz123",
    "year": 2024,
    "journal": "Nature"
  }
}
```

**paper.updated** - Published when a paper is modified
```json
{
  "event_type": "paper.updated",
  "timestamp": "2025-01-09T10:30:00Z",
  "service": "literature-database",
  "event_id": "uuid",
  "paper_id": 42,
  "paper_title": "Updated Paper Title",
  "changes": ["title", "rating", "tags"],
  "metadata": {
    "updated_fields": ["title", "rating", "tags"],
    "doi": "10.1000/abc456",
    "year": 2023
  }
}
```

**paper.deleted** - Published when a paper is removed
```json
{
  "event_type": "paper.deleted",
  "timestamp": "2025-01-09T10:30:00Z",
  "service": "literature-database",
  "event_id": "uuid",
  "paper_id": 123,
  "paper_title": "Deleted Paper",
  "metadata": {
    "doi": "10.1000/deleted123",
    "year": 2022,
    "journal": "Science"
  }
}
```

#### Sync Events

**sync.completed** - Published when Zotero sync finishes
```json
{
  "event_type": "sync.completed",
  "timestamp": "2025-01-09T10:35:00Z",
  "service": "literature-database",
  "event_id": "uuid",
  "sync_id": "sync_20250109_103045",
  "sync_type": "zotero",
  "results": {
    "papers_processed": 15,
    "papers_added": 3,
    "papers_updated": 7,
    "papers_unchanged": 5,
    "attachments_linked": 12,
    "errors": 0
  },
  "duration_seconds": 267,
  "papers_processed": 15
}
```

### Event Consumption

#### Python Example

```python
import redis
import json

# Connect to Redis
r = redis.from_url("redis://localhost:6379", decode_responses=True)

# Subscribe to events
pubsub = r.pubsub()
pubsub.subscribe('paper.added', 'paper.updated', 'paper.deleted', 'sync.completed')

# Listen for events
for message in pubsub.listen():
    if message['type'] == 'message':
        event = json.loads(message['data'])
        print(f"Event: {event['event_type']} - Paper: {event.get('paper_title')}")
        
        # Handle specific events
        if event['event_type'] == 'paper.added':
            print(f"New paper added: {event['paper_title']}")
        elif event['event_type'] == 'sync.completed':
            print(f"Sync completed: {event['results']['papers_added']} papers added")
```

#### Node.js Example

```javascript
const redis = require('redis');
const client = redis.createClient({ url: 'redis://localhost:6379' });

client.on('message', (channel, message) => {
    const event = JSON.parse(message);
    console.log(`Event: ${event.event_type} - Paper: ${event.paper_title}`);
    
    // Handle specific events
    switch (event.event_type) {
        case 'paper.added':
            console.log(`New paper: ${event.paper_title}`);
            break;
        case 'sync.completed':
            console.log(`Sync done: ${event.results.papers_added} papers added`);
            break;
    }
});

// Subscribe to channels
client.subscribe('paper.added', 'paper.updated', 'paper.deleted', 'sync.completed');
```

### Event Channels

Events are published to Redis channels matching their event type:

- **paper.added** - Paper creation events
- **paper.updated** - Paper modification events
- **paper.deleted** - Paper deletion events
- **sync.completed** - Sync completion events

### Event Reliability

- **Graceful Degradation**: Service continues operating if Redis is unavailable
- **Health Monitoring**: Redis connection status included in `/health` endpoint
- **Logging**: All events are logged even if Redis publishing fails
- **No Data Loss**: Core functionality unaffected by event publishing failures

---

## 📈 Rate Limiting

Development (no limits):
- All endpoints: Unlimited

Production (via API Gateway):
- **Search**: 100 requests/minute per user
- **CRUD operations**: 1000 requests/minute per user  
- **Sync operations**: 5 requests/minute per user

---

## 🔧 Development Tools

### API Testing

```bash
# Health check
curl http://localhost:8001/health

# List papers
curl http://localhost:8001/api/v1/papers

# Search papers
curl -X POST http://localhost:8001/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 5}'

# Trigger sync
curl -X POST http://localhost:8001/api/v1/sync/zotero \
  -H "Content-Type: application/json" \
  -d '{"force_full_sync": false}'
```

### Swagger UI

Access interactive API documentation:
- **Development**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

---

**Literature Database API Ready for Integration! 🚀**