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

# Conditional jumps: opcode -> condition on the (integer) argument.
# Control also has `jmp LABEL`, `ret` / `ret VALUE` (exit from the
# procedure), and `param N, VALUE` / `RESULT = call @PROC, N` for calls.
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
# A TAC program (compilation unit) is a list of global variables and
# procedures. Globals are named `@x` and are valid operands wherever a
# temporary is. Procedures are named `@f`; their parameters are the
# named temporaries `%x`.

@dc.dataclass
class TACVar:
    name  : str                 # @x
    init  : int

    def __str__(self):
        return f'var {self.name} = {self.init};'

@dc.dataclass
class TACProc:
    name      : str             # @f
    arguments : list[str]       # [%x, %y]
    body      : list[TAC]

    def __str__(self):
        head = self.name
        if self.arguments:
            head += '(' + ', '.join(self.arguments) + ')'
        lines = [f'proc {head}:']
        for instr in self.body:
            lines.append(str(instr) if instr.opcode == 'label' else f'  {instr}')
        return '\n'.join(lines)

TACUnit = list[TACVar | TACProc]

# --------------------------------------------------------------------
def unit_to_string(unit: TACUnit) -> str:
    """The textual form of a TAC program"""
    return '\n\n'.join(str(decl) for decl in unit) + '\n'
