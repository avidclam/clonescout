# ADR 004: Standardizing Type Hinting Conventions for Python 3.11

## Status
Accepted

## Context
The project has standardized on Python 3.11. Historically, Python type hinting relied heavily on the `typing` module (e.g., `typing.List`, `typing.Union`, `typing.Iterator`). 

With the introduction of PEP 585 (Python 3.9) and PEP 604 (Python 3.10), native types and the `|` operator became available, making many constructs in the `typing` module obsolete or deprecated. To ensure code consistency, improve readability, and prevent mixed styles (such as mixing `typing.Dict` with `dict`), we need a strict agreement on how to annotate types.

## Decision
We adopt a modern type hinting convention that leverages Python 3.11 native capabilities. The responsibilities are divided as follows:

1. **Use `collections.abc`** for abstract classes, interfaces, and protocols:
   - `Iterator`, `Callable`, `Generator`, `Sequence`, `Mapping`, `MutableMapping`, `Iterable`

2. **Use `typing`** only for type-system primitives and internal static checking mechanisms that have no native or `collections.abc` equivalents:
   - `Any`, `TYPE_CHECKING`, `TypeVar`, `TypeAlias`

3. **Use built-in types directly** (in lowercase) for concrete data structures and type references:
   - `list`, `dict`, `tuple`, `set`, `frozenset`, `type`

4. **Use the `|` operator** for generic unions and optional values:
   - Use `X | Y` instead of `Union[X, Y]`
   - Use `X | None` instead of `Optional[X]`

## Consequences
- **Codebase Modernization:** The code looks cleaner, uniform, and strictly follows modern Python best practices.
- **Future-Proofing:** Avoiding deprecated `typing` attributes ensures a seamless upgrade path to Python 3.12+ (and safeguards against Python 3.14, where deprecated typing aliases are scheduled for removal).
- **Tooling and Automation:** Automated linters and formatters (specifically **Ruff** with `UP` (pyupgrade) rules enabled) must be configured to enforce these conventions and auto-fix violations.
