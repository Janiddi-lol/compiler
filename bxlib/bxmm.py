# --------------------------------------------------------------------
import contextlib as cl

from typing import Optional as Opt

from .bxast import *
from .bxscope import Scope
from .bxtac import *


class MM:
    def __init__(self):
        self._counter = -1
        self._tac: list[TAC] = []
        self._scope = Scope()
        self._loops: list[tuple[str, str]] = []
        self._unit: TACUnit = []

    @staticmethod
    def mm(prgm: Program) -> TACUnit:
        mm = MM()
        mm.for_program(prgm)
        return mm._unit

    def fresh_temporary(self) -> str:
        self._counter += 1
        return f'%{self._counter}'

    def fresh_label(self) -> str:
        self._counter += 1
        return f'%.L{self._counter}'

    def push(
        self,
        opcode: str,
        *arguments: str | int,
        result: Opt[str] = None,
    ):
        self._tac.append(TAC(opcode, list(arguments), result))

    def push_label(self, label: str):
        self.push('label', label)

    @cl.contextmanager
    def in_loop(self, labels: tuple[str, str]):
        self._loops.append(labels)
        try:
            yield
        finally:
            self._loops.pop()

    @staticmethod
    def parameters(decl: ProcDecl):
        for names, _ in decl.arguments:
            yield from names

    # ---- programs and procedures
    def for_program(self, prgm: Program):
        # Globals are available in every procedure, irrespective of source order.
        for decl in prgm:
            if isinstance(decl, GlobVarDecl):
                self._scope.push(decl.name.value, f'@{decl.name.value}')
                value = int(decl.init.value)
                self._unit.append(TACVar(f'@{decl.name.value}', value))

        for decl in prgm:
            if not isinstance(decl, ProcDecl):
                continue

            self._counter = -1
            self._tac = []
            arguments = [f'%{name.value}' for name in self.parameters(decl)]

            with self._scope.in_subscope():
                for name, operand in zip(self.parameters(decl), arguments):
                    self._scope.push(name.value, operand)

                # The procedure body and its parameters share one scope.
                assert isinstance(decl.body, BlockStatement)
                for statement in decl.body.body:
                    self.for_statement(statement)
                self.push('ret')

            self._unit.append(TACProc(f'@{decl.name.value}', arguments, self._tac))

    def for_block(self, block: Block):
        with self._scope.in_subscope():
            for stmt in block:
                self.for_statement(stmt)

    # ---- statements
    def for_statement(self, stmt: Statement):
        match stmt:
            case VarDeclStatement(name, init, _):
                # Evaluate before introducing the new binding, so a shadowing
                # initializer sees the enclosing variable.
                temp = self.for_expression(init)
                assert temp is not None
                self._scope.push(name.value, self.fresh_temporary())
                self.push('copy', temp, result=self._scope[name.value])

            case AssignStatement(lhs, rhs):
                temp = self.for_expression(rhs)
                assert temp is not None
                self.push('copy', temp, result=self._scope[lhs.value])

            case ExprStatement(expression):
                self.for_expression(expression)

            case ReturnStatement(expr):
                if expr is None:
                    self.push('ret')
                else:
                    value = self.for_expression(expr)
                    assert value is not None
                    self.push('ret', value)

            case BlockStatement(body):
                self.for_block(body)

            case IfStatement(condition, then, else_):
                tlabel = self.fresh_label()
                flabel = self.fresh_label()
                olabel = self.fresh_label()

                self.for_bexpression(condition, tlabel, flabel)
                self.push_label(tlabel)
                self.for_statement(then)
                self.push('jmp', olabel)
                self.push_label(flabel)
                if else_ is not None:
                    self.for_statement(else_)
                self.push_label(olabel)

            case WhileStatement(condition, body):
                clabel = self.fresh_label()
                blabel = self.fresh_label()
                olabel = self.fresh_label()

                with self.in_loop((clabel, olabel)):
                    self.push_label(clabel)
                    self.for_bexpression(condition, blabel, olabel)
                    self.push_label(blabel)
                    self.for_statement(body)
                    self.push('jmp', clabel)
                    self.push_label(olabel)

            case ContinueStatement():
                self.push('jmp', self._loops[-1][0])

            case BreakStatement():
                self.push('jmp', self._loops[-1][1])

            case _:
                raise TypeError(f'unsupported statement: {type(stmt).__name__}')

    def for_call(self, proc: Name, arguments: list[Expression], type_: Type) -> Opt[str]:
        # Evaluate every argument before emitting any param instruction. This
        # prevents a nested call from consuming the outer call's parameters.
        values = [self.for_expression(argument) for argument in arguments]
        assert all(value is not None for value in values)
        for index, value in enumerate(values, start=1):
            assert value is not None
            self.push('param', index, value)

        target = None if type_ == Type.VOID else self.fresh_temporary()
        self.push('call', f'@{proc.value}', len(values), result=target)
        return target

    # ---- expressions as values
    def for_expression(self, expr: Expression) -> Opt[str]:
        if expr.type_ == Type.BOOL:
            target = self.fresh_temporary()
            tlabel = self.fresh_label()
            flabel = self.fresh_label()

            self.push('const', 0, result=target)
            self.for_bexpression(expr, tlabel, flabel)
            self.push_label(tlabel)
            self.push('const', 1, result=target)
            self.push_label(flabel)
            return target

        match expr:
            case VarExpression(name):
                return self._scope[name.value]

            case IntExpression(value):
                target = self.fresh_temporary()
                self.push('const', value, result=target)
                return target

            case OpAppExpression(operator, arguments):
                values = [self.for_expression(argument) for argument in arguments]
                assert all(value is not None for value in values)
                target = self.fresh_temporary()
                self.push(OPCODES[operator], *values, result=target)
                return target

            case CallExpression(proc, arguments):
                assert expr.type_ is not None
                return self.for_call(proc, arguments, expr.type_)

            case PrintExpression(argument):
                value = self.for_expression(argument)
                assert value is not None and argument.type_ is not None
                runtime = (
                    '@__bx_print_bool'
                    if argument.type_ == Type.BOOL
                    else '@__bx_print_int'
                )
                self.push('param', 1, value)
                self.push('call', runtime, 1)
                return None

            case _:
                raise TypeError(f'unsupported expression: {type(expr).__name__}')

    # ---- boolean expressions as jumps
    CMP_JMP = {
        'cmp-equal': 'jz',
        'cmp-not-equal': 'jnz',
        'cmp-lower-than': 'jl',
        'cmp-lower-or-equal-than': 'jle',
        'cmp-greater-than': 'jnle',
        'cmp-greater-or-equal-than': 'jnl',
    }

    def for_bexpression(self, expr: Expression, tlabel: str, flabel: str):
        assert expr.type_ == Type.BOOL, expr

        match expr:
            case VarExpression(name):
                self.push('jz', self._scope[name.value], flabel)
                self.push('jmp', tlabel)

            case BoolExpression(True):
                self.push('jmp', tlabel)

            case BoolExpression(False):
                self.push('jmp', flabel)

            case CallExpression(proc, arguments):
                value = self.for_call(proc, arguments, Type.BOOL)
                assert value is not None
                self.push('jz', value, flabel)
                self.push('jmp', tlabel)

            case OpAppExpression(operator, [e1, e2]) if operator in self.CMP_JMP:
                t1 = self.for_expression(e1)
                t2 = self.for_expression(e2)
                assert t1 is not None and t2 is not None
                temp = self.fresh_temporary()
                self.push('sub', t1, t2, result=temp)
                self.push(self.CMP_JMP[operator], temp, tlabel)
                self.push('jmp', flabel)

            case OpAppExpression('boolean-and', [e1, e2]):
                olabel = self.fresh_label()
                self.for_bexpression(e1, olabel, flabel)
                self.push_label(olabel)
                self.for_bexpression(e2, tlabel, flabel)

            case OpAppExpression('boolean-or', [e1, e2]):
                olabel = self.fresh_label()
                self.for_bexpression(e1, tlabel, olabel)
                self.push_label(olabel)
                self.for_bexpression(e2, tlabel, flabel)

            case OpAppExpression('boolean-not', [argument]):
                self.for_bexpression(argument, flabel, tlabel)

            case _:
                raise TypeError(f'unsupported boolean expression: {expr!r}')


def lower(prgm: Program) -> TACUnit:
    return MM.mm(prgm)
