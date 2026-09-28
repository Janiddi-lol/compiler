# --------------------------------------------------------------------
from .bxtac import TAC

# ====================================================================
# A small interpreter for TAC (with labels and jumps), to test the
# lowering before the backend handles jumps.

class TACError(Exception):
    pass

MASK = (1 << 64) - 1

def _wrap(x: int) -> int:
    x &= MASK
    return x - (1 << 64) if x >> 63 else x

def _div(a: int, b: int) -> int:
    if b == 0:
        raise TACError('division by zero')
    q = abs(a) // abs(b)
    return _wrap(q if (a < 0) == (b < 0) else -q)

BINOPS = {
    'add': lambda a, b: _wrap(a + b),
    'sub': lambda a, b: _wrap(a - b),
    'mul': lambda a, b: _wrap(a * b),
    'div': _div,
    'mod': lambda a, b: _wrap(a - _div(a, b) * b),
    'and': lambda a, b: _wrap(a & b),
    'or' : lambda a, b: _wrap(a | b),
    'xor': lambda a, b: _wrap(a ^ b),
    'shl': lambda a, b: _wrap(a << (b & 63)),
    'shr': lambda a, b: _wrap(a >> (b & 63)),
}

UNOPS = {
    'neg': lambda a: _wrap(-a),
    'not': lambda a: _wrap(~a),
}

JUMPS = {
    'jz'  : lambda a: a == 0,
    'jnz' : lambda a: a != 0,
    'jl'  : lambda a: a <  0,
    'jnl' : lambda a: a >= 0,
    'jle' : lambda a: a <= 0,
    'jnle': lambda a: a >  0,
}

# --------------------------------------------------------------------
def run(body: list[TAC], output = print):
    """Execute the TAC instructions of `body`, calling `output` for
    every `print`. Reading a temporary that was never written is an
    error, as is jumping to an undefined label."""

    labels = {}
    for i, instr in enumerate(body):
        if instr.opcode == 'label':
            label = instr.arguments[0]
            if label in labels:
                raise TACError(f'duplicate label {label}')
            labels[label] = i

    temps = {}

    def read(temp):
        if temp not in temps:
            raise TACError(f'temporary {temp} is read before being written')
        return temps[temp]

    def target(label):
        if label not in labels:
            raise TACError(f'jump to the undefined label {label}')
        return labels[label]

    pc = 0
    while pc < len(body):
        instr = body[pc]; pc += 1
        opcode, args = instr.opcode, instr.arguments

        match opcode:
            case 'nop' | 'label':
                pass
            case 'const':
                temps[instr.result] = _wrap(args[0])
            case 'copy':
                temps[instr.result] = read(args[0])
            case 'print':
                output(read(args[0]))
            case 'jmp':
                pc = target(args[0])
            case _ if opcode in JUMPS:
                if JUMPS[opcode](read(args[0])):
                    pc = target(args[1])
            case _ if opcode in UNOPS:
                temps[instr.result] = UNOPS[opcode](read(args[0]))
            case _ if opcode in BINOPS:
                temps[instr.result] = BINOPS[opcode](read(args[0]), read(args[1]))
            case _:
                raise TACError(f'unknown opcode {opcode}: {instr}')
