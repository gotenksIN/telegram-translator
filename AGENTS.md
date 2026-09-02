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
- Always split messages longer than 4096 characters cleanly at line breaks before delivery.
- Attach link preview options only to the first chunk of a multi-part response.
- Check and reject replied messages originating from the bot itself.

Use semantic line breaks in Markdown prose: put each complete sentence on its own source line.
Use active voice, present tense, ASD-STE100 short sentences, and sentence-case headings.
Do not use exclamation points in documentation.

## Testing principles

Test contracts through public or executable interfaces.
Assert outputs, side effects, errors, and externally visible state that distinguish a conforming implementation from a broken one.
Every test must protect a behavioral contract.
Remove tests that only prove a feature, API, command, handler, or registration exists.
Let the typechecker enforce static type relationships.
Do not add runtime tests that a typecheck alone satisfies.

Test adapters against project-owned contracts at the integration boundary.
Do not simulate external providers or encode assumptions about their payload, event, or API shapes in unit tests.
For adapters such as Telegram, Gemini, or HTTP/yt-dlp, verify only the translation and behavior the project owns.
Do not test private structure, helper names, prompt prose, or internal mock topologies.

## Simplicity (YAGNI)

Implement only current, explicit requirements.
Do not add speculative features, abstractions, configuration, dependencies, or extensibility for hypothetical future use.
Prefer the smallest clear change that reuses existing code and standard facilities.
Delete obsolete code when safe.

Before writing a utility or adding a dependency, search the repository for an existing implementation and its callers.
Then check the standard library and already-declared dependencies.
Reuse an established option when it fits.
Ask before adding a new dependency.

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

## Git workflow

Never create commits unless the user explicitly asks for them.
When the user requests per-task commits, commit each discrete task before starting the next one.
Before every commit, run the exact full commands `git status`, `git diff`, and `git log -10`.
Do not replace these required inspections with abbreviated variants such as `git status --short`, `git diff --stat`, or `git log --oneline`.
Read the full commit messages from `git log -10`, including their bodies and trailers.
Stage only files that belong to the current task.

Format commit messages per repository conventions:
- Use the subject format `<scope>: <Capitalized summary>`. Derive the lowercase scope from the component or directory you changed.
- Write the summary in the imperative mood and do not end it with a period.
- Keep the subject near 50 characters and never longer than 72 characters.
- Add a concise, technical body when the subject does not provide enough context. Explain what changed and why.
- Separate the subject from the body with a blank line and wrap body text at 72 characters.

Check commit signing once per session with `git config commit.gpgsign` and `git config user.signingkey`.
Remember the result for the rest of the session.
If both are set, sign every commit with the configured method and use `git commit --signoff`.
Do not amend commits, push, or rewrite history unless the user explicitly asks.
