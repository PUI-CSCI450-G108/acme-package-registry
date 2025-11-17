# Implementation Plan: Missing BASELINE Endpoints

## Overview
Implement 4 missing BASELINE endpoints + fix 1 route mismatch to achieve full API spec compliance.

Based on OpenAPI spec version 3.4.4 review completed 2025-11-16.

---

## Current Status

### ✅ Implemented Endpoints (7/17)
- GET /health
- POST /artifacts (list/query)
- DELETE /reset
- GET /artifacts/{artifact_type}/{id}
- POST /artifact/{artifact_type}
- GET /artifact/model/{id}/rate
- GET /artifact/byName/{name}

### ❌ Missing BASELINE Endpoints (4)
1. PUT /artifacts/{artifact_type}/{id} - Update artifact
2. GET /artifact/{artifact_type}/{id}/cost - Get artifact cost
3. GET /artifact/model/{id}/lineage - Retrieve lineage graph
4. POST /artifact/model/{id}/license-check - License compatibility check

### ⚠️ Route Mismatch (1)
- POST /artifact/search → should be POST /artifact/byRegEx

---

## 1. PUT /artifacts/{artifact_type}/{id} - Update Artifact (BASELINE)

**New file:** `lambda_handlers/update_artifact.py`

### Implementation Details

**Input validation:**
- Validate `artifact_type` in path (model/dataset/code)
- Validate `artifact_id` format (alphanumeric + hyphens)
- Validate `artifact_id` exists in S3
- Parse request body to get `Artifact` envelope with metadata + data
- Ensure name and id in body match the path parameters

**Logic:**
1. Load existing artifact from S3 using `load_artifact_from_s3(artifact_id)`
2. Verify artifact type matches path parameter
3. Validate request body has matching name and id
4. Replace URL/data fields with new values from request body
5. If artifact type is "model":
   - Re-evaluate the model using `evaluate_model(url, artifact_store)`
   - Update rating with fresh metrics
6. Update metadata (keep same id, update name if changed)
7. Save updated artifact back to S3 using `save_artifact_to_s3(artifact_id, artifact_data)`

**Response codes:**
- 200: Artifact updated successfully
- 400: Malformed request, invalid artifact_type, or name/id mismatch
- 403: Authentication failed
- 404: Artifact doesn't exist

**Example Request:**
```json
PUT /artifacts/model/abc123
{
  "metadata": {
    "name": "bert-base-uncased",
    "id": "abc123",
    "type": "model"
  },
  "data": {
    "url": "https://huggingface.co/google-bert/bert-base-uncased"
  }
}
```

**Example Response:**
```json
200 OK
```

**template.yaml changes:**
```yaml
UpdateArtifactFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: .
    Handler: lambda_handlers.update_artifact.handler
    Description: Update artifact content
    FunctionName: acme-registry-update-artifact
    Environment:
      Variables:
        HF_TOKEN: !Ref HuggingFaceToken
        ARTIFACTS_BUCKET: !Ref ArtifactsBucket
    Policies:
      - S3ReadPolicy:
          BucketName: !Ref ArtifactsBucket
      - S3WritePolicy:
          BucketName: !Ref ArtifactsBucket
    Events:
      UpdateArtifactApi:
        Type: HttpApi
        Properties:
          ApiId: !Ref AcmeApiGateway
          Path: /artifacts/{artifact_type}/{id}
          Method: PUT
```

---

## 2. GET /artifact/{artifact_type}/{id}/cost - Get Artifact Cost (BASELINE)

**New file:** `lambda_handlers/get_artifact_cost.py`

### Implementation Details

**Input validation:**
- Validate `artifact_type` in path (model/dataset/code)
- Validate `artifact_id` format and existence
- Parse `dependency` query parameter (boolean, default: false)

**Logic:**
1. Load artifact from S3
2. Get artifact size using new helper function `get_artifact_size(artifact_id)`
   - For HuggingFace models: use `model_info.safetensors` or `model_info.siblings` to calculate total size
   - For datasets: sum file sizes from dataset info
   - Return size in MB (megabytes)
3. Calculate standalone cost = total size in MB
4. If `dependency=false`:
   - Return simple response with only `total_cost`
5. If `dependency=true`:
   - Parse dependencies using `parse_dependencies(model_info)`
   - Recursively fetch dependency sizes
   - Build response with both `standalone_cost` and `total_cost`
   - Include all dependencies in response

**Response format (dependency=false):**
```json
{
  "artifact_id": {
    "total_cost": 412.5
  }
}
```

**Response format (dependency=true):**
```json
{
  "3847247294": {
    "standalone_cost": 412.5,
    "total_cost": 1255.0
  },
  "4628173590": {
    "standalone_cost": 280.0,
    "total_cost": 280.0
  },
  "5738291045": {
    "standalone_cost": 562.5,
    "total_cost": 562.5
  }
}
```

**Response codes:**
- 200: Success
- 400: Malformed artifact_type or artifact_id
- 403: Authentication failed
- 404: Artifact not found
- 500: Cost calculation error

**template.yaml changes:**
```yaml
GetArtifactCostFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: .
    Handler: lambda_handlers.get_artifact_cost.handler
    Description: Get artifact cost with optional dependency calculation
    FunctionName: acme-registry-get-artifact-cost
    Timeout: 60
    MemorySize: 512
    Environment:
      Variables:
        HF_TOKEN: !Ref HuggingFaceToken
        ARTIFACTS_BUCKET: !Ref ArtifactsBucket
    Policies:
      - S3ReadPolicy:
          BucketName: !Ref ArtifactsBucket
    Events:
      GetArtifactCostApi:
        Type: HttpApi
        Properties:
          ApiId: !Ref AcmeApiGateway
          Path: /artifact/{artifact_type}/{id}/cost
          Method: GET
```

**Helper functions needed in `lambda_handlers/utils.py`:**

```python
def get_artifact_size(artifact_id: str, model_info: Any = None) -> float:
    """
    Get artifact size in MB.

    Args:
        artifact_id: Artifact identifier
        model_info: Optional pre-fetched model info

    Returns:
        Size in megabytes
    """
    # Implementation: Extract from HF API safetensors or siblings
    pass


def parse_dependencies(model_info: Any, artifact_data: dict) -> List[str]:
    """
    Parse dependencies from model config.

    Extracts:
    - Base models (from config.json _name_or_path)
    - Datasets (from dataset_tags in model card)
    - Other dependencies

    Args:
        model_info: HuggingFace model info object
        artifact_data: Stored artifact data

    Returns:
        List of dependency artifact IDs
    """
    pass


def calculate_dependency_costs(
    artifact_id: str,
    visited: Optional[Set[str]] = None
) -> Dict[str, Dict[str, float]]:
    """
    Recursively calculate costs for artifact and dependencies.

    Returns dict mapping artifact_id to cost breakdown.
    """
    pass
```

---

## 3. GET /artifact/model/{id}/lineage - Get Lineage Graph (BASELINE)

**New file:** `lambda_handlers/get_artifact_lineage.py`

### Implementation Details

**Input validation:**
- Validate `artifact_id` from path
- Verify artifact exists and is type "model"

**Logic:**
1. Load model artifact from S3
2. Fetch model info from HuggingFace to get config.json and model card
3. Extract lineage information using `extract_lineage_from_config(model_info)`
4. Build graph structure with `build_lineage_graph(artifact_id, model_info)`
5. Return graph with nodes and edges

**Lineage extraction sources:**
- **config.json** - base model references, architecture
- **Model card** - dataset tags, training data references
- **Artifact metadata** - stored relationships

**Graph structure:**
- **Nodes:** Each artifact (model, dataset, code) with metadata
  - `artifact_id`: Unique identifier (may be external if not in our registry)
  - `name`: Human-readable name
  - `source`: Where discovered (config_json, model_card, dataset_tags, etc.)
  - `metadata`: Additional context

- **Edges:** Directed relationships
  - `from_node_artifact_id`: Upstream dependency
  - `to_node_artifact_id`: Downstream dependent
  - `relationship`: Type (fine_tuning_dataset, base_model, etc.)

**Response format:**
```json
{
  "nodes": [
    {
      "artifact_id": "3847247294",
      "name": "audience-classifier",
      "source": "config_json",
      "metadata": {
        "repository_url": "https://huggingface.co/...",
        "sha": "23c9e8adf2"
      }
    },
    {
      "artifact_id": "5738291045",
      "name": "bookcorpus",
      "source": "upstream_dataset"
    }
  ],
  "edges": [
    {
      "from_node_artifact_id": "5738291045",
      "to_node_artifact_id": "3847247294",
      "relationship": "fine_tuning_dataset"
    }
  ]
}
```

**Response codes:**
- 200: Lineage graph computed successfully
- 400: Malformed metadata, cannot compute graph
- 403: Authentication failed
- 404: Artifact not found

**template.yaml changes:**
```yaml
GetArtifactLineageFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: .
    Handler: lambda_handlers.get_artifact_lineage.handler
    Description: Retrieve lineage graph for artifact
    FunctionName: acme-registry-get-artifact-lineage
    Timeout: 60
    MemorySize: 512
    Environment:
      Variables:
        HF_TOKEN: !Ref HuggingFaceToken
        ARTIFACTS_BUCKET: !Ref ArtifactsBucket
    Policies:
      - S3ReadPolicy:
          BucketName: !Ref ArtifactsBucket
    Events:
      GetArtifactLineageApi:
        Type: HttpApi
        Properties:
          ApiId: !Ref AcmeApiGateway
          Path: /artifact/model/{id}/lineage
          Method: GET
```

**Helper functions needed in `lambda_handlers/utils.py`:**

```python
def extract_lineage_from_config(model_info: Any) -> Dict[str, Any]:
    """
    Extract lineage nodes and edges from model config.

    Parses:
    - config.json for base models (_name_or_path, model_type)
    - Model card for dataset references
    - Training arguments for data paths

    Returns:
        Dict with 'nodes' and 'edges' lists
    """
    pass


def build_lineage_graph(artifact_id: str, model_info: Any) -> Dict[str, Any]:
    """
    Construct complete lineage graph structure.

    Args:
        artifact_id: Root artifact ID
        model_info: HuggingFace model info

    Returns:
        Complete graph with nodes and edges per spec schema
    """
    pass


def resolve_artifact_id_from_name(name: str, artifact_type: str) -> Optional[str]:
    """
    Look up artifact ID from name in S3 registry.

    Used to link external references to stored artifacts.
    """
    pass
```

---

## 4. POST /artifact/model/{id}/license-check - License Compatibility (BASELINE)

**New file:** `lambda_handlers/check_artifact_license.py`

### Implementation Details

**Input validation:**
- Validate `artifact_id` from path
- Verify artifact exists and is type "model"
- Parse request body: `{"github_url": "https://github.com/..."}`
- Validate GitHub URL format

**Logic:**
1. Load model artifact from S3
2. Get model's license from HuggingFace metadata using existing model info
3. Fetch license from GitHub repository using GitHub API
4. Check compatibility using `check_license_compatibility(model_license, github_license)`
5. Return boolean result

**License compatibility rules:**
- **MIT, Apache-2.0, BSD-3-Clause:** Compatible with most uses
- **GPL-3.0:** Compatible if downstream project is also GPL
- **LGPL:** Compatible for linking/using, may restrict modification
- **Custom licenses:** Parse and evaluate based on common patterns
- **No license / Unknown:** Return false (conservative approach)

**Compatibility matrix:**

| Model License | GitHub License | Compatible? | Notes |
|--------------|----------------|-------------|-------|
| MIT | MIT/Apache/BSD/GPL | ✓ | Permissive |
| Apache-2.0 | MIT/Apache/BSD/GPL | ✓ | Permissive |
| GPL-3.0 | GPL-3.0 | ✓ | Copyleft compatible |
| GPL-3.0 | MIT/Apache | ✗ | GPL more restrictive |
| MIT | GPL-3.0 | ✓ | Can use GPL code in MIT |
| Unknown | Any | ✗ | Conservative |

**Response format:** Boolean `true` or `false`

**Example Request:**
```json
POST /artifact/model/abc123/license-check
{
  "github_url": "https://github.com/google-research/bert"
}
```

**Example Response:**
```json
true
```

**Response codes:**
- 200: License check completed successfully
- 400: Malformed request (invalid github_url)
- 403: Authentication failed
- 404: Artifact or GitHub repository not found
- 502: External license information retrieval failed (GitHub API error)

**template.yaml changes:**
```yaml
CheckArtifactLicenseFunction:
  Type: AWS::Serverless::Function
  Properties:
    CodeUri: .
    Handler: lambda_handlers.check_artifact_license.handler
    Description: Check license compatibility for artifact
    FunctionName: acme-registry-check-artifact-license
    Timeout: 30
    MemorySize: 256
    Environment:
      Variables:
        HF_TOKEN: !Ref HuggingFaceToken
        ARTIFACTS_BUCKET: !Ref ArtifactsBucket
    Policies:
      - S3ReadPolicy:
          BucketName: !Ref ArtifactsBucket
    Events:
      CheckArtifactLicenseApi:
        Type: HttpApi
        Properties:
          ApiId: !Ref AcmeApiGateway
          Path: /artifact/model/{id}/license-check
          Method: POST
```

**Helper functions needed in `lambda_handlers/utils.py`:**

```python
def fetch_github_license(github_url: str) -> Optional[str]:
    """
    Fetch license from GitHub repository.

    Uses GitHub API /repos/{owner}/{repo}/license endpoint.

    Args:
        github_url: GitHub repository URL

    Returns:
        License identifier (e.g., "MIT", "Apache-2.0") or None
    """
    pass


def check_license_compatibility(
    model_license: str,
    github_license: str
) -> bool:
    """
    Check if model license is compatible with GitHub project license.

    Evaluates compatibility for:
    - Inference usage
    - Fine-tuning usage
    - Integration into downstream projects

    Args:
        model_license: License from HuggingFace model
        github_license: License from GitHub repo

    Returns:
        True if compatible, False otherwise
    """
    # Leverage existing logic from src/metrics/license.py
    pass


def normalize_license_name(license_str: str) -> str:
    """
    Normalize license string to standard SPDX identifier.

    Examples:
    - "MIT License" → "MIT"
    - "apache-2.0" → "Apache-2.0"
    - "gpl-3.0" → "GPL-3.0"
    """
    pass
```

**Leverage existing code:**
- Use `src/metrics/license.py:compute_license_metric` logic as reference
- Reuse license parsing and evaluation patterns
- Add GitHub API integration for external repo license fetching

---

## 5. Fix Route Mismatch: POST /artifact/search → POST /artifact/byRegEx

### Changes Required

**File: `template.yaml`**

Update the SearchArtifactsFunction route:

```yaml
# BEFORE
SearchArtifactsFunction:
  Events:
    SearchArtifactsApi:
      Type: HttpApi
      Properties:
        ApiId: !Ref AcmeApiGateway
        Path: /artifact/search
        Method: POST

# AFTER
SearchArtifactsFunction:
  Events:
    SearchArtifactsApi:
      Type: HttpApi
      Properties:
        ApiId: !Ref AcmeApiGateway
        Path: /artifact/byRegEx
        Method: POST
```

**File: `lambda_handlers/search_artifacts.py`**

Update docstring and add backward compatibility:

```python
"""
Lambda handler for POST /artifact/byRegEx

Searches for artifacts using regex (name and/or id) and semantic version constraints.
Returns matching artifact *metadata* entries (id, name, version, type).

Supports both spec format and extended format for backward compatibility:
- Spec format: {"regex": "..."}
- Extended format: {"name_regex": "...", "version": "...", "types": [...], "id_regex": "..."}
"""

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # ... existing code ...

    # Parse JSON body
    body = json.loads(raw) if isinstance(raw, str) else raw

    # Support both formats
    if "regex" in body and "name_regex" not in body:
        # Spec format - map to extended format
        body["name_regex"] = body["regex"]

    name_regex = body.get("name_regex")
    # ... rest of existing logic ...
```

**Update function description in template.yaml:**
```yaml
SearchArtifactsFunction:
  Properties:
    Description: Search artifacts by regex and version (implements /artifact/byRegEx endpoint)
```

---

## Summary of Implementation

### New Files to Create (4)
1. `lambda_handlers/update_artifact.py` - PUT /artifacts/{artifact_type}/{id}
2. `lambda_handlers/get_artifact_cost.py` - GET /artifact/{artifact_type}/{id}/cost
3. `lambda_handlers/get_artifact_lineage.py` - GET /artifact/model/{id}/lineage
4. `lambda_handlers/check_artifact_license.py` - POST /artifact/model/{id}/license-check

### Files to Modify (2)
1. `template.yaml`
   - Add 4 new Lambda function resources
   - Update SearchArtifactsFunction route from `/artifact/search` to `/artifact/byRegEx`

2. `lambda_handlers/search_artifacts.py`
   - Update docstring to reference correct endpoint
   - Add support for spec format `{"regex": "..."}` alongside extended format

### New Helper Functions in `lambda_handlers/utils.py` (9)

**Cost Calculation:**
1. `get_artifact_size(artifact_id, model_info) -> float`
2. `parse_dependencies(model_info, artifact_data) -> List[str]`
3. `calculate_dependency_costs(artifact_id, visited) -> Dict[str, Dict[str, float]]`

**Lineage Graph:**
4. `extract_lineage_from_config(model_info) -> Dict[str, Any]`
5. `build_lineage_graph(artifact_id, model_info) -> Dict[str, Any]`
6. `resolve_artifact_id_from_name(name, artifact_type) -> Optional[str]`

**License Compatibility:**
7. `fetch_github_license(github_url) -> Optional[str]`
8. `check_license_compatibility(model_license, github_license) -> bool`
9. `normalize_license_name(license_str) -> str`

---

## Testing Strategy

### Unit Tests
Create test files for each new handler:
- `tests/test_update_artifact.py`
- `tests/test_get_artifact_cost.py`
- `tests/test_get_artifact_lineage.py`
- `tests/test_check_artifact_license.py`

### Test Cases Per Endpoint

**Update Artifact:**
- ✓ Valid update request
- ✗ Artifact doesn't exist (404)
- ✗ Name/ID mismatch (400)
- ✗ Invalid artifact_type (400)
- ✗ Malformed JSON (400)

**Get Cost:**
- ✓ Without dependencies
- ✓ With dependencies (recursive)
- ✗ Artifact not found (404)
- ✗ Invalid dependency query param (400)
- ✗ Cost calculation error (500)

**Get Lineage:**
- ✓ Model with dependencies
- ✓ Model without dependencies (empty graph)
- ✗ Artifact not found (404)
- ✗ Non-model artifact (400)
- ✗ Malformed metadata (400)

**License Check:**
- ✓ Compatible licenses (MIT + MIT)
- ✓ Compatible with copyleft (MIT + GPL)
- ✗ Incompatible licenses (GPL + MIT)
- ✗ GitHub repo not found (404)
- ✗ Invalid GitHub URL (400)
- ✗ GitHub API failure (502)

**Search (byRegEx):**
- ✓ Spec format: `{"regex": "bert.*"}`
- ✓ Extended format: `{"name_regex": "bert.*", "version": "1.0.0"}`
- ✗ Missing regex field (400)
- ✗ Invalid regex pattern (400)

### Integration Tests
- Test full workflow: create → update → get cost → check license
- Test dependency traversal with real artifacts
- Test lineage graph construction with complex models
- Verify all error codes match spec

---

## Implementation Order Recommendation

1. **Fix search endpoint first** (quickest, low risk)
   - Update template.yaml route
   - Add backward compatibility to search_artifacts.py
   - Test both request formats

2. **Implement update artifact** (builds on existing patterns)
   - Create update_artifact.py using existing handlers as template
   - Add to template.yaml
   - Test CRUD operations

3. **Implement cost calculation** (moderate complexity)
   - Create helper functions for size extraction
   - Implement dependency traversal
   - Create get_artifact_cost.py handler

4. **Implement lineage graph** (most complex)
   - Create graph extraction logic
   - Handle external references
   - Create get_artifact_lineage.py handler

5. **Implement license check** (reuses existing code)
   - Add GitHub API integration
   - Leverage existing license.py logic
   - Create check_artifact_license.py handler

---

## Dependencies & External APIs

### HuggingFace API
- Model info extraction (config.json, model card)
- Dataset metadata
- File sizes (safetensors, siblings)

### GitHub API
- License fetching: `GET /repos/{owner}/{repo}/license`
- Rate limiting: Consider caching or token usage
- Endpoint: https://api.github.com

### AWS S3
- Artifact storage/retrieval
- List operations for dependency resolution

---

## Performance Considerations

1. **Cost calculation with dependencies**
   - Cache dependency costs to avoid repeated HF API calls
   - Set reasonable timeout (60s)
   - Consider async processing for large graphs

2. **Lineage graph construction**
   - Limit recursion depth to prevent infinite loops
   - Cache model info lookups
   - Set timeout to 60s

3. **License check**
   - Cache GitHub license results (TTL: 1 hour)
   - Handle GitHub API rate limiting gracefully
   - Consider using conditional requests (ETag)

---

## Security Considerations

1. **GitHub URL validation**
   - Validate URL format before making API calls
   - Prevent SSRF attacks (only allow github.com domain)
   - Sanitize error messages

2. **Dependency traversal**
   - Prevent circular dependencies from causing infinite loops
   - Limit maximum dependency depth
   - Validate all artifact IDs

3. **License compatibility**
   - Conservative approach for unknown licenses
   - Log all license decisions for audit trail
   - Handle edge cases (no license, custom licenses)

---

## Completion Checklist

- [ ] Fix search endpoint route (template.yaml + search_artifacts.py)
- [ ] Implement update_artifact.py handler
- [ ] Implement get_artifact_cost.py handler + helper functions
- [ ] Implement get_artifact_lineage.py handler + helper functions
- [ ] Implement check_artifact_license.py handler + helper functions
- [ ] Update template.yaml with 4 new Lambda functions
- [ ] Write unit tests for all new handlers
- [ ] Write integration tests for end-to-end workflows
- [ ] Update API documentation
- [ ] Deploy and test on AWS
- [ ] Verify all error codes match spec
- [ ] Verify all response schemas match spec
- [ ] Performance testing for dependency/lineage operations
- [ ] Security review for GitHub API integration

---

**Document Version:** 1.0
**Last Updated:** 2025-11-16
**Status:** Ready for implementation
