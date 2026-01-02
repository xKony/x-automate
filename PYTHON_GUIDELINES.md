## 1. Introduction & Philosophy

This document outlines the mandatory coding standards for all Python development within the organization. Our goal is to maintain a codebase that is **scalable, readable, and performant**. We adhere to strict modularity and type safety to prevent technical debt.

**Core Principles:**

1.  **Readability counts.** Code is read much more often than it is written.
2.  **Explicit is better than implicit.** Type hints and specific error handling are required.
3.  **Performance matters.** Use efficient structures and vectorized operations.

---

## 2. Style & Naming Conventions (PEP 8)

We adhere to [PEP 8](https://peps.python.org/pep-0008/) with specific enforcement on naming patterns.

### 2.1 Naming Rules

| Entity              | Convention      | Example                                |
| :------------------ | :-------------- | :------------------------------------- |
| **Variables**       | `snake_case`    | `user_id`, `retry_count`               |
| **Functions**       | `snake_case`    | `calculate_metric()`, `fetch_data()`   |
| **Classes**         | `PascalCase`    | `DataProcessor`, `UserAuth`            |
| **Constants**       | `UPPER_CASE`    | `MAX_RETRIES`, `DEFAULT_TIMEOUT`       |
| **Private Members** | Prefix with `_` | `_internal_cache`, `_validate_input()` |

### 2.2 Code Example

```python
# GOOD
MAX_BUFFER_SIZE = 1024

class DataStream:
    def __init__(self):
        self._buffer = []  # Private attribute

    def process_stream(self):
        pass

# BAD
MaxBufferSize = 1024
class data_stream:
    def ProcessStream(self):
        pass
```

---

## 3. Type Safety & Tooling

To support static analysis (`mypy`) and improve IDE autocompletion, type hinting is **mandatory** for all function signatures and class attributes.

### 3.1 Requirements

- Import types from the standard `typing` module (or built-ins in Python 3.9+).
- Use `Optional` for values that can be `None`.
- Use `List`, `Dict`, `Tuple`, or `Iterable` for data structures.

### 3.2 Code Example

```python
from typing import List, Optional, Dict

def fetch_user_metadata(user_ids: List[int]) -> Dict[int, str]:
    """
    Retrieves metadata for a list of user IDs.
    """
    result: Dict[int, str] = {}
    for uid in user_ids:
        # Implementation...
        pass
    return result

def get_config(key: str) -> Optional[str]:
    # Returns None if key is missing, rather than crashing
    pass

```

---

## 4. Performance & Efficiency

Python is interpreted, making algorithmic efficiency critical. Inefficient patterns are grounds for code review rejection.

### 4.1 Membership Checking

**Rule:** Never use `list` for membership checks (`x in y`) if the collection is large. Use `set`.

- **List Lookup:**
- **Set Lookup:**

```python
# BAD: O(n)
valid_ids = [1, 2, 3, 4, 5, ... 10000]
if current_id in valid_ids:
    pass

# GOOD: O(1)
valid_ids = {1, 2, 3, 4, 5, ... 10000}
if current_id in valid_ids:
    pass

```

### 4.2 Memory Management with Generators

**Rule:** Use Generators (`yield`) when processing large datasets or streams. Do not materialize large lists in memory.

```python
from typing import Iterator

# BAD: Loads 1GB data into memory
def get_large_logs() -> List[str]:
    logs = []
    for line in open("huge_file.log"):
        logs.append(line)
    return logs

# GOOD: Yields one line at a time (Low Memory Footprint)
def stream_large_logs() -> Iterator[str]:
    with open("huge_file.log") as f:
        for line in f:
            yield line

```

### 4.3 Vectorization (NumPy/Pandas)

**Rule:** Avoid explicit Python loops for mathematical operations on datasets. Use vectorized operations provided by NumPy or Pandas.

```python
import numpy as np

# BAD: Slow Python Loop
data = [1, 2, 3, 4, 5]
squared = []
for x in data:
    squared.append(x ** 2)

# GOOD: Vectorized Operation (C-optimized)
arr = np.array([1, 2, 3, 4, 5])
squared = arr ** 2

```

---

## 5. Error Handling & Observability

Failures must be handled gracefully and visibly. Silencing errors is strictly forbidden.

### 5.1 Exception Handling

**Rule:** Never use a bare `except:` clause. Catch specific exceptions.

```python
from utils.logger import get_logger()

log = get_logger()

# BAD
try:
    data = load_json()
except:
    pass  # Silently fails, impossible to debug

# GOOD
try:
    data = load_json()
except (ValueError, FileNotFoundError) as e:
    log.error(f"Failed to load configuration: {e}")
    raise  # Re-raise if the application cannot recover

```

### 5.2 Logging

**Rule:** Log logic should reside close to the source of the error to capture context (local variables, state). Use structured logging where possible. Add debugging whenever possible to easily catch errors. Always use the logger from utils.logger.

---

## 6. Architecture & Modularity

### 6.1 Single Responsibility Principle (SRP)

**Rule:** A function should do exactly **one** thing.
**Constraint:** Limit functions to **20-30 lines** of code. If a function exceeds this, it is likely doing too much and must be refactored into helper functions.

### 6.2 Class Design

**Rule:** Avoid "God Classes" (classes that manage disparate parts of the system).

- Break classes down by functionality (e.g., `UserAuthenticator`, `UserProfileManager`, `UserActivityLogger` instead of `UserManager`).
- Depend on abstractions, not concretions.

```python
# BAD: God Class
class SystemManager:
    def connect_db(self): ...
    def send_email(self): ...
    def process_payments(self): ...
    def render_ui(self): ...

# GOOD: Modular Design
class EmailService:
    def send(self, recipient: str, body: str): ...

class PaymentProcessor:
    def charge(self, amount: float): ...

```

```

```
