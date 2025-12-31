# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 21
- **Intra-repo dependencies**: 31
- **External stdlib dependencies**: 16
- **External third-party dependencies**: 18

## External Dependencies

### Standard Library / Core Modules

Total: 16 unique modules

- `contextlib.asynccontextmanager`
- `datetime.UTC`
- `datetime.datetime`
- `enum.Enum`
- `functools.lru_cache`
- `hashlib`
- `json`
- `logging`
- `os`
- `sys`
- `typing.Any`
- `unittest.mock.MagicMock`
- `unittest.mock.patch`
- `uuid`
- `uuid.UUID`
- `uuid.uuid4`

### Third-Party Packages

Total: 18 unique packages

- `fastapi.APIRouter`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
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

- `app/models/plan.py` (10 dependents)
- `app/config.py` (6 dependents)
- `app/services/firestore_service.py` (5 dependents)
- `app/services/execution_service.py` (3 dependents)
- `app/main.py` (3 dependents)
- `app/dependencies.py` (2 dependents)
- `app/api/health.py` (1 dependents)
- `app/api/plans.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/dependencies.py` (4 dependencies)
- `app/api/plans.py` (3 dependencies)
- `app/main.py` (3 dependencies)
- `tests/test_dependencies.py` (3 dependencies)
- `tests/test_execution_service.py` (3 dependencies)
- `tests/test_plans_api.py` (3 dependencies)
- `app/services/execution_service.py` (2 dependencies)
- `app/services/firestore_service.py` (2 dependencies)
- `tests/test_firestore_service.py` (2 dependencies)
- `app/models/__init__.py` (1 dependencies)
