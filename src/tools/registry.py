"""Tool registry: register functions, validate IO, build OpenAI schemas."""

import inspect
import types
from dataclasses import dataclass
from typing import Any, Callable, TypeVar, Union, overload, get_type_hints

from pydantic import BaseModel, ValidationError

from src.tools.base import ToolError

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class RegisteredTool:
    fn: Callable[..., Any]
    schema: dict[str, Any]
    params_model: type[BaseModel] | None
    result_model: type[BaseModel] | None


class ToolRegistry:
    """Central registry mapping tool names → (callable, OpenAI schema)."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    @overload
    def register(self, fn: F) -> F: ...

    @overload
    def register(
        self,
        fn: None = None,
        *,
        params_model: type[BaseModel] | None = None,
        result_model: type[BaseModel] | None = None,
    ) -> Callable[[F], F]: ...

    def register(
        self,
        fn: F | None = None,
        *,
        params_model: type[BaseModel] | None = None,
        result_model: type[BaseModel] | None = None,
    ) -> F | Callable[[F], F]:
        """Decorator: register a tool with optional IO models."""

        def _decorator(inner_fn: F) -> F:
            schema = self._build_schema(inner_fn, params_model=params_model)
            self._tools[inner_fn.__name__] = RegisteredTool(
                fn=inner_fn,
                schema=schema,
                params_model=params_model,
                result_model=result_model,
            )
            return inner_fn

        if fn is not None:
            return _decorator(fn)
        return _decorator

    def schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas in OpenAI `tools=` format."""
        return [tool.schema for tool in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        """Call a registered tool by name with strict input/output validation."""
        if name not in self._tools:
            raise ToolError(f"Unknown tool: '{name}'", code="unknown_tool")
        tool = self._tools[name]

        call_args = args
        if tool.params_model is not None:
            try:
                validated_args = tool.params_model.model_validate(args)
            except ValidationError as exc:
                raise ToolError(
                    self._format_validation_message(exc),
                    code="invalid_arguments",
                    details=exc.errors(),
                ) from exc
            call_args = validated_args.model_dump(
                mode="python", by_alias=False, exclude_none=False
            )

        try:
            result = tool.fn(**call_args)
        except ToolError:
            raise
        except Exception as exc:
            error_code = getattr(getattr(exc, "code", None), "value", None)
            if not isinstance(error_code, str):
                raw_code = getattr(exc, "code", None)
                error_code = str(raw_code) if raw_code is not None else "tool_execution_error"
            raise ToolError(
                str(exc),
                code=error_code,
                details={"exception_type": type(exc).__name__},
            ) from exc

        if tool.result_model is not None:
            try:
                validated_result = tool.result_model.model_validate(result)
            except ValidationError as exc:
                raise ToolError(
                    self._format_validation_message(exc),
                    code="invalid_result",
                    details=exc.errors(),
                ) from exc
            return validated_result.model_dump(
                mode="python", by_alias=True, exclude_none=False
            )
        return result

    # ------------------------------------------------------------------
    # Schema building
    # ------------------------------------------------------------------

    def _build_schema(
        self, fn: Callable[..., Any], *, params_model: type[BaseModel] | None = None
    ) -> dict[str, Any]:
        parameters: dict[str, Any]
        if params_model is not None:
            parameters = self._model_to_parameters_schema(params_model)
        else:
            parameters = self._build_parameters_from_signature(fn)

        return {
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": (inspect.getdoc(fn) or fn.__name__).strip(),
                "parameters": parameters,
            },
        }

    def _build_parameters_from_signature(self, fn: Callable[..., Any]) -> dict[str, Any]:
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
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _model_to_parameters_schema(
        self, model_type: type[BaseModel]
    ) -> dict[str, Any]:
        model_schema = model_type.model_json_schema()
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": model_schema.get("properties", {}),
            "required": model_schema.get("required", []),
        }
        if "additionalProperties" in model_schema:
            parameters["additionalProperties"] = model_schema["additionalProperties"]
        return parameters

    def _format_validation_message(self, exc: ValidationError) -> str:
        errors = exc.errors()
        if not errors:
            return "Validation failed"
        first = errors[0]
        loc = ".".join(str(part) for part in first.get("loc", [])) or "<input>"
        msg = str(first.get("msg", "Validation failed"))
        return f"Invalid value for '{loc}': {msg}"

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
