# Agent specification

`CONTEXT.md` is the authoritative technical and architectural specification for this repository.
It describes the bot lifecycle, schemas, preview pipeline, rate limits, and domain model from first principles.
Read `CONTEXT.md` before changing code, tests, scripts, or documentation.
Always keep `CONTEXT.md` up-to-date whenever architecture, schemas, pipeline flow, or domain concepts change.

## Development rules

Use ASCII for documentation, code, and comments unless existing content requires another character set.
Keep comments rare and explain non-obvious behavior.
Do not use legacy `google-generativeai`.
Use `google-genai` for all Gemini operations.

When a Gemini request does not require automatic function calling, construct its config with `build_content_config()` so AFC is disabled explicitly instead of relying on SDK defaults.
This requirement applies to structured, plain-text, tool-enabled, and tool-free requests that do not require automatic function calling.
Test each Gemini request type at the adapter boundary.
Assert behaviorally required request configuration, including disabled AFC, without binding coverage to config builder structure.

Keep the modules in `app/` on an acyclic dependency graph:
- `app/settings.py` is a foundation module with no project-internal imports.
- `app/preview.py` is an independent module with no project-internal imports.
- `app/gemini.py` depends only on `app.settings`.
- `app/main.py` orchestrates `settings`, `preview`, and `gemini`, and owns the bot lifecycle.

Enforce server-side request forgery (SSRF) defenses on all preview fetches:
- Validate every preview URL and redirect hop with `validate_public_http_url` before issuing HTTP requests.
- Never bypass or disable IP resolution or the non-public address check.

Enforce Telegram delivery and throughput constraints:
- Enforce the global semaphore (`MAX_RUNNING_TRANSLATIONS = 3`) and sliding window rate limiter (`MAX_TRANSLATIONS_PER_MINUTE = 10`) before processing requests.
- Reject messages and translations longer than 4096 characters with an explicit limit notice.
- Attach link preview options to the preview translation reply.
- Check and reject replied messages originating from the bot itself.

## Validation matrix

Run only checks strictly relevant to the changed files.
Never chain full test suites, unchanged tool checks, or multi-command verification runs for small, focused edits.
For documentation or instruction edits, do not run pytest, ruff, or CLI commands.

| Changed files | Required checks |
| --- | --- |
| Documentation or instructions only | No code validation. Check Markdown semantics manually. |
| `app/settings.py` | `uv run pytest tests/test_settings.py` |
| `app/preview.py` | `uv run pytest tests/test_preview.py` |
| `app/gemini.py` | `uv run pytest tests/test_gemini.py` |
| `app/main.py` | `uv run pytest tests/test_main.py` |
| `tests/` | Run only the specific changed test file. |
| Python production or test files | `uv run ruff check <changed-file>` and `uv run ruff format --check <changed-file>`. |

Run the full pytest suite only when the user explicitly requests it or when a change touches cross-module boundaries without clear ownership.
