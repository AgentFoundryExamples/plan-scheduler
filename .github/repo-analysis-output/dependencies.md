# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 27
- **Intra-repo dependencies**: 43
- **External stdlib dependencies**: 18
- **External third-party dependencies**: 20

## External Dependencies

### Standard Library / Core Modules

Total: 18 unique modules

- `base64`
- `contextlib.asynccontextmanager`
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
- `typing.Any`
- `unittest.mock.MagicMock`
- `unittest.mock.patch`
- `uuid`
- `uuid.UUID`
- `uuid.uuid4`

### Third-Party Packages

Total: 20 unique packages

- `fastapi.APIRouter`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Header`
- `fastapi.Query`
- `fastapi.Response`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `google.api_core.exceptions`
- `google.auth.exceptions`
- `google.cloud.firestore`
- `pydantic.BaseModel`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic.field_validator`
- `pydantic.model_validator`
- `pydantic_settings.BaseSettings`
- `pydantic_settings.SettingsConfigDict`
- `pytest`
- `pythonjsonlogger.json.JsonFormatter`

## Most Depended Upon Files (Intra-Repo)

- `app/models/plan.py` (12 dependents)
- `app/services/firestore_service.py` (8 dependents)
- `app/config.py` (7 dependents)
- `app/services/execution_service.py` (4 dependents)
- `app/main.py` (4 dependents)
- `app/models/pubsub.py` (3 dependents)
- `app/dependencies.py` (2 dependents)
- `app/api/health.py` (1 dependents)
- `app/api/plans.py` (1 dependents)
- `app/api/pubsub.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/api/pubsub.py` (5 dependencies)
- `app/dependencies.py` (4 dependencies)
- `app/main.py` (4 dependencies)
- `app/api/plans.py` (3 dependencies)
- `app/services/firestore_service.py` (3 dependencies)
- `tests/test_dependencies.py` (3 dependencies)
- `tests/test_execution_service.py` (3 dependencies)
- `tests/test_plans_api.py` (3 dependencies)
- `tests/test_pubsub_api.py` (3 dependencies)
- `app/services/execution_service.py` (2 dependencies)
