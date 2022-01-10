from typing import Any, Dict, Type, TypeVar

_T = TypeVar("_T")


class Member:
    """A member of a UDT. Can be a Field or Padding"""

    size: int = 0

    def __init__(self) -> None:
        raise NotImplementedError

    @classmethod
    def _from_json(cls: Type[_T], d: Dict[str, Any]) -> _T:
        raise NotImplementedError

    def _to_json(self) -> Dict[str, Any]:
        raise NotImplementedError


class Padding(Member):
    """Padding bytes in a struct or union"""

    def __init__(self, size: int):
        self.size = size

    @classmethod
    def _from_json(cls, d: Dict[str, int]):
        return cls(size=d["s"])

    def _to_json(self) -> Dict[str, int]:
        return {"T": 5, "s": self.size}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Padding):
            return self.size == other.size
        return False

    def __hash__(self) -> int:
        return self.size

    def __str__(self) -> str:
        return f"PADDING ({self.size})"


class Field(Member):
    """Information about a field in a struct or union"""

    def __init__(self, *, name: str, size: int, type_name: str):
        self.name = name
        self.type_name = type_name
        self.size = size

    @classmethod
    def _from_json(cls, d: Dict[str, Any]):
        return cls(name=d["n"], type_name=d["t"], size=d["s"])

    def _to_json(self) -> Dict[str, Any]:
        return {
            "T": 4,
            "n": self.name,
            "t": self.type_name,
            "s": self.size,
        }

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Field):
            return self.name == other.name and self.type_name == other.type_name
        return False

    def __hash__(self) -> int:
        return hash((self.name, self.type_name))

    def __str__(self) -> str:
        return f"{self.type_name} {self.name}"
