# Advanced Guide to Python `unittest.mock`

This guide builds on `python-unittest-magicmock-guide.md` and focuses on more advanced mocking patterns you will run into in real test suites.

It covers:

- `patch.object`
- chained mocks
- async mocking with `AsyncMock`
- common mocking mistakes and how to avoid them

## `patch.object`

Use `patch.object` when you already have a reference to the class or object you want to patch.

Example production code:

```python
class PaymentGateway:
    def charge(self, amount: int) -> str:
        return "real-transaction-id"


def process_payment(gateway: PaymentGateway, amount: int) -> str:
    return gateway.charge(amount)
```

Test:

```python
import unittest
from unittest.mock import patch


class PaymentGateway:
    def charge(self, amount: int) -> str:
        return "real-transaction-id"


def process_payment(gateway: PaymentGateway, amount: int) -> str:
    return gateway.charge(amount)


class TestProcessPayment(unittest.TestCase):
    def test_process_payment_uses_gateway_charge(self) -> None:
        gateway = PaymentGateway()

        with patch.object(gateway, "charge", return_value="mock-123") as mock_charge:
            result = process_payment(gateway, 50)

        self.assertEqual(result, "mock-123")
        mock_charge.assert_called_once_with(50)
```

You can also patch methods on a class:

```python
with patch.object(PaymentGateway, "charge", return_value="mock-123") as mock_charge:
    gateway = PaymentGateway()
    result = process_payment(gateway, 50)
```

That affects instances created inside the patched block.

## Why `patch.object` Is Useful

It is helpful when:

- you want to patch a method on a specific instance
- you already imported the class into your test
- using a string-based `patch("module.name")` would be more awkward

## Using `autospec` to Catch Bad Calls

One common problem with mocks is that they accept almost any call shape unless you constrain them.

Example:

```python
import unittest
from unittest.mock import patch


class UserRepository:
    def get_by_id(self, user_id: int) -> dict:
        return {"id": user_id}


class TestUserRepository(unittest.TestCase):
    def test_autospec_preserves_method_signature(self) -> None:
        with patch.object(UserRepository, "get_by_id", autospec=True) as mock_get_by_id:
            repository = UserRepository()
            repository.get_by_id(10)

        mock_get_by_id.assert_called_once_with(repository, 10)
```

With `autospec=True`, the mock keeps the original signature. That helps catch mistakes such as calling a method with the wrong number of arguments.

## Chained Mocks

Sometimes production code calls a series of methods on an object. That is called a chain.

Example production code:

```python
def get_order_total(client, order_id: str) -> int:
    response = client.orders().get(order_id)
    return response.json()["total"]
```

You can mock the whole chain by configuring each return value:

```python
import unittest
from unittest.mock import MagicMock


def get_order_total(client, order_id: str) -> int:
    response = client.orders().get(order_id)
    return response.json()["total"]


class TestGetOrderTotal(unittest.TestCase):
    def test_get_order_total_reads_nested_response(self) -> None:
        client = MagicMock()
        client.orders.return_value.get.return_value.json.return_value = {"total": 125}

        result = get_order_total(client, "A100")

        self.assertEqual(result, 125)
        client.orders.assert_called_once_with()
        client.orders.return_value.get.assert_called_once_with("A100")
```

This works, but it can become hard to read if the chain is long.

A cleaner version is to name the intermediate mocks:

```python
orders_api = MagicMock()
response = MagicMock()

client.orders.return_value = orders_api
orders_api.get.return_value = response
response.json.return_value = {"total": 125}
```

That style is usually easier to debug.

## Mocking Context Managers

If the code uses `with`, mock the object returned by `__enter__()`.

Example production code:

```python
def read_first_line(opener, path: str) -> str:
    with opener(path) as handle:
        return handle.readline().strip()
```

Test:

```python
import unittest
from unittest.mock import MagicMock


def read_first_line(opener, path: str) -> str:
    with opener(path) as handle:
        return handle.readline().strip()


class TestReadFirstLine(unittest.TestCase):
    def test_read_first_line_uses_context_manager(self) -> None:
        opener = MagicMock()
        handle = MagicMock()
        handle.readline.return_value = "hello\n"
        opener.return_value.__enter__.return_value = handle

        result = read_first_line(opener, "data.txt")

        self.assertEqual(result, "hello")
        opener.assert_called_once_with("data.txt")
        handle.readline.assert_called_once_with()
```

## Async Mocking with `AsyncMock`

When testing `async def` functions, use `AsyncMock` for awaitable collaborators.

Example production code:

```python
async def fetch_user_name(client, user_id: int) -> str:
    user = await client.get_user(user_id)
    return user["name"]
```

Test:

```python
import unittest
from unittest.mock import AsyncMock


async def fetch_user_name(client, user_id: int) -> str:
    user = await client.get_user(user_id)
    return user["name"]


class TestFetchUserName(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_user_name_awaits_client(self) -> None:
        client = AsyncMock()
        client.get_user.return_value = {"id": 1, "name": "Alice"}

        result = await fetch_user_name(client, 1)

        self.assertEqual(result, "Alice")
        client.get_user.assert_awaited_once_with(1)
```

`AsyncMock` supports async-specific assertions such as:

- `assert_awaited()`
- `assert_awaited_once()`
- `assert_awaited_once_with(...)`

## Patching Async Functions

If the code imports and awaits a function, patch it with an async-capable mock.

Example production code:

```python
# service.py
from api import fetch_profile


async def get_timezone(user_id: int) -> str:
    profile = await fetch_profile(user_id)
    return profile["timezone"]
```

Test:

```python
import unittest
from unittest.mock import AsyncMock, patch

from service import get_timezone


class TestGetTimezone(unittest.IsolatedAsyncioTestCase):
    @patch("service.fetch_profile", new_callable=AsyncMock)
    async def test_get_timezone_reads_profile(self, mock_fetch_profile) -> None:
        mock_fetch_profile.return_value = {"timezone": "UTC"}

        result = await get_timezone(10)

        self.assertEqual(result, "UTC")
        mock_fetch_profile.assert_awaited_once_with(10)
```

## Side Effects for Sequential Behavior

`side_effect` is especially useful when the same mock is called multiple times.

```python
mock = MagicMock()
mock.fetch.side_effect = [{"page": 1}, {"page": 2}, StopIteration]
```

Or to simulate an error followed by success:

```python
mock.save.side_effect = [RuntimeError("temporary failure"), True]
```

That lets you test retry logic without a real dependency.

## Common Mocking Mistakes

### 1. Patching the Wrong Location

Patch where the object is looked up, not where it originally came from.

Bad:

```python
@patch("mailer.send_email")
```

Good, if `notifier.py` imported it with `from mailer import send_email`:

```python
@patch("notifier.send_email")
```

### 2. Using `MagicMock` for Awaited Calls

If the code does `await dependency.method()`, a plain `MagicMock` is usually the wrong choice.

Use `AsyncMock` instead.

### 3. Mocking Too Much

Over-mocking can make tests brittle and less useful.

For example, this is often a smell:

- mocking the function you are actually trying to test
- asserting every internal helper call instead of the final behavior
- building a deep tree of mocks when a small fake object would be clearer

Prefer testing observable behavior first, and only verify collaborator calls when those interactions are important.

### 4. Forgetting That Class Patches Affect Instantiation

If you patch a class, the patched object becomes the fake constructor result.

Example:

```python
@patch("orders.Repository")
def test_load_order(self, mock_repository_class) -> None:
    mock_repository = mock_repository_class.return_value
    mock_repository.get.return_value = {"id": 1}
```

In this pattern:

- `mock_repository_class` is the patched class
- `mock_repository_class.return_value` is the instance your code receives

### 5. Not Resetting or Recreating Mocks Between Checks

If you reuse a mock across multiple assertions, old calls stay recorded.

Use:

```python
mock.reset_mock()
```

or create a fresh mock for each test.

### 6. Ignoring `spec` and `autospec`

A loose mock can hide typos:

```python
client.feth_user(1)
```

That may silently pass on a plain mock even though `feth_user` is misspelled.

Using `spec`, `spec_set`, or `autospec` helps catch these mistakes earlier.

## A Practical Pattern: Verify Behavior, Then Important Interactions

A balanced test often looks like this:

```python
import unittest
from unittest.mock import MagicMock


def create_welcome_message(notifier, user: dict) -> str:
    message = f"Welcome {user['name']}"
    notifier.send(user["email"], message)
    return message


class TestCreateWelcomeMessage(unittest.TestCase):
    def test_create_welcome_message_returns_and_sends_message(self) -> None:
        notifier = MagicMock()

        result = create_welcome_message(
            notifier,
            {"name": "Alice", "email": "alice@example.com"},
        )

        self.assertEqual(result, "Welcome Alice")
        notifier.send.assert_called_once_with(
            "alice@example.com",
            "Welcome Alice",
        )
```

This checks both:

- the result returned by your function
- the important side effect with its collaborator

## Summary

Advanced mocking is most useful when your code:

- creates dependencies internally
- makes chained calls
- uses async functions
- relies on context managers

The main ideas to remember are:

- patch where the dependency is looked up
- use `patch.object` when you already have the target object or class
- use `AsyncMock` for awaited behavior
- use `autospec` or `spec` to make mocks safer
- avoid over-mocking when a simpler test setup will do
