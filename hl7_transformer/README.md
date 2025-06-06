# HL7 Transformer

HL7 Transformer Service

## Development

Create virtual environment and start using it:

```
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```pip install -r requirements```

Run code quality checks:

```
pipx run ruff check
pipx run bandit *.py tests/**/*.py
pipx run mypy --ignore-missing-imports *.py
```

Run unit tests:

```python -m unittest discover tests```
