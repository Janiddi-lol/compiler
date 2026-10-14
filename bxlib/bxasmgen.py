# --------------------------------------------------------------------
import abc
import re

from .bxtac import JUMPS, TAC, TACProc, TACUnit, TACVar


class AsmGenError(Exception):
    pass


class AsmGen(abc.ABC):
    BACKENDS = {}
    NAME = None
    SYSTEM = None
    MACHINE = None

    SIMPLE_OPCODES = {
        'nop': (0, False),
        'const': (1, True),
        'copy': (1, True),
        'neg': (1, True),
        'not': (1, True),
        'add': (2, True),
        'sub': (2, True),
        'mul': (2, True),
        'div': (2, True),
        'mod': (2, True),
        'and': (2, True),
        'or': (2, True),
        'xor': (2, True),
        'shl': (2, True),
        'shr': (2, True),
        'print': (1, False),       # retained for Lab 1/2 TAC compatibility
        'label': (1, False),
        'jmp': (1, False),
        'jz': (2, False),
        'jnz': (2, False),
        'jl': (2, False),
        'jnl': (2, False),
        'jle': (2, False),
        'jnle': (2, False),
    }

    TEMP = re.compile(r'%(0|[1-9][0-9]*|[A-Za-z][A-Za-z0-9_]*)\Z')
    GLOBAL = re.compile(r'@[A-Za-z_][A-Za-z0-9_]*\Z')
    LABEL = re.compile(r'%\.L(0|[1-9][0-9]*|[A-Za-z_][A-Za-z0-9_]*)\Z')

    def __init__(self, proc: TACProc, globals_: set[str]):
        self.proc = proc
        self.globals = globals_
        self._asm: list[str] = []
        self._pending_params: dict[int, str] = {}
        self._temps: dict[str, int] = {}
        for argument in proc.arguments:
            self._record_temp(argument)
        for instruction in proc.body:
            if isinstance(instruction, TAC):
                for operand in instruction.arguments:
                    self._record_temp(operand)
                self._record_temp(instruction.result)

    def _record_temp(self, operand):
        if isinstance(operand, str) and self.TEMP.fullmatch(operand):
            self._temps.setdefault(operand, len(self._temps))

    def _slot(self, temp: str) -> int:
        return self._temps[temp]

    def _get_asm(self, opcode, *args):
        return f'\t{opcode}' if not args else f'\t{opcode}\t{", ".join(args)}'

    def _get_label(self, label):
        return f'{label}:'

    def _emit(self, opcode, *args):
        self._asm.append(self._get_asm(opcode, *args))

    @property
    def _proc_id(self) -> str:
        return self.proc.name[1:]

    def _label(self, label: str) -> str:
        return f'.Lbx.{self._proc_id}.{label[3:]}'

    @property
    def _end_label(self) -> str:
        return f'.Lbx.{self._proc_id}.end'

    def _emit_label(self, label):
        self._asm.append(self._get_label(self._label(label)))

    def _is_operand(self, value) -> bool:
        return (
            isinstance(value, str)
            and (
                self.TEMP.fullmatch(value) is not None
                or (
                    self.GLOBAL.fullmatch(value) is not None
                    and value in self.globals
                )
            )
        )

    def _error(self, message: str, instruction: TAC):
        raise AsmGenError(f'{self.proc.name}: {message}: {instruction!r}')

    def _check(self, instruction: TAC):
        if not isinstance(instruction, TAC):
            raise AsmGenError(f'{self.proc.name}: not a TAC instruction: {instruction!r}')

        opcode = instruction.opcode
        arguments = instruction.arguments
        result = instruction.result
        if not isinstance(arguments, (list, tuple)):
            self._error('arguments must be a list or tuple', instruction)

        if opcode in self.SIMPLE_OPCODES:
            nargs, has_result = self.SIMPLE_OPCODES[opcode]
            if len(arguments) != nargs:
                self._error(f"`{opcode}' expects {nargs} argument(s)", instruction)
            if has_result != (result is not None):
                self._error(
                    f"`{opcode}' {'expects' if has_result else 'does not produce'} a result",
                    instruction,
                )
            if has_result and not self._is_operand(result):
                self._error('invalid result operand', instruction)
            for index, argument in enumerate(arguments):
                if opcode == 'const':
                    if not (
                        isinstance(argument, int)
                        and not isinstance(argument, bool)
                        and -(1 << 63) <= argument < (1 << 63)
                    ):
                        self._error("`const' expects a 64-bit integer", instruction)
                elif opcode in ('label', 'jmp') or (opcode in JUMPS and index == 1):
                    if not isinstance(argument, str) or not self.LABEL.fullmatch(argument):
                        self._error('invalid label', instruction)
                elif not self._is_operand(argument):
                    self._error('invalid operand', instruction)
            return

        if opcode == 'param':
            if (
                len(arguments) != 2
                or not isinstance(arguments[0], int)
                or isinstance(arguments[0], bool)
                or arguments[0] < 1
                or not self._is_operand(arguments[1])
                or result is not None
            ):
                self._error("invalid `param' instruction", instruction)
            return

        if opcode == 'call':
            if (
                len(arguments) != 2
                or not isinstance(arguments[0], str)
                or self.GLOBAL.fullmatch(arguments[0]) is None
                or not isinstance(arguments[1], int)
                or isinstance(arguments[1], bool)
                or arguments[1] < 0
                or (result is not None and not self._is_operand(result))
            ):
                self._error("invalid `call' instruction", instruction)
            return

        if opcode == 'ret':
            if len(arguments) not in (0, 1) or result is not None:
                self._error("invalid `ret' instruction", instruction)
            if arguments and not self._is_operand(arguments[0]):
                self._error('invalid return operand', instruction)
            return

        self._error(f"unsupported TAC opcode `{opcode}'", instruction)

    def __call__(self, instruction: TAC):
        self._check(instruction)
        getattr(self, f'_emit_{instruction.opcode}')(
            *instruction.arguments,
            *([] if instruction.result is None else [instruction.result]),
        )

    def _emit_nop(self):
        pass

    def _emit_param(self, index, value):
        if index in self._pending_params:
            raise AsmGenError(f'{self.proc.name}: duplicate parameter {index}')
        self._pending_params[index] = value

    @classmethod
    def check_labels(cls, proc: TACProc):
        labels: set[str] = set()
        for instruction in proc.body:
            if isinstance(instruction, TAC) and instruction.opcode == 'label':
                label = instruction.arguments[0]
                if label in labels:
                    raise AsmGenError(f'{proc.name}: duplicate label: {instruction}')
                labels.add(label)
        for instruction in proc.body:
            if isinstance(instruction, TAC) and (
                instruction.opcode == 'jmp' or instruction.opcode in JUMPS
            ):
                if instruction.arguments[-1] not in labels:
                    raise AsmGenError(
                        f'{proc.name}: jump to an undefined label: {instruction}'
                    )

    @classmethod
    def lower(cls, unit: TACUnit) -> str:
        globals_: dict[str, int] = {}
        procedures: set[str] = set()
        declarations: list[TACProc] = []

        for declaration in unit:
            match declaration:
                case TACVar(name, init):
                    if cls.GLOBAL.fullmatch(name) is None:
                        raise AsmGenError(f'invalid global variable name: {name!r}')
                    if name in globals_:
                        raise AsmGenError(f'duplicate global variable: {name}')
                    globals_[name] = init
                case TACProc(name, arguments, _):
                    if cls.GLOBAL.fullmatch(name) is None:
                        raise AsmGenError(f'invalid procedure name: {name!r}')
                    if name in procedures:
                        raise AsmGenError(f'duplicate procedure: {name}')
                    if any(cls.TEMP.fullmatch(argument) is None for argument in arguments):
                        raise AsmGenError(f'{name}: invalid formal argument')
                    procedures.add(name)
                    declarations.append(declaration)
                case _:
                    raise AsmGenError(f'not a TAC declaration: {declaration!r}')

        if '@main' not in procedures:
            raise AsmGenError('no @main procedure')

        sections = cls._global_section(globals_)
        known_globals = set(globals_)
        for proc in declarations:
            cls.check_labels(proc)
            emitter = cls(proc, known_globals)
            for instruction in proc.body:
                emitter(instruction)
            if emitter._pending_params:
                raise AsmGenError(f'{proc.name}: param instruction(s) without a call')
            sections.extend(emitter._procedure())
        return '\n'.join(sections) + '\n'

    @classmethod
    @abc.abstractmethod
    def _global_section(cls, globals_: dict[str, int]) -> list[str]:
        pass

    @abc.abstractmethod
    def _procedure(self) -> list[str]:
        pass

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


class AsmGen_x64_Linux(AsmGen):
    NAME = 'x64-linux'
    SYSTEM = 'Linux'
    MACHINE = 'x86_64'
    ARGUMENT_REGISTERS = ('%rdi', '%rsi', '%rdx', '%rcx', '%r8', '%r9')

    @staticmethod
    def _symbol(name: str) -> str:
        return name[1:]

    @staticmethod
    def _global_symbol(name: str) -> str:
        return f'bx.{name[1:]}'

    def _location(self, operand: str) -> str:
        if operand.startswith('@'):
            return f'{self._global_symbol(operand)}(%rip)'
        return f'-{8 * (self._slot(operand) + 1)}(%rbp)'

    def _emit_const(self, constant, destination):
        if -(1 << 31) <= constant < (1 << 31):
            self._emit('movq', f'${constant}', self._location(destination))
        else:
            self._emit('movabsq', f'${constant}', '%r11')
            self._emit('movq', '%r11', self._location(destination))

    def _emit_copy(self, source, destination):
        self._emit('movq', self._location(source), '%r11')
        self._emit('movq', '%r11', self._location(destination))

    def _emit_alu1(self, opcode, source, destination):
        self._emit('movq', self._location(source), '%r11')
        self._emit(opcode, '%r11')
        self._emit('movq', '%r11', self._location(destination))

    def _emit_neg(self, source, destination): self._emit_alu1('negq', source, destination)
    def _emit_not(self, source, destination): self._emit_alu1('notq', source, destination)

    def _emit_alu2(self, opcode, left, right, destination):
        self._emit('movq', self._location(left), '%r11')
        self._emit(opcode, self._location(right), '%r11')
        self._emit('movq', '%r11', self._location(destination))

    def _emit_add(self, a, b, d): self._emit_alu2('addq', a, b, d)
    def _emit_sub(self, a, b, d): self._emit_alu2('subq', a, b, d)
    def _emit_and(self, a, b, d): self._emit_alu2('andq', a, b, d)
    def _emit_or(self, a, b, d): self._emit_alu2('orq', a, b, d)
    def _emit_xor(self, a, b, d): self._emit_alu2('xorq', a, b, d)

    def _emit_mul(self, left, right, destination):
        self._emit('movq', self._location(left), '%rax')
        self._emit('imulq', self._location(right))
        self._emit('movq', '%rax', self._location(destination))

    def _emit_divmod(self, left, right, destination, remainder):
        self._emit('movq', self._location(left), '%rax')
        self._emit('cqto')
        self._emit('idivq', self._location(right))
        self._emit('movq', '%rdx' if remainder else '%rax', self._location(destination))

    def _emit_div(self, a, b, d): self._emit_divmod(a, b, d, False)
    def _emit_mod(self, a, b, d): self._emit_divmod(a, b, d, True)

    def _emit_shift(self, opcode, left, right, destination):
        self._emit('movq', self._location(left), '%r11')
        self._emit('movq', self._location(right), '%rcx')
        self._emit(opcode, '%cl', '%r11')
        self._emit('movq', '%r11', self._location(destination))

    def _emit_shl(self, a, b, d): self._emit_shift('salq', a, b, d)
    def _emit_shr(self, a, b, d): self._emit_shift('sarq', a, b, d)

    def _emit_jmp(self, label): self._emit('jmp', self._label(label))

    def _emit_cjmp(self, opcode, source, label):
        self._emit('cmpq', '$0', self._location(source))
        self._emit(opcode, self._label(label))

    def _emit_jz(self, s, l): self._emit_cjmp('jz', s, l)
    def _emit_jnz(self, s, l): self._emit_cjmp('jnz', s, l)
    def _emit_jl(self, s, l): self._emit_cjmp('jl', s, l)
    def _emit_jnl(self, s, l): self._emit_cjmp('jge', s, l)
    def _emit_jle(self, s, l): self._emit_cjmp('jle', s, l)
    def _emit_jnle(self, s, l): self._emit_cjmp('jg', s, l)

    def _emit_ret(self, *value):
        if value:
            self._emit('movq', self._location(value[0]), '%rax')
        else:
            self._emit('xorq', '%rax', '%rax')
        self._emit('jmp', self._end_label)

    def _emit_call(self, procedure, nargs, *destination):
        if set(self._pending_params) != set(range(1, nargs + 1)):
            raise AsmGenError(f'{self.proc.name}: malformed parameters for call {procedure}')

        stack_count = max(0, nargs - len(self.ARGUMENT_REGISTERS))
        stack_size = 8 * (stack_count + (stack_count & 1))
        if stack_size:
            self._emit('subq', f'${stack_size}', '%rsp')

        for index in range(7, nargs + 1):
            value = self._pending_params[index]
            self._emit('movq', self._location(value), '%r11')
            self._emit('movq', '%r11', f'{8 * (index - 7)}(%rsp)')
        for index, register in enumerate(self.ARGUMENT_REGISTERS[:nargs], start=1):
            self._emit('movq', self._location(self._pending_params[index]), register)

        self._emit('callq', self._symbol(procedure))
        if stack_size:
            self._emit('addq', f'${stack_size}', '%rsp')
        if destination:
            self._emit('movq', '%rax', self._location(destination[0]))
        self._pending_params.clear()

    def _emit_print(self, source):
        self._pending_params[1] = source
        self._emit_call('@__bx_print_int', 1)

    @classmethod
    def _global_section(cls, globals_):
        if not globals_:
            return []
        result = ['\t.data']
        for name, value in globals_.items():
            symbol = cls._global_symbol(name)
            result.extend(('\t.p2align\t3', f'{symbol}:', f'\t.quad\t{value}'))
        return result

    def _procedure(self):
        nslots = len(self._temps) + (len(self._temps) & 1)
        symbol = self._symbol(self.proc.name)
        prefix = [
            '\t.text', f'\t.globl\t{symbol}', f'\t.type\t{symbol}, @function',
            f'{symbol}:', '\tpushq\t%rbp', '\tmovq\t%rsp, %rbp',
            f'\tsubq\t${8 * nslots}, %rsp',
        ]
        for index, argument in enumerate(self.proc.arguments):
            destination = self._location(argument)
            if index < len(self.ARGUMENT_REGISTERS):
                prefix.append(self._get_asm('movq', self.ARGUMENT_REGISTERS[index], destination))
            else:
                prefix.append(self._get_asm('movq', f'{16 + 8 * (index - 6)}(%rbp)', '%r11'))
                prefix.append(self._get_asm('movq', '%r11', destination))
        suffix = [
            f'{self._end_label}:', '\tmovq\t%rbp, %rsp', '\tpopq\t%rbp', '\tretq',
            f'\t.size\t{symbol}, .-{symbol}',
        ]
        return prefix + self._asm + suffix


AsmGen.register(AsmGen_x64_Linux)


class AsmGen_arm64(AsmGen):
    ARGUMENT_REGISTERS = tuple(f'X{i}' for i in range(8))
    SYMBOL_PREFIX = ''
    GLOBAL_PAGE = False

    @staticmethod
    def _sub_imm(destination, source, immediate):
        assert 0 <= immediate < (1 << 24)
        result = []
        if immediate >= (1 << 12):
            result.append(('sub', destination, source, f'#{immediate >> 12}', 'lsl 12'))
            source, immediate = destination, immediate & 0xfff
        if immediate or not result:
            result.append(('sub', destination, source, f'#{immediate}'))
        return result

    @staticmethod
    def _add_imm(destination, source, immediate):
        assert 0 <= immediate < (1 << 24)
        result = []
        if immediate >= (1 << 12):
            result.append(('add', destination, source, f'#{immediate >> 12}', 'lsl 12'))
            source, immediate = destination, immediate & 0xfff
        if immediate or not result:
            result.append(('add', destination, source, f'#{immediate}'))
        return result

    @classmethod
    def _symbol(cls, name: str) -> str:
        return cls.SYMBOL_PREFIX + name[1:]

    @classmethod
    def _global_symbol(cls, name: str) -> str:
        return cls.SYMBOL_PREFIX + 'bx.' + name[1:]

    def _temp_address(self, temp: str, scratch='X15') -> str:
        offset = 8 * (self._slot(temp) + 1)
        if offset <= 256:
            return f'[FP, #-{offset}]'
        for instruction in self._sub_imm(scratch, 'FP', offset):
            self._emit(*instruction)
        return f'[{scratch}]'

    def _global_address(self, global_: str, scratch='X15') -> str:
        symbol = self._global_symbol(global_)
        if self.GLOBAL_PAGE:
            self._emit('adrp', scratch, f'{symbol}@PAGE')
            self._emit('add', scratch, scratch, f'{symbol}@PAGEOFF')
        else:
            self._emit('adrp', scratch, symbol)
            self._emit('add', scratch, scratch, f':lo12:{symbol}')
        return f'[{scratch}]'

    def _load(self, operand: str, register: str):
        address = (
            self._global_address(operand)
            if operand.startswith('@')
            else self._temp_address(operand)
        )
        self._emit('ldr', register, address)

    def _store(self, register: str, operand: str):
        address = (
            self._global_address(operand)
            if operand.startswith('@')
            else self._temp_address(operand)
        )
        self._emit('str', register, address)

    def _emit_const(self, constant, destination):
        if constant < 0:
            constant += 1 << 64
        self._emit('movz', 'X9', f'#{constant & 0xffff}')
        constant >>= 16
        shift = 16
        while constant:
            self._emit('movk', 'X9', f'#{constant & 0xffff}', f'lsl {shift}')
            constant >>= 16
            shift += 16
        self._store('X9', destination)

    def _emit_copy(self, source, destination):
        self._load(source, 'X9')
        self._store('X9', destination)

    def _emit_alu1(self, opcode, source, destination):
        self._load(source, 'X9')
        self._emit(opcode, 'X10', 'X9')
        self._store('X10', destination)

    def _emit_neg(self, s, d): self._emit_alu1('neg', s, d)
    def _emit_not(self, s, d): self._emit_alu1('mvn', s, d)

    def _emit_alu2(self, opcode, left, right, destination):
        self._load(left, 'X9')
        self._load(right, 'X10')
        self._emit(opcode, 'X11', 'X9', 'X10')
        self._store('X11', destination)

    def _emit_add(self, a, b, d): self._emit_alu2('add', a, b, d)
    def _emit_sub(self, a, b, d): self._emit_alu2('sub', a, b, d)
    def _emit_mul(self, a, b, d): self._emit_alu2('mul', a, b, d)
    def _emit_div(self, a, b, d): self._emit_alu2('sdiv', a, b, d)
    def _emit_and(self, a, b, d): self._emit_alu2('and', a, b, d)
    def _emit_or(self, a, b, d): self._emit_alu2('orr', a, b, d)
    def _emit_xor(self, a, b, d): self._emit_alu2('eor', a, b, d)
    def _emit_shl(self, a, b, d): self._emit_alu2('lsl', a, b, d)
    def _emit_shr(self, a, b, d): self._emit_alu2('asr', a, b, d)

    def _emit_mod(self, left, right, destination):
        self._load(left, 'X9')
        self._load(right, 'X10')
        self._emit('sdiv', 'X11', 'X9', 'X10')
        self._emit('msub', 'X11', 'X11', 'X10', 'X9')
        self._store('X11', destination)

    def _emit_jmp(self, label): self._emit('b', self._label(label))

    def _emit_jz(self, source, label):
        self._load(source, 'X9'); self._emit('cbz', 'X9', self._label(label))

    def _emit_jnz(self, source, label):
        self._load(source, 'X9'); self._emit('cbnz', 'X9', self._label(label))

    def _emit_cjmp(self, opcode, source, label):
        self._load(source, 'X9')
        self._emit('cmp', 'X9', '#0')
        self._emit(opcode, self._label(label))

    def _emit_jl(self, s, l): self._emit_cjmp('b.lt', s, l)
    def _emit_jnl(self, s, l): self._emit_cjmp('b.ge', s, l)
    def _emit_jle(self, s, l): self._emit_cjmp('b.le', s, l)
    def _emit_jnle(self, s, l): self._emit_cjmp('b.gt', s, l)

    def _emit_ret(self, *value):
        if value:
            self._load(value[0], 'X0')
        else:
            self._emit('mov', 'X0', '#0')
        self._emit('b', self._end_label)

    def _emit_call(self, procedure, nargs, *destination):
        if set(self._pending_params) != set(range(1, nargs + 1)):
            raise AsmGenError(f'{self.proc.name}: malformed parameters for call {procedure}')

        stack_count = max(0, nargs - len(self.ARGUMENT_REGISTERS))
        stack_size = 8 * (stack_count + (stack_count & 1))
        for instruction in self._sub_imm('SP', 'SP', stack_size) if stack_size else []:
            self._emit(*instruction)

        for index in range(9, nargs + 1):
            self._load(self._pending_params[index], 'X9')
            self._emit('str', 'X9', f'[SP, #{8 * (index - 9)}]')
        for index, register in enumerate(self.ARGUMENT_REGISTERS[:nargs], start=1):
            self._load(self._pending_params[index], register)

        self._emit('bl', self._symbol(procedure))
        for instruction in self._add_imm('SP', 'SP', stack_size) if stack_size else []:
            self._emit(*instruction)
        if destination:
            self._store('X0', destination[0])
        self._pending_params.clear()

    def _emit_print(self, source):
        self._pending_params[1] = source
        self._emit_call('@__bx_print_int', 1)

    @classmethod
    def _global_section(cls, globals_):
        if not globals_:
            return []
        result = ['\t.data']
        for name, value in globals_.items():
            symbol = cls._global_symbol(name)
            result.extend(('\t.p2align\t3', f'{symbol}:', f'\t.quad\t{value}'))
        return result

    def _procedure(self):
        nslots = len(self._temps) + (len(self._temps) & 1)
        frame_size = 8 * nslots
        symbol = self._symbol(self.proc.name)
        prefix = ['\t.text', f'\t.globl\t{symbol}', '\t.p2align\t2', f'{symbol}:',
                  '\tstp\tFP, LR, [SP, #-16]!', '\tmov\tFP, SP']
        prefix.extend(self._get_asm(*item) for item in self._sub_imm('SP', 'SP', frame_size))

        # Incoming arguments are copied into their stable frame slots before
        # the body makes any calls.
        saved_asm, self._asm = self._asm, []
        for index, argument in enumerate(self.proc.arguments):
            if index < len(self.ARGUMENT_REGISTERS):
                self._store(self.ARGUMENT_REGISTERS[index], argument)
            else:
                offset = 16 + 8 * (index - 8)
                self._emit('ldr', 'X9', f'[FP, #{offset}]')
                self._store('X9', argument)
        argument_moves = self._asm
        self._asm = saved_asm

        suffix = [f'{self._end_label}:', '\tmov\tSP, FP',
                  '\tldp\tFP, LR, [SP], #16', '\tret']
        return prefix + argument_moves + self._asm + suffix


class AsmGen_arm64_Darwin(AsmGen_arm64):
    NAME = 'arm64-apple-darwin'
    SYSTEM = 'Darwin'
    MACHINE = 'arm64'
    SYMBOL_PREFIX = '_'
    GLOBAL_PAGE = True


AsmGen.register(AsmGen_arm64_Darwin)


class AsmGen_arm64_Linux(AsmGen_arm64):
    NAME = 'arm64-linux'
    SYSTEM = 'Linux'
    MACHINE = 'aarch64'


AsmGen.register(AsmGen_arm64_Linux)
