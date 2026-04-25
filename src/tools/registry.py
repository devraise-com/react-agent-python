"""Tool registry: register functions, auto-generate OpenAI schemas, dispatch calls."""

import inspect
import types
from typing import Any, Callable, TypeVar, Union, get_type_hints

from src.tools.base import ToolError

F = TypeVar("F", bound=Callable[..., Any])


class ToolRegistry:
    """Central registry mapping tool names → (callable, OpenAI schema)."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {}

    def register(self, fn: F) -> F:
        """Decorator: introspect fn, build JSON Schema, store in registry."""
        schema = self._build_schema(fn)
        self._tools[fn.__name__] = (fn, schema)
        return fn

    def schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas in OpenAI `tools=` format."""
        return [schema for _, schema in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        """Call a registered tool by name; wrap any exception as ToolError."""
        if name not in self._tools:
            raise ToolError(f"Unknown tool: '{name}'")
        fn, _ = self._tools[name]
        try:
            return fn(**args)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Schema building
    # ------------------------------------------------------------------

    def _build_schema(self, fn: Callable[..., Any]) -> dict[str, Any]:
        sig = inspect.signature(fn)
        try:
            hints = get_type_hints(fn)
        except Exception:
            hints = {}
        hints.pop("return", None)

        properties: dict[str, Any] = {}
        required: list[str] = []

        for name, param in sig.parameters.items():
            annotation = hints.get(name, str)
            properties[name] = self._annotation_to_schema(annotation)
            if param.default is inspect.Parameter.empty:
                required.append(name)

        return {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": (inspect.getdoc(fn) or fn.__name__).strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def _annotation_to_schema(self, annotation: Any) -> dict[str, Any]:
        """Convert a Python type annotation to a JSON Schema fragment."""
        if annotation is str:
            return {"type": "string"}
        if annotation is int:
            return {"type": "integer"}
        if annotation is float:
            return {"type": "number"}
        if annotation is bool:
            return {"type": "boolean"}

        origin = getattr(annotation, "__origin__", None)
        args: tuple[Any, ...] = getattr(annotation, "__args__", ())

        # list[X]
        if origin is list:
            item_schema = self._annotation_to_schema(args[0] if args else str)
            return {"type": "array", "items": item_schema}

        # X | None  (Python 3.10+ union)  or  Optional[X] = Union[X, None]
        if isinstance(annotation, types.UnionType) or origin is Union:
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return self._annotation_to_schema(non_none[0])

        return {"type": "string"}  # safe fallback
