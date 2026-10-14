# --------------------------------------------------------------------
from .bxtac import TAC, TACVar, TACProc, TACUnit

# ====================================================================
# A small interpreter for TAC programs (global variables, procedures,
# labels and jumps), to test the lowering independently of the
# backend.

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

# The runtime procedures, called like any other procedure
BUILTINS = {
    '@__bx_print_int' : (1, lambda output, x: output(x)),
    '@__bx_print_bool': (1, lambda output, x: output('true' if x else 'false')),
}

# --------------------------------------------------------------------
class Interpreter:
    def __init__(self, unit: TACUnit, output):
        self.output  = output
        self.globals = {}
        self.procs   = {}

        for decl in unit:
            match decl:
                case TACVar(name, init):
                    if name in self.globals:
                        raise TACError(f'duplicate global variable {name}')
                    self.globals[name] = _wrap(init)
                case TACProc(name, _, _):
                    if name in self.procs:
                        raise TACError(f'duplicate procedure {name}')
                    self.procs[name] = decl
                case _:
                    raise TACError(f'not a TAC declaration: {decl!r}')

        if '@main' not in self.procs:
            raise TACError('no @main procedure')

    def run(self):
        self.call('@main', [])

    def call(self, name: str, args: list[int]):
        if name in BUILTINS:
            nargs, fun = BUILTINS[name]
            if len(args) != nargs:
                raise TACError(f'{name} expects {nargs} argument(s), got {len(args)}')
            return fun(self.output, *args)

        if name not in self.procs:
            raise TACError(f'call to the undefined procedure {name}')
        proc = self.procs[name]
        if len(args) != len(proc.arguments):
            raise TACError(
                f'{name} expects {len(proc.arguments)} argument(s), got {len(args)}')

        return self.execute(proc, dict(zip(proc.arguments, args)))

    def execute(self, proc: TACProc, temps: dict[str, int]):
        body   = proc.body
        labels = {}
        for i, instr in enumerate(body):
            if instr.opcode == 'label':
                label = instr.arguments[0]
                if label in labels:
                    raise TACError(f'{proc.name}: duplicate label {label}')
                labels[label] = i

        def read(x):
            if isinstance(x, str) and x.startswith('@'):
                if x not in self.globals:
                    raise TACError(f'{proc.name}: undefined global variable {x}')
                return self.globals[x]
            if x not in temps:
                raise TACError(f'{proc.name}: {x} is read before being written')
            return temps[x]

        def write(x, value):
            if x.startswith('@'):
                if x not in self.globals:
                    raise TACError(f'{proc.name}: undefined global variable {x}')
                self.globals[x] = value
            else:
                temps[x] = value

        def target(label):
            if label not in labels:
                raise TACError(f'{proc.name}: jump to the undefined label {label}')
            return labels[label]

        params = []
        pc = 0
        while pc < len(body):
            instr = body[pc]; pc += 1
            opcode, args = instr.opcode, instr.arguments

            match opcode:
                case 'nop' | 'label':
                    pass
                case 'const':
                    write(instr.result, _wrap(args[0]))
                case 'copy':
                    write(instr.result, read(args[0]))
                case 'print':
                    # the TAC `print` instruction of labs 1-2: still
                    # accepted, until you lower `print` to a call
                    self.output(read(args[0]))
                case 'param':
                    if args[0] != len(params) + 1:
                        raise TACError(f'{proc.name}: parameters out of order: {instr}')
                    params.append(read(args[1]))
                case 'call':
                    if args[1] != len(params):
                        raise TACError(
                            f'{proc.name}: {args[1]} argument(s) expected, '
                            f'{len(params)} param instruction(s) found: {instr}')
                    result, params = self.call(args[0], params), []
                    if instr.result is not None:
                        if result is None:
                            raise TACError(f'{proc.name}: {args[0]} returns no value: {instr}')
                        write(instr.result, result)
                case 'jmp':
                    pc = target(args[0])
                case 'ret':
                    return read(args[0]) if args else None
                case _ if opcode in JUMPS:
                    if JUMPS[opcode](read(args[0])):
                        pc = target(args[1])
                case _ if opcode in UNOPS:
                    write(instr.result, UNOPS[opcode](read(args[0])))
                case _ if opcode in BINOPS:
                    write(instr.result, BINOPS[opcode](read(args[0]), read(args[1])))
                case _:
                    raise TACError(f'{proc.name}: unknown opcode {opcode}: {instr}')

        raise TACError(f'{proc.name}: fell off the end of the procedure without `ret`')

# --------------------------------------------------------------------
def run(unit: TACUnit, output = print):
    """Execute the TAC program `unit`, starting from `@main`, calling
    `output` for every printed value."""

    Interpreter(unit, output).run()
