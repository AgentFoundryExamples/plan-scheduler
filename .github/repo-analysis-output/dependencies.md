# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 13
- **Intra-repo dependencies**: 9
- **External stdlib dependencies**: 8
- **External third-party dependencies**: 12

## External Dependencies

### Standard Library / Core Modules

Total: 8 unique modules

- `contextlib.asynccontextmanager`
- `functools.lru_cache`
- `logging`
- `os`
- `sys`
- `unittest.mock.MagicMock`
- `unittest.mock.patch`
- `uuid`

### Third-Party Packages

Total: 12 unique packages

- `fastapi.APIRouter`
- `fastapi.FastAPI`
- `fastapi.testclient.TestClient`
- `google.api_core.exceptions`
- `google.auth.exceptions`
- `google.cloud.firestore`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic_settings.BaseSettings`
- `pydantic_settings.SettingsConfigDict`
- `pytest`
- `pythonjsonlogger.json.JsonFormatter`

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (4 dependents)
- `app/services/firestore_service.py` (2 dependents)
- `app/main.py` (2 dependents)
- `app/api/health.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/dependencies.py` (2 dependencies)
- `app/main.py` (2 dependencies)
- `app/services/firestore_service.py` (1 dependencies)
- `tests/test_config.py` (1 dependencies)
- `tests/test_firestore_service.py` (1 dependencies)
- `tests/test_health.py` (1 dependencies)
- `tests/test_logging.py` (1 dependencies)
