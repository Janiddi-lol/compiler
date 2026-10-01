# --------------------------------------------------------------------
import abc
import re

from .bxtac import TAC

# ====================================================================
# Straightline TAC to assembly
#
# This backend only knows the straightline fragment of TAC: constants,
# copies, the arithmetic & bitwise operators, and `print`. Every
# temporary is given a slot in the stack frame of `main`, and every
# instruction is translated in isolation. Control flow (labels, jumps)
# and procedures are the subject of the next labs.
#
# The input is the body of the `@main` procedure, as a list of TAC
# instructions (see bxtac.py).

class AsmGenError(Exception):
    pass

# --------------------------------------------------------------------
class AsmGen(abc.ABC):
    BACKENDS = {}
    NAME     = None
    SYSTEM   = None
    MACHINE  = None

    # the straightline TAC instructions: opcode -> (#arguments, has a result)
    OPCODES = {
        'nop'  : (0, False),
        'const': (1, True ),
        'copy' : (1, True ),
        'neg'  : (1, True ),
        'not'  : (1, True ),
        'add'  : (2, True ),
        'sub'  : (2, True ),
        'mul'  : (2, True ),
        'div'  : (2, True ),
        'mod'  : (2, True ),
        'and'  : (2, True ),
        'or'   : (2, True ),
        'xor'  : (2, True ),
        'shl'  : (2, True ),
        'shr'  : (2, True ),
        'print': (1, False),
    }

    TEMP = re.compile(r'%(0|[1-9][0-9]*|[A-Za-z][A-Za-z0-9_]*)\Z')

    def __init__(self):
        self._temps = dict()
        self._asm   = []

    # ---- temporaries are mapped to stack slots, on first use
    def _temp(self, temp: str) -> str:
        index = self._temps.setdefault(temp, len(self._temps))
        prelude, temp = self._format_temp(index)
        for i in prelude:
            self._emit(*i)
        return temp

    @abc.abstractmethod
    def _format_temp(self, index: int):
        pass

    # ---- assembly output
    def _get_asm(self, opcode, *args):
        if not args:
            return f'\t{opcode}'
        return f'\t{opcode}\t{", ".join(args)}'

    def _get_label(self, lbl):
        return f'{lbl}:'

    def _emit(self, opcode, *args):
        self._asm.append(self._get_asm(opcode, *args))

    def _emit_label(self, lbl):
        self._asm.append(self._get_label(lbl))

    # ---- validation of one TAC instruction
    @classmethod
    def _check(cls, instr):
        def error(msg):
            raise AsmGenError(f'{msg}: {instr!r}')

        def is_temp(x):
            return isinstance(x, str) and cls.TEMP.match(x) is not None

        def is_int64(x):
            return isinstance(x, int) and not isinstance(x, bool) \
                and -(1 << 63) <= x < (1 << 63)

        if not isinstance(instr, TAC):
            error('not a TAC instruction (see bxlib/bxtac.py)')

        opcode, args, result = instr.opcode, instr.arguments, instr.result

        if opcode not in cls.OPCODES:
            error(
                f"unsupported TAC opcode `{opcode}' "
                "(this backend only handles straightline TAC)")

        nargs, hasresult = cls.OPCODES[opcode]

        if not isinstance(args, (list, tuple)) or len(args) != nargs:
            error(f"`{opcode}' expects exactly {nargs} argument(s)")

        if hasresult and not is_temp(result):
            error(f"`{opcode}' expects a temporary as result")

        if not hasresult and result is not None:
            error(f"`{opcode}' does not produce a result")

        for arg in args:
            if opcode == 'const':
                if not is_int64(arg):
                    error("`const' expects a 64-bit integer argument")
            elif not is_temp(arg):
                error(f"`{opcode}' expects temporaries as arguments")

        return opcode, list(args) + ([result] if hasresult else [])

    # ---- translation of one TAC instruction
    def __call__(self, instr: TAC):
        opcode, args = self._check(instr)
        getattr(self, f'_emit_{opcode}')(*args)

    def _emit_nop(self):
        pass

    @abc.abstractmethod
    def _prologue(self, nslots: int) -> list[str]:
        pass

    @abc.abstractmethod
    def _epilogue(self) -> list[str]:
        pass

    @classmethod
    def lower(cls, body: list[TAC]) -> str:
        emitter = cls()

        for instr in body:
            emitter(instr)

        nslots  = len(emitter._temps)
        nslots += nslots & 1    # keep the stack 16-bytes aligned

        aout = emitter._prologue(nslots) + emitter._asm + emitter._epilogue()

        return "\n".join(aout) + "\n"

    # ---- backends registry
    @classmethod
    def get_backend(cls, name: str):
        return cls.BACKENDS[name]

    @classmethod
    def select_backend(cls, system: str, machine: str):
        for backend in cls.BACKENDS.values():
            if system == backend.SYSTEM and machine == backend.MACHINE:
                return backend
        return None

    @classmethod
    def register(cls, backend):
        cls.BACKENDS[backend.NAME] = backend

# --------------------------------------------------------------------
class AsmGen_x64_Linux(AsmGen):
    NAME    = 'x64-linux'
    SYSTEM  = 'Linux'
    MACHINE = 'x86_64'

    def _format_temp(self, index):
        return [], f'-{8*(index+1)}(%rbp)'

    def _emit_const(self, ctt, dst):
        if -(1 << 31) <= ctt < (1 << 31):
            self._emit('movq', f'${ctt}', self._temp(dst))
        else:
            self._emit('movabsq', f'${ctt}', '%r11')
            self._emit('movq', '%r11', self._temp(dst))

    def _emit_copy(self, src, dst):
        self._emit('movq', self._temp(src), '%r11')
        self._emit('movq', '%r11', self._temp(dst))

    def _emit_alu1(self, opcode, src, dst):
        self._emit('movq', self._temp(src), '%r11')
        self._emit(opcode, '%r11')
        self._emit('movq', '%r11', self._temp(dst))

    def _emit_neg(self, src, dst):
        self._emit_alu1('negq', src, dst)

    def _emit_not(self, src, dst):
        self._emit_alu1('notq', src, dst)

    def _emit_alu2(self, opcode, op1, op2, dst):
        self._emit('movq', self._temp(op1), '%r11')
        self._emit(opcode, self._temp(op2), '%r11')
        self._emit('movq', '%r11', self._temp(dst))

    def _emit_add(self, op1, op2, dst):
        self._emit_alu2('addq', op1, op2, dst)

    def _emit_sub(self, op1, op2, dst):
        self._emit_alu2('subq', op1, op2, dst)

    def _emit_mul(self, op1, op2, dst):
        self._emit('movq', self._temp(op1), '%rax')
        self._emit('imulq', self._temp(op2))
        self._emit('movq', '%rax', self._temp(dst))

    def _emit_div(self, op1, op2, dst):
        self._emit('movq', self._temp(op1), '%rax')
        self._emit('cqto')
        self._emit('idivq', self._temp(op2))
        self._emit('movq', '%rax', self._temp(dst))

    def _emit_mod(self, op1, op2, dst):
        self._emit('movq', self._temp(op1), '%rax')
        self._emit('cqto')
        self._emit('idivq', self._temp(op2))
        self._emit('movq', '%rdx', self._temp(dst))

    def _emit_and(self, op1, op2, dst):
        self._emit_alu2('andq', op1, op2, dst)

    def _emit_or(self, op1, op2, dst):
        self._emit_alu2('orq', op1, op2, dst)

    def _emit_xor(self, op1, op2, dst):
        self._emit_alu2('xorq', op1, op2, dst)

    def _emit_shift(self, opcode, op1, op2, dst):
        self._emit('movq', self._temp(op1), '%r11')
        self._emit('movq', self._temp(op2), '%rcx')
        self._emit(opcode, '%cl', '%r11')
        self._emit('movq', '%r11', self._temp(dst))

    def _emit_shl(self, op1, op2, dst):
        self._emit_shift('salq', op1, op2, dst)

    def _emit_shr(self, op1, op2, dst):
        self._emit_shift('sarq', op1, op2, dst)

    def _emit_print(self, src):
        self._emit('leaq', '.Lprintfmt(%rip)', '%rdi')
        self._emit('movq', self._temp(src), '%rsi')
        self._emit('xorq', '%rax', '%rax')
        self._emit('callq', 'printf@PLT')

    def _prologue(self, nslots):
        return [
            self._get_asm('.section', '.rodata'),
            self._get_label('.Lprintfmt'),
            self._get_asm('.string', '"%ld\\n"'),
            self._get_asm('.text'),
            self._get_asm('.globl', 'main'),
            self._get_label('main'),
            self._get_asm('pushq', '%rbp'),
            self._get_asm('movq', '%rsp', '%rbp'),
            self._get_asm('subq', f'${8*nslots}', '%rsp'),
        ]

    def _epilogue(self):
        return [
            self._get_asm('movq', '%rbp', '%rsp'),
            self._get_asm('popq', '%rbp'),
            self._get_asm('xorq', '%rax', '%rax'),
            self._get_asm('retq'),
        ]

AsmGen.register(AsmGen_x64_Linux)

# --------------------------------------------------------------------
class AsmGen_arm64_Darwin(AsmGen):
    NAME    = 'arm64-apple-darwin'
    SYSTEM  = 'Darwin'
    MACHINE = 'arm64'

    @staticmethod
    def _sub_imm(dst, src, imm):
        # `sub` takes a 12-bits immediate, optionally shifted by 12
        # bits: larger offsets (up to 16MB) need two instructions
        assert 0 <= imm < (1 << 24)
        aout = []
        if imm >= (1 << 12):
            aout.append(('sub', dst, src, f'#{imm >> 12}', 'lsl 12'))
            src, imm = dst, imm & 0xfff
        if imm != 0 or not aout:
            aout.append(('sub', dst, src, f'#{imm}'))
        return aout

    def _format_temp(self, index):
        index = 8*(index+1)
        if index > 256:
            return self._sub_imm('X15', 'FP', index), '[X15]'
        return [], f'[FP, #-{index}]'

    def _emit_const(self, ctt, dst):
        if ctt < 0:
            ctt = (1 << 64) + ctt
        self._emit('movz', 'X9', f'#{ctt & 0xffff}')
        ctt, i = (ctt >> 16), 1
        while ctt != 0:
            self._emit('movk', 'X9', f'#{ctt & 0xffff}', f'lsl {16*i}')
            ctt >>= 16; i += 1
        self._emit('str', 'X9', self._temp(dst))

    def _emit_copy(self, src, dst):
        self._emit('ldr', 'X9', self._temp(src))
        self._emit('str', 'X9', self._temp(dst))

    def _emit_alu1(self, opcode, src, dst):
        self._emit('ldr', 'X9', self._temp(src))
        self._emit(opcode, 'X10', 'X9')
        self._emit('str', 'X10', self._temp(dst))

    def _emit_neg(self, src, dst):
        self._emit_alu1('neg', src, dst)

    def _emit_not(self, src, dst):
        self._emit_alu1('mvn', src, dst)

    def _emit_alu2(self, opcode, op1, op2, dst):
        self._emit('ldr', 'X9', self._temp(op1))
        self._emit('ldr', 'X10', self._temp(op2))
        self._emit(opcode, 'X11', 'X9', 'X10')
        self._emit('str', 'X11', self._temp(dst))

    def _emit_add(self, op1, op2, dst):
        self._emit_alu2('add', op1, op2, dst)

    def _emit_sub(self, op1, op2, dst):
        self._emit_alu2('sub', op1, op2, dst)

    def _emit_mul(self, op1, op2, dst):
        self._emit_alu2('mul', op1, op2, dst)

    def _emit_div(self, op1, op2, dst):
        self._emit_alu2('sdiv', op1, op2, dst)

    def _emit_mod(self, op1, op2, dst):
        self._emit('ldr' , 'X9', self._temp(op1))
        self._emit('ldr' , 'X10', self._temp(op2))
        self._emit('sdiv', 'X11', 'X9', 'X10')
        self._emit('msub', 'X11', 'X11', 'X10', 'X9')
        self._emit('str' , 'X11', self._temp(dst))

    def _emit_and(self, op1, op2, dst):
        self._emit_alu2('and', op1, op2, dst)

    def _emit_or(self, op1, op2, dst):
        self._emit_alu2('orr', op1, op2, dst)

    def _emit_xor(self, op1, op2, dst):
        self._emit_alu2('eor', op1, op2, dst)

    def _emit_shl(self, op1, op2, dst):
        self._emit_alu2('lsl', op1, op2, dst)

    def _emit_shr(self, op1, op2, dst):
        self._emit_alu2('asr', op1, op2, dst)

    def _emit_print(self, src):
        # printf is variadic: on arm64/macOS, variadic arguments go
        # on the stack (16-bytes aligned)
        self._emit('ldr' , 'X9', self._temp(src))
        self._emit('str' , 'X9', '[SP, #-16]!')
        self._emit('adrp', 'X0', 'l._printfmt@PAGE')
        self._emit('add' , 'X0', 'X0', 'l._printfmt@PAGEOFF')
        self._emit('bl'  , '_printf')
        self._emit('add' , 'SP', 'SP', '#16')

    def _prologue(self, nslots):
        return [
            self._get_asm('.text'),
            self._get_asm('.globl', '_main'),
            self._get_asm('.align', '4'),
            self._get_label('_main'),
            self._get_asm('stp', 'FP', 'LR', '[SP, #-16]!'),
            self._get_asm('mov', 'FP', 'SP'),
        ] + [self._get_asm(*i) for i in self._sub_imm('SP', 'SP', 8*nslots)]

    def _epilogue(self):
        return [
            self._get_asm('mov', 'SP', 'FP'),
            self._get_asm('ldp', 'FP', 'LR', '[SP]', '#16'),
            self._get_asm('mov', 'X0', '#0'),
            self._get_asm('ret'),
            self._get_asm('.data'),
            self._get_label('l._printfmt'),
            self._get_asm('.asciz', '"%lld\\n"'),
        ]

AsmGen.register(AsmGen_arm64_Darwin)

# --------------------------------------------------------------------
class AsmGen_arm64_Linux(AsmGen_arm64_Darwin):
    NAME    = 'arm64-linux'
    SYSTEM  = 'Linux'
    MACHINE = 'aarch64'

    def _emit_print(self, src):
        # on Linux, variadic arguments are passed in registers
        self._emit('ldr' , 'X1', self._temp(src))
        self._emit('adrp', 'X0', '.Lprintfmt')
        self._emit('add' , 'X0', 'X0', ':lo12:.Lprintfmt')
        self._emit('bl'  , 'printf')

    def _prologue(self, nslots):
        return [
            self._get_asm('.text'),
            self._get_asm('.globl', 'main'),
            self._get_label('main'),
            self._get_asm('stp', 'FP', 'LR', '[SP, #-16]!'),
            self._get_asm('mov', 'FP', 'SP'),
        ] + [self._get_asm(*i) for i in self._sub_imm('SP', 'SP', 8*nslots)]

    def _epilogue(self):
        return [
            self._get_asm('mov', 'SP', 'FP'),
            self._get_asm('ldp', 'FP', 'LR', '[SP]', '#16'),
            self._get_asm('mov', 'X0', '#0'),
            self._get_asm('ret'),
            self._get_asm('.section', '.rodata'),
            self._get_label('.Lprintfmt'),
            self._get_asm('.asciz', '"%lld\\n"'),
        ]

AsmGen.register(AsmGen_arm64_Linux)
