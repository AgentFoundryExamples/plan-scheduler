# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 30
- **Intra-repo dependencies**: 49
- **External stdlib dependencies**: 20
- **External third-party dependencies**: 25

## External Dependencies

### Standard Library / Core Modules

Total: 20 unique modules

- `base64`
- `contextlib.asynccontextmanager`
- `contextvars`
- `datetime.UTC`
- `datetime.datetime`
- `enum.Enum`
- `functools.lru_cache`
- `hashlib`
- `json`
- `logging`
- `os`
- `secrets`
- `sys`
- `time`
- `typing.Any`
- `unittest.mock.MagicMock`
- `unittest.mock.patch`
- `uuid`
- `uuid.UUID`
- `uuid.uuid4`

### Third-Party Packages

Total: 25 unique packages

- `fastapi.APIRouter`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Header`
- `fastapi.Query`
- `fastapi.Request`
- `fastapi.Response`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `google.api_core.exceptions`
- `google.auth.exceptions`
- `google.auth.exceptions.GoogleAuthError`
- `google.auth.exceptions.InvalidValue`
- `google.auth.jwt`
- `google.cloud.firestore`
- `pydantic.BaseModel`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic.field_validator`
- `pydantic.model_validator`
- ... and 5 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/models/plan.py` (12 dependents)
- `app/services/firestore_service.py` (9 dependents)
- `app/config.py` (8 dependents)
- `app/services/execution_service.py` (4 dependents)
- `app/main.py` (4 dependents)
- `app/dependencies.py` (3 dependents)
- `app/auth.py` (3 dependents)
- `app/models/pubsub.py` (3 dependents)
- `app/api/health.py` (1 dependents)
- `app/api/plans.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/api/pubsub.py` (6 dependencies)
- `app/dependencies.py` (4 dependencies)
- `app/main.py` (4 dependencies)
- `tests/test_pubsub_api.py` (4 dependencies)
- `app/api/plans.py` (3 dependencies)
- `app/services/firestore_service.py` (3 dependencies)
- `tests/test_dependencies.py` (3 dependencies)
- `tests/test_execution_service.py` (3 dependencies)
- `tests/test_plans_api.py` (3 dependencies)
- `app/services/execution_service.py` (2 dependencies)
