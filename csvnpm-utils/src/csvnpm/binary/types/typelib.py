import gzip
import os
import warnings
from abc import ABC, abstractmethod, abstractstaticmethod
from collections import defaultdict
from json import JSONEncoder, dumps, loads
from typing import (
    Any,
    DefaultDict,
    Dict,
    ItemsView,
    Iterable,
    KeysView,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
)
from typing import Union as tUnion
from typing import ValuesView

from csvnpm.binary.types.member import Field, Member, Padding
from csvnpm.binary.types.typeinfo import (
    Array,
    Disappear,
    FunctionPointer,
    Pointer,
    TypeInfo,
    Void,
)
from csvnpm.binary.types.udt import Struct, Union
from sortedcollections import ValueSortedDict


class Entry(NamedTuple):
    """A single entry in the TypeLib"""

    frequency: int  # order matters, frequency first for sorting
    typeinfo: TypeInfo

    def __eq__(self, other) -> bool:
        if isinstance(other, Entry):
            return other.typeinfo == self.typeinfo
        return False

    def __lt__(self, other) -> bool:
        assert isinstance(other, Entry)
        return self.frequency < other.frequency

    def inc(self, value: int) -> "Entry":
        return Entry(frequency=self.frequency + value, typeinfo=self.typeinfo)

    def __repr__(self) -> str:
        return f"({self.frequency}, {str(self.typeinfo)})"


T = TypeVar("T", bound="TypeLibABC")


class EntryList:
    """A list of entries in the TypeLib. Each is list of Entries sorted by
    frequency.
    """

    def __init__(self, data: List[Entry] = []):
        # type is not subscriptable, real type is ValueSortedDict[TypeInfo, Entry]
        self._data: ValueSortedDict = self._initialize_data(data)

    @staticmethod
    def _initialize_data(data: Iterable[Entry], freq: int = -1) -> ValueSortedDict:
        return ValueSortedDict({t.typeinfo: t for t in data if t.frequency >= freq})

    @property
    def frequency(self) -> int:
        """
        The total frequency for this entry list
        :return: the total of the frequencies for all entries in list
        """
        return sum(c.frequency for c in self._data.values())

    def add_n(self, item: TypeInfo, n: int) -> bool:
        """
        Add n items, increasing frequency if it already exists.
        :param item: item to add
        :param n: count of item to add
        :return: True if the item already existed during any of the adds
        """
        entry = self._data.get(item, Entry(0, item)).inc(n)
        # this statement fits the comment, but is a code change
        # exists = bool(entry.frequency > 1)
        self._data[item] = entry
        return True  # should return exists

    def add(self, item: TypeInfo) -> bool:
        """
        Add an item, increasing frequency if it already exists.
        :param item: item to add
        :return: True if the item already existed.
        """
        return self.add_n(item, 1)

    def add_entry(self, entry: Entry) -> bool:
        """
        Add an Entry, returns True if the entry already existed
        :param entry: entry to add with associated frequency
        :return: is entry previosly exist
        """
        return self.add_n(entry.typeinfo, entry.frequency)

    def add_all(self, other: "EntryList"):
        """
        Add all entries in other
        :param other: second list, could be thought of as `+` across frequencies
        """
        for entry in other:
            self.add_entry(entry)

    def get_freq(self, item: TypeInfo) -> Optional[int]:
        """
        Get the frequency of an item, None if it does not exist
        :param item: type of item to retrieve frequency for
        :return: frequency if exists else `None`  # bad practice, should just return 0
        """
        return self._data[item].freqency if item in self._data else None

    def sort(self):
        warnings.warn("structure is now always sorted", DeprecationWarning)

    def _to_json(self) -> List[Entry]:
        return self._data

    def __iter__(self):
        yield from self._data.values()

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, i: int) -> Entry:
        return self._data.peekitem(i)[1]

    def __repr__(self) -> str:
        return f"{[(entry) for entry in self._data.values()]}"

    def prune(self, freq):
        self._data = self._initialize_data(self._data.values(), freq=freq)


class TypeLibABC(ABC):
    """A library of types.

    Allows access to types by size.

    The usual dictionary magic methods are implemented, allowing for
    dictionary-like access to TypeInfo.
    """

    def __init__(self, data: Optional[DefaultDict[int, EntryList]] = None):
        if data is None:
            self._data: DefaultDict[int, EntryList] = defaultdict(EntryList)
        else:
            self._data = data

    @abstractstaticmethod
    def parse_type(typ: Any) -> TypeInfo:
        raise NotImplementedError

    @abstractmethod
    def add_type(self, typ: Any, worklist: Set[str] = set()):
        raise NotImplementedError

    def add_entry_list(self, size: int, entries: EntryList):
        """
        Add an entry list of items of size 'size'

        :param size: size of entry list
        :param entries: entry list
        """
        if size in self:
            self[size].add_all(entries)
        else:
            self[size] = entries

    def add(self, typ):
        entry = EntryList()
        entry.add(typ)
        self.add_entry_list(typ.size, entry)

    def add_json_file(self, json_file: str, *, threads: int = 1):
        """
        Adds the info in a serialized (gzipped) JSON file to this TypeLib

        :param json_file: string name of json file to process
        :param threads: unused number likely deprectated
        """
        other: Optional[Any] = None
        with open(json_file, "r") as other_file:
            other = TypeLibCodec.decode(other_file.read())
        if issubclass(type(other), TypeLibABC):
            # not all codec types have `.__class__.items()`
            for size, entries in other.items():  # type: ignore
                self.add_entry_list(size, entries)

    def sort(self):
        warnings.warn(
            "structure is now always sorted, see `ValueSortedDict`", DeprecationWarning
        )

    @classmethod
    def fix_bit(cls, typ):
        succeed = True
        for m in typ.layout:
            if isinstance(m, Field):
                succeed &= m.size % 8 == 0
                if not succeed:
                    break
                m.size //= 8
            elif isinstance(m, Struct):
                succeed &= cls.fix_bit(m)
        typ.size = sum(m.size for m in typ.layout)
        return succeed

    def fix(self) -> "TypeLibABC":
        """
        HACK: workaround to deal with the struct bit/bytes problem in the data.
        :return: TypeLibrary of inherited type
        """
        cls = self.__class__
        new_lib = cls()
        for size in self.keys():
            for entry in self[size]:
                succeed = True
                if isinstance(entry.typeinfo, Struct):
                    succeed &= cls.fix_bit(entry.typeinfo)
                    nsize = entry.typeinfo.size
                else:
                    nsize = size
                if succeed:
                    if nsize not in new_lib:
                        new_lib.add_entry_list(nsize, EntryList())
                    new_lib[nsize].add_entry(entry)
        return new_lib

    def make_cached_replacement_dict(self):
        self.cached_replacement_dict = defaultdict(set)
        for size in self.keys():
            if size > 1024:
                continue
            for entry in self[size]:
                self.cached_replacement_dict[
                    entry.typeinfo.accessible_offsets(),
                    entry.typeinfo.start_offsets(),
                ].add(entry.typeinfo)

    def valid_layout_for_types(self, rest_a, rest_s, typs):
        for typ in typs:
            if len(rest_a) == 0:
                return False
            ret = self.get_next_replacements(rest_a, rest_s)
            find = False
            for typ_set, a, s in ret:
                if typ in typ_set:
                    rest_a, rest_s = a, s
                    find = True
                    break
            if not find:
                return False
        return True

    def get_replacements(
        self, types: Tuple[TypeInfo, ...]
    ) -> Iterable[Tuple[TypeInfo, ...]]:
        """
        Given a list of types, get all possible lists of replacements

        :param types: tuple of types to replace
        :raises NotImplementedError: ABC stub
        """
        raise NotImplementedError

    def get_next_replacements(
        self, accessible: Tuple[int, ...], start_offsets: Tuple[int, ...]
    ) -> List[Tuple[Set[TypeInfo], Tuple[int, ...], Tuple[int, ...]]]:
        """
        Given a memory layout, get a list of next possible legal types.

        Notes:
        - The first start offset and accessible offset should be the same
        - The list returned is sorted by decreasing frequency in the library

        :param accessible: accessible (i.e., non-padding) addresses in memory
        :param start_offsets: legal offsets for the start of a type
        :return: an iterable of (type, accessible, start) tuples, where
            "type" is a legal type, "accessible" is a tuple of remaining
            accessible locations if this type is used, and "start" is the
            remaining start locations if this type is used.
        """
        if not hasattr(self, "cached_replacement_dict"):
            self.make_cached_replacement_dict()
        start = accessible[0]
        if start != start_offsets[0]:
            # print("No replacements, start != first accessible")
            return []

        # The last element of accessible is the last address in memory.
        length = (accessible[-1] - start) + 1
        replacements = []
        # Filter out types that are too long or of size zero
        for size in filter(lambda s: s <= length and s != 0, self.keys()):
            # Compute the memory layout of the remainder
            rest_accessible: Tuple[int, ...] = tuple(
                s for s in accessible if s >= (size + start)
            )
            rest_start: Tuple[int, ...] = tuple(
                s for s in start_offsets if s >= (size + start)
            )
            # If the remainder of the start offsets is not either an empty tuple
            # or if the first element of the new start offsets is not the same
            # as the first member of the new accessible, this is not a legal
            # size.
            if len(rest_start) != 0 and (
                len(rest_accessible) == 0 or rest_start[0] != rest_accessible[0]
            ):
                continue
            # If there are no more start offsets, but there are still accessible
            # offsets, this is not a legal replacement.
            if len(rest_start) == 0 and len(rest_accessible) != 0:
                continue
            shifted_cur_accessible = tuple(
                s - start for s in accessible if s < (size + start)
            )
            shifted_cur_start = tuple(
                s - start for s in start_offsets if s < (size + start)
            )
            typs: Set[TypeInfo] = self.cached_replacement_dict[
                shifted_cur_accessible, shifted_cur_start
            ]
            replacements.append((typs, rest_accessible, rest_start))
        return replacements
        #  {typ.typeinfo: (a, s) for (typ, a, s) in replacements}

    @staticmethod
    def accessible_of_types(types: Iterable[TypeInfo]) -> List[int]:
        """
        Given a list of types, get the list of accessible offsets.
        This is suitable for use with get_next_replacement.
        :param types: iterable of type info
        :return: list of offsets for each type
        """
        offset = 0
        accessible = []
        for t in types:
            accessible += [offset + a for a in t.accessible_offsets()]
            offset += t.size
        return accessible

    @staticmethod
    def start_offsets_of_types(types: Iterable[TypeInfo]) -> List[int]:
        """
        Given a list of types, get the list of accessible offsets.
        This is suitable for use with get_next_replacement.

        :param types: iterable of type info
        :return: list of offsets for each type
        """
        offset = 0
        start_offsets = []
        for t in types:
            start_offsets += [offset + s for s in t.start_offsets()]
            offset += t.size
        return start_offsets

    def items(self) -> ItemsView[int, "EntryList"]:
        return self._data.items()

    def keys(self) -> KeysView[int]:
        return self._data.keys()

    def values(self) -> ValuesView["EntryList"]:
        return self._data.values()

    @classmethod
    def load_dir(cls, path: str, *, threads: int = 1):
        """
        Loads all the serialized (gzipped) JSON files in a directory
        :param path: string path of directory to load
        :param threads: threads for multiprocessing
        :return: decoded TypeLibCodec
        """
        files = [
            os.path.join(path, f)
            for f in os.listdir(path)
            if os.path.isfile(os.path.join(path, f))
        ]
        with gzip.open(files[0], "rt") as first_serialized:
            new_lib = TypeLibCodec.decode(first_serialized.read())

        if isinstance(new_lib, cls):  # None is not a TypeLib
            for f in files[1:]:
                new_lib.add_json_file(f, threads=threads)
        return new_lib

    @classmethod
    def _from_json(cls: Type[T], d: Dict[str, Any]) -> T:
        data: DefaultDict[int, EntryList] = defaultdict(EntryList)

        # Convert lists of types into sets
        for key, lib_entry in d.items():
            if key == "T":
                continue
            entry_list: List[Entry] = [
                Entry(frequency=f, typeinfo=ti) for (f, ti) in lib_entry
            ]
            data[int(key)] = EntryList(entry_list)
        return cls(data)

    def _to_json(self) -> Dict[Any, Any]:
        """Encodes as JSON

        The 'T' field encodes which TypeInfo class is represented by this JSON:
            E: EntryList
            0: TypeLib
            1: TypeInfo
            2: Array
            3: Pointer
            4: Field
            5: Padding
            6: Struct
            7: Union
            8: Void
            9: FunctionPointer

            0: TypeInfo
            1: Array
            2: Pointer
            3: UDT.Field
            4: UDT.Padding
            5: Struct
            6: Union
            7: Void
            8: Function Pointer
        :return: json struct as dict
        """
        encoded: Dict[Any, Any] = {
            str(key): val._to_json() for key, val in self._data.items()
        }
        encoded["T"] = 0
        return encoded

    def __contains__(self, key: int) -> bool:
        return key in self._data

    def __iter__(self) -> Iterable[int]:
        for k in self._data.keys():
            yield k

    def __getitem__(self, key: int) -> "EntryList":
        return self._data[key]

    def __setitem__(self, key: int, item: "EntryList"):
        self._data[key] = item

    def __str__(self) -> str:
        ret = ""
        for n in sorted(self._data.keys()):
            ret += f"{n}: {self._data[n]}\n"
        return ret

    def prune(self, freq):
        for key in self._data:
            self._data[key].prune(freq)

        for key, entry in self._data.items():
            if len(entry) == 0:
                self._data.pop(key)


class TypelessTypeLib(TypeLibABC):
    @staticmethod
    def parse_type(typ: Any) -> TypeInfo:  # type: ignore
        return Void()

    def add_type(
        self,
        typ: Any,
        worklist: Set[str] = set(),
    ):
        return None


class TypeLibCodec:
    """Encoder/Decoder functions"""

    CodecTypes = tUnion[TypeLibABC, EntryList, TypeInfo, Member]

    _typelib_key = 0
    _classes: Dict[
        tUnion[int, str],
        tUnion[
            Type[TypeLibABC],
            Type[EntryList],
            Type[TypeInfo],
            Type[Member],
        ],
    ] = {
        "E": EntryList,
        _typelib_key: TypelessTypeLib,
        1: TypeInfo,
        2: Array,
        3: Pointer,
        4: Field,
        5: Padding,
        6: Struct,
        7: Union,
        8: Void,
        9: FunctionPointer,
        10: Disappear,
    }

    def __init__(self, typelib: Type[TypeLibABC] = TypelessTypeLib):
        self.set_typelib(typelib)

    @classmethod
    def set_typelib(cls, typelib: Type[TypeLibABC]):
        assert issubclass(typelib, TypeLibABC)
        cls._classes[cls._typelib_key] = typelib
        return True

    @staticmethod
    def decode(encoded: str) -> CodecTypes:
        """
        :param encoded: string representation of encoded TypeLibCodec
        :return: Decodes a JSON string
        """
        return loads(encoded, object_hook=TypeLibCodec.read_metadata)

    @classmethod
    def read_metadata(cls, d: Dict[str, Any]) -> "TypeLibCodec.CodecTypes":
        return cls._classes[d["T"]]._from_json(d)  # type: ignore

    class _Encoder(JSONEncoder):
        def default(self, obj: Any) -> Any:
            if hasattr(obj, "_to_json"):
                return obj._to_json()
            if isinstance(obj, set):
                return list(obj)
            return super().default(obj)

    @staticmethod
    def encode(o: CodecTypes) -> str:
        """
        :param o: instance of code cype
        :return: Encodes a TypeLib or TypeInfo as JSON
        """
        # 'separators' removes spaces after , and : for efficiency
        return dumps(o, cls=TypeLibCodec._Encoder, separators=(",", ":"))
