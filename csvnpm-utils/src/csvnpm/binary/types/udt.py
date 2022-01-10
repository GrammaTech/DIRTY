from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeVar
from typing import Union as tUnion

from csvnpm.binary.types.member import Field, Member, Padding
from csvnpm.binary.types.typeinfo import TypeInfo

_T = TypeVar("_T")


class UDT(TypeInfo):
    """An object representing struct or union types"""

    def __init__(self) -> None:
        raise NotImplementedError


class Union(UDT):
    """Stores information about a union"""

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        members: Iterable[tUnion[Field, "Struct", "Union"]],
        padding: Optional[Padding] = None,
    ):
        self.name = name
        self.members = tuple(members)
        self.padding = padding
        # Set size to 0 if there are no members
        try:
            self.size = max(m.size for m in members)
        except ValueError:
            self.size = 0
        if self.padding is not None:
            self.size += self.padding.size

    def has_padding(self) -> bool:
        """
        :return: True if this Union has padding
        """
        return self.padding is not None

    def accessible_offsets(self) -> Tuple[int, ...]:
        """
        :return: Offsets accessible in this Union
        """
        return tuple(range(max(m.size for m in self.members)))

    def inaccessible_offsets(self) -> Tuple[int, ...]:
        """
        :return: Offsets inaccessible in this Union or empty tuple
        """
        if not self.has_padding():
            return tuple()
        return tuple(range(max(m.size for m in self.members), self.size))

    def start_offsets(self) -> Tuple[int, ...]:
        """
        :return: the start offsets elements in this Union
        """
        return (0,)

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "Union":
        return cls(name=d["n"], members=d["m"], padding=d["p"])

    def _to_json(self) -> Dict[str, Any]:
        return {
            "T": 8,
            "n": self.name,
            "m": [m._to_json() for m in self.members],
            "p": self.padding,
        }

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Union):
            return (
                self.name == other.name
                and self.members == other.members
                and self.padding == other.padding
            )
        return False

    def __hash__(self) -> int:
        return hash((self.name, self.members, self.padding))

    def __str__(self) -> str:
        if self.name is None:
            ret = "union {{ "
        else:
            ret = f"union {self.name} {{ "
        for m in self.members:
            ret += f"{str(m)}; "
        if self.padding is not None:
            ret += f"{str(self.padding)}; "
        ret += "}"
        return ret

    def tokenize(self) -> List[str]:
        raise NotImplementedError


class Struct(UDT):
    """Stores information about a struct"""

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        layout: Iterable[tUnion[Member, "Struct", Union]],
    ):
        self.name = name
        self.layout = tuple(layout)
        self.size = sum(lay.size for lay in layout)

    def has_padding(self) -> bool:
        """
        :return: True if the Struct has padding
        """
        return any((isinstance(m, Padding) for m in self.layout))

    def accessible_offsets(self) -> Tuple[int, ...]:
        """
        :return: Offsets accessible in this struct
        """
        accessible: Tuple[int, ...] = tuple()
        current_offset = 0
        for m in self.layout:
            next_offset = current_offset + m.size
            if isinstance(m, Field):
                for offset in range(current_offset, next_offset):
                    accessible += (offset,)
            current_offset = next_offset
        return accessible

    def inaccessible_offsets(self) -> Tuple[int, ...]:
        """
        :return: Offsets inaccessible in this struct
        """
        if not self.has_padding():
            return tuple()
        inaccessible: Tuple[int, ...] = tuple()
        current_offset = 0
        for m in self.layout:
            next_offset = current_offset + m.size
            if isinstance(m, Padding):
                for offset in range(current_offset, next_offset):
                    inaccessible += (offset,)
            current_offset = next_offset
        return inaccessible

    def start_offsets(self) -> Tuple[int, ...]:
        """
        :return: the start offsets of fields in this struct

          For example, if int is 4-bytes, char is 1-byte, and long is 8-bytes,
          a struct with the layout:

            [int, char, padding(3), long, long]
            has offsets [0, 4, 8, 16].
        """
        starts: Tuple[int, ...] = tuple()
        current_offset = 0
        for m in self.layout:
            if isinstance(m, Field):
                starts += (current_offset,)
            current_offset += m.size
        return starts

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "Struct":
        return cls(name=d["n"], layout=d["l"])

    def _to_json(self) -> Dict[str, Any]:
        return {
            "T": 6,
            "n": self.name,
            "l": [lay._to_json() for lay in self.layout],
        }

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Struct):
            return self.name == other.name and self.layout == other.layout
        return False

    def __hash__(self) -> int:
        return hash((self.name, self.layout))

    def __str__(self) -> str:
        if self.name is None:
            ret = "struct {{ "
        else:
            ret = f"struct {self.name} {{ "
        for lay in self.layout:
            ret += f"{str(lay)}; "
        ret += "}"
        return ret

    def tokenize(self) -> List[str]:
        return (
            ["<struct>", self.name if self.name is not None else ""]
            + [str(lay) for lay in self.layout]
            + ["<eot>"]
        )
