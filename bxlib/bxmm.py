# --------------------------------------------------------------------
from .bxast import *
from .bxtac import *

# ====================================================================
# AST to TAC lowering -- THIS IS YOUR JOB

def lower(prgm: Program, mode: str) -> list[TAC]:
    """Lower the AST `prgm` (a list of statements, see bxast.py) to
    the body of the `@main` TAC procedure.

    The result is a list of TAC instructions (see bxtac.py), e.g.:

        TAC('const', [42],         '%0')      # %0 = const 42;
        TAC('add',   ['%0', '%1'], '%2')      # %2 = add %0, %1;
        TAC('print', ['%2'])                  # print %2;

    `mode` is either 'tmm' (top-down maximal munch) or 'bmm'
    (bottom-up maximal munch).
    """

    raise NotImplementedError('AST to TAC lowering is not implemented yet')
