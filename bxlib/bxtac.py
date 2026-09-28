# --------------------------------------------------------------------
import dataclasses as dc

from typing import Optional as Opt

# ====================================================================
# Three-Address Code

# BX operator names (as produced by the parser) -> TAC opcodes
OPCODES = {
    'opposite'              : 'neg',
    'addition'              : 'add',
    'subtraction'           : 'sub',
    'multiplication'        : 'mul',
    'division'              : 'div',
    'modulus'               : 'mod',
    'bitwise-negation'      : 'not',
    'bitwise-and'           : 'and',
    'bitwise-or'            :  'or',
    'bitwise-xor'           : 'xor',
    'left-shift'            : 'shl',
    'arithmetic-right-shift': 'shr',
}

# --------------------------------------------------------------------
@dc.dataclass
class TAC:
    opcode    : str
    arguments : list[str | int]
    result    : Opt[str] = None

    def __str__(self):
        aout = self.opcode
        if self.arguments:
            aout += ' ' + ', '.join(str(x) for x in self.arguments)
        if self.result is not None:
            aout = f'{self.result} = {aout}'
        return aout + ';'

# --------------------------------------------------------------------
def tac_to_string(name: str, body: list[TAC]) -> str:
    """The textual form of a TAC procedure"""
    return '\n'.join([f'proc {name}:'] + [f'  {instr}' for instr in body]) + '\n'
