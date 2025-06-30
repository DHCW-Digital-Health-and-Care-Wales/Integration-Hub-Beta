# Container App Health Check


## Development

Create virtual environment and start using it:

```python3 -m venv venv```

Activate virtual enviornment:

```source venv/bin/activate```

Install dependencies:

```pip install -r requirements.txt```

Run code quality checks:

```
pipx run ruff check
pipx run bandit health_check_lib/**/*.py
pipx run mypy --ignore-missing-imports health_check_lib/**/*.py
```

Run unit tests:

```python -m unittest discover tests```
