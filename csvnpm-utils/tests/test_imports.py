import csvnpm
import pytest
from csvnpm.binary import function, ida_ast
from csvnpm.binary.types import member, typeinfo, typelib, udt
from csvnpm.dataset_gen import generate, lexer
from csvnpm.dataset_gen.decompiler import collect, debug, dump_trees
from csvnpm.ida import idaapi


@pytest.mark.commit
def test_donothing():
    assert True
