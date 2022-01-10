from typing import List, Set
from typing import Union as tUnion

from csvnpm.binary.types.member import Field, Member
from csvnpm.binary.types.typeinfo import Array, FunctionPointer, Pointer, Void
from csvnpm.binary.types.typelib import TypeInfo, TypeLibABC
from csvnpm.binary.types.udt import Padding, Struct, Union
from csvnpm.ida import ida_typeinf


class TypeLib(TypeLibABC):
    @staticmethod
    def parse_type(typ: ida_typeinf.tinfo_t) -> TypeInfo:  # type: ignore
        """
        Parses an IDA tinfo_t object

        :param typ: type as defined by ida
        :return: CSNVPM compliant TypeInfo for use in DIRTY
        """
        if typ.is_void():
            return Void()
        if typ.is_funcptr() or "(" in typ.dstr():
            return FunctionPointer(name=typ.dstr())
        if typ.is_decl_ptr():
            return Pointer(typ.get_pointed_object().dstr())
        if typ.is_array():
            # To get array type info, first create an
            # array_type_data_t then call get_array_details to
            # populate it. Unions and structs follow a similar
            # pattern.
            array_info = ida_typeinf.array_type_data_t()
            typ.get_array_details(array_info)
            nelements = array_info.nelems
            element_size = array_info.elem_type.get_size()
            element_type = array_info.elem_type.dstr()
            return Array(
                nelements=nelements,
                element_size=element_size,
                element_type=element_type,
            )
        if typ.is_udt():
            udt_info = ida_typeinf.udt_type_data_t()
            typ.get_udt_details(udt_info)
            name = typ.dstr()
            size = udt_info.total_size
            nmembers = typ.get_udt_nmembers()
            if typ.is_union():
                members = []
                largest_size = 0
                for n in range(nmembers):
                    member = ida_typeinf.udt_member_t()
                    # To get the nth member set OFFSET to n and tell find_udt_member
                    # to search by index.
                    member.offset = n
                    typ.find_udt_member(member, ida_typeinf.STRMEM_INDEX)
                    largest_size = max(largest_size, member.size)
                    type_name = member.type.dstr()
                    members.append(
                        Field(
                            name=member.name,
                            size=member.size,
                            type_name=type_name,
                        )
                    )
                end_padding = size - (largest_size // 8)
                if end_padding == 0:
                    return Union(name=name, members=members)
                return Union(
                    name=name,
                    members=members,
                    padding=Padding(end_padding),
                )
            else:
                # UDT is a struct
                layout: List[tUnion[Member, Struct, Union]] = []
                next_offset = 0
                for n in range(nmembers):
                    member = ida_typeinf.udt_member_t()
                    member.offset = n
                    typ.find_udt_member(member, ida_typeinf.STRMEM_INDEX)
                    # Check for padding. Careful, because offset and
                    # size are in bits, not bytes.
                    if member.offset != next_offset:
                        layout.append(Padding((member.offset - next_offset) // 8))
                    next_offset = member.offset + member.size
                    type_name = member.type.dstr()
                    layout.append(
                        Field(
                            name=member.name,
                            size=member.size,
                            type_name=type_name,
                        )
                    )
                # Check for padding at the end
                end_padding = size - next_offset // 8
                if end_padding > 0:
                    layout.append(Padding(end_padding))
                return Struct(name=name, layout=layout)
        return TypeInfo(name=typ.dstr(), size=typ.get_size())

    def add_type(
        self,
        typ: ida_typeinf.tinfo_t,
        worklist: Set[str] = set(),
    ):
        """
        Adds an element to the TypeLib by parsing an IDA tinfo_t object

        :param typ: types as defined by ida
        :param worklist: set of found types nested within current type
        """
        if typ.dstr() in worklist or typ.is_void():
            return
        worklist.add(typ.dstr())
        new_type: TypeInfo = self.parse_type(typ)
        # If this type isn't a duplicate, break down the subtypes
        if not self._data[new_type.size].add(new_type):
            if typ.is_decl_ptr() and not (typ.is_funcptr() or "(" in typ.dstr()):
                self.add_type(typ.get_pointed_object(), worklist)
            elif typ.is_array():
                self.add_type(typ.get_array_element(), worklist)
            elif typ.is_udt():
                udt_info = ida_typeinf.udt_type_data_t()
                typ.get_udt_details(udt_info)
                name = typ.dstr()  # noqa: F841
                size = udt_info.total_size  # noqa: F841
                nmembers = typ.get_udt_nmembers()
                for n in range(nmembers):
                    member = ida_typeinf.udt_member_t()
                    # To get the nth member set OFFSET to n and tell find_udt_member
                    # to search by index.
                    member.offset = n
                    typ.find_udt_member(member, ida_typeinf.STRMEM_INDEX)
                    self.add_type(member.type, worklist)
