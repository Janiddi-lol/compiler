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

# Conditional jumps: opcode -> condition on the (integer) argument
JUMPS = {
    'jz'  : '== 0',
    'jnz' : '!= 0',
    'jl'  : '< 0' ,
    'jnl' : '>= 0',
    'jle' : '<= 0',
    'jnle': '> 0' ,
}

# --------------------------------------------------------------------
@dc.dataclass
class TAC:
    opcode    : str
    arguments : list[str | int]
    result    : Opt[str] = None

    def __str__(self):
        if self.opcode == 'label':
            return f'{self.arguments[0]}:'
        aout = self.opcode
        if self.arguments:
            aout += ' ' + ', '.join(str(x) for x in self.arguments)
        if self.result is not None:
            aout = f'{self.result} = {aout}'
        return aout + ';'

# --------------------------------------------------------------------
def tac_to_string(name: str, body: list[TAC]) -> str:
    """The textual form of a TAC procedure"""
    lines = [f'proc {name}:']
    for instr in body:
        lines.append(str(instr) if instr.opcode == 'label' else f'  {instr}')
    return '\n'.join(lines) + '\n'
