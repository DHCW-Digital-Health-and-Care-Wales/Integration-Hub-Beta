# HL7 Transformer

HL7 Transformer Service

## Development

Create a virtual environment using uv:

```
uv venv
```

Install dependencies:

```
uv sync
```

Run code quality checks:

```
pipx run ruff check
pipx run bandit hl7_transformer/**/*.py tests/**/*.py
pipx run mypy --ignore-missing-imports hl7_transformer/**/*.py tests/**/*.py
```

or using uv:

```
uv run ruff check
uv run bandit hl7_transformer/**/*.py tests/**/*.py
```

Run unit tests:

`python -m unittest discover tests`

or using uv:

`uv run -m unittest discover tests`
