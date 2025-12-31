# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 10
- **Intra-repo dependencies**: 6
- **External stdlib dependencies**: 6
- **External third-party dependencies**: 9

## External Dependencies

### Standard Library / Core Modules

Total: 6 unique modules

- `contextlib.asynccontextmanager`
- `functools.lru_cache`
- `logging`
- `os`
- `sys`
- `unittest.mock.patch`

### Third-Party Packages

Total: 9 unique packages

- `fastapi.APIRouter`
- `fastapi.FastAPI`
- `fastapi.testclient.TestClient`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic_settings.BaseSettings`
- `pydantic_settings.SettingsConfigDict`
- `pytest`
- `pythonjsonlogger.json.JsonFormatter`

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (3 dependents)
- `app/main.py` (2 dependents)
- `app/api/health.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (2 dependencies)
- `app/dependencies.py` (1 dependencies)
- `tests/test_config.py` (1 dependencies)
- `tests/test_health.py` (1 dependencies)
- `tests/test_logging.py` (1 dependencies)
