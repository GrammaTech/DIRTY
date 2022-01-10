from typing import Any, Dict, List, Optional, Tuple
from typing import Union as tUnion


class TypeInfo:
    """Stores information about a type"""

    def __init__(self, *, name: Optional[str], size: int):
        self.name = name
        self.size = size

    def accessible_offsets(self) -> Tuple[int, ...]:
        """
        :return: Offsets accessible in this type
        """
        return tuple(range(self.size))

    def inaccessible_offsets(self) -> Tuple[int, ...]:
        """
        :return: Inaccessible offsets in this type (e.g., padding in a Struct)
        """
        return tuple()

    def start_offsets(self) -> Tuple[int, ...]:
        """
        :return: Start offsets of elements in this type
        """
        return (0,)

    def replacable_with(self, others: Tuple["TypeInfo", ...]) -> bool:
        """
        Check if this type can be replaced with others
        :param others: types to compare against
        :return: bool of can be replaced
        """
        if self.size != sum(other.size for other in others):
            return False
        cur_offset = 0
        other_start: Tuple[int, ...] = tuple()
        other_accessible: Tuple[int, ...] = tuple()
        other_inaccessible: Tuple[int, ...] = tuple()
        for other in others:

            def displace(offsets: Tuple[int, ...]) -> Tuple[int, ...]:
                return tuple(off + cur_offset for off in offsets)

            other_start += displace(other.start_offsets())
            other_accessible += displace(other.accessible_offsets())
            other_inaccessible += displace(other.inaccessible_offsets())
        return (
            set(self.start_offsets()).issubset(other_start)
            and self.accessible_offsets() == other_accessible
            and self.inaccessible_offsets() == other_inaccessible
        )

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "TypeInfo":
        """
        Decodes from a dictionary
        :param d: json as dict
        :return: TypeInfo instance
        """
        return cls(name=d["n"], size=d["s"])

    def _to_json(self) -> Dict[str, Any]:
        return {"T": 1, "n": self.name, "s": self.size}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, TypeInfo):
            return self.name == other.name and self.size == other.size
        return False

    def __hash__(self) -> int:
        return hash((self.name, self.size))

    def __str__(self) -> str:
        return f"{self.name}"

    def tokenize(self) -> List[str]:
        return [str(self), "<eot>"]

    @classmethod
    def detokenize(cls, subtypes: List[str]) -> List[str]:
        """
        A list of concatenated subtypes separated by <eot>
        :param subtypes: list of string represenations of subtype tags
        :return: list of type tags stored as strings
        """
        ret: List[str] = []
        current: List[str] = []
        for subtype in subtypes:
            if subtype == "<eot>":
                ret.append(cls.parse_subtype(current))
                current = []
            else:
                current.append(subtype)
        return ret

    @classmethod
    def parse_subtype(cls, subtypes: List[str]) -> str:
        if len(subtypes) == 0:
            return ""
        if subtypes[0] == "<struct>":
            ret = "struct"
            if len(subtypes) == 1:
                return ret
            ret += f" {subtypes[1]} {{ "
            for subtype in subtypes[2:]:
                ret += f"{subtype}; "
            return ret + "}"
        elif subtypes[0] == "<ptr>":
            if len(subtypes) == 1:
                return " *"
            else:
                return f"{subtypes[1]} *"
        elif subtypes[0] == "<array>":
            if len(subtypes) < 3:
                return "[]"
            else:
                return f"{subtypes[1]}{subtypes[2]}"
        else:
            return subtypes[0]


class Array(TypeInfo):
    """Stores information about an array"""

    def __init__(self, *, nelements: int, element_size: int, element_type: str):
        self.element_type = element_type
        self.element_size = element_size
        self.nelements = nelements
        self.size = element_size * nelements

    def start_offsets(self) -> Tuple[int, ...]:
        """
        For example, the type int[4] has start offsets [0, 4, 8, 12] (for 4-byte ints).
        :return: the start offsets elements in this array
        """
        return tuple(range(self.size)[:: self.element_size])

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "Array":
        return cls(nelements=d["n"], element_size=d["s"], element_type=d["t"])

    def _to_json(self) -> Dict[str, Any]:
        return {
            "T": 2,
            "n": self.nelements,
            "s": self.element_size,
            "t": self.element_type,
        }

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Array):
            return (
                self.nelements == other.nelements
                and self.element_size == other.element_size
                and self.element_type == other.element_type
            )
        return False

    def __hash__(self) -> int:
        return hash((self.nelements, self.element_size, self.element_type))

    def __str__(self) -> str:
        if self.nelements == 0:
            return f"{self.element_type}[]"
        return f"{self.element_type}[{self.nelements}]"

    def tokenize(self) -> List[str]:
        return [
            "<array>",
            f"{self.element_type}",
            f"[{self.nelements}]",
            "<eot>",
        ]


class Pointer(TypeInfo):
    """Stores information about a pointer.

    Note that the referenced type is by name because recursive data structures
    would recurse indefinitely.
    """

    size = 8

    def __init__(self, target_type_name: str):
        self.target_type_name = target_type_name

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "Pointer":
        return cls(d["t"])

    def _to_json(self) -> Dict[str, Any]:
        return {"T": 3, "t": self.target_type_name}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Pointer):
            return self.target_type_name == other.target_type_name
        return False

    def __hash__(self) -> int:
        return hash(self.target_type_name)

    def __str__(self) -> str:
        return f"{self.target_type_name} *"

    def tokenize(self) -> List[str]:
        return ["<ptr>", self.target_type_name, "<eot>"]


class Void(TypeInfo):
    size = 0

    def __init__(self) -> None:
        pass

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "Void":
        return cls()

    def _to_json(self) -> Dict[str, int]:
        return {"T": 8}

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Void)

    def __hash__(self) -> int:
        return 0

    def __str__(self) -> str:
        return "void"


class Disappear(TypeInfo):
    """Target type for variables that don't appear in the ground truth function"""

    size = 0

    def __init__(self) -> None:
        pass

    @classmethod
    def _from_json(cls, d: Dict[str, Any]) -> "Disappear":
        return cls()

    def _to_json(self) -> Dict[str, int]:
        return {"T": 10}

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Disappear)

    def __hash__(self) -> int:
        return 0

    def __str__(self) -> str:
        return "disappear"


class FunctionPointer(TypeInfo):
    """Stores information about a function pointer."""

    size = Pointer.size

    def __init__(self, name: str):
        self.name = name

    def replacable_with(self, other: Tuple[TypeInfo, ...]) -> bool:
        # No function pointers are replacable for now
        return False

    @classmethod
    def _from_json(cls, d: Dict[str, tUnion[str, int, None]]) -> "FunctionPointer":
        return cls(d["n"])  # type: ignore

    def _to_json(self) -> Dict[str, Any]:
        return {"T": 9, "n": self.name}

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, FunctionPointer):
            return self.name == other.name
        return False

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return f"{self.name}"
