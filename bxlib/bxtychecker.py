# --------------------------------------------------------------------
import contextlib as cl

from dataclasses import dataclass
from typing import Optional as Opt

from .bxast import *
from .bxerrors import Reporter
from .bxscope import Scope


@dataclass(frozen=True)
class ProcType:
    arguments: tuple[Type, ...]
    result: Type


class TypeChecker:
    B = Type.BOOL
    I = Type.INT

    SIGS = {
        'opposite': ([I], I),
        'bitwise-negation': ([I], I),
        'boolean-not': ([B], B),
        'addition': ([I, I], I),
        'subtraction': ([I, I], I),
        'multiplication': ([I, I], I),
        'division': ([I, I], I),
        'modulus': ([I, I], I),
        'left-shift': ([I, I], I),
        'arithmetic-right-shift': ([I, I], I),
        'bitwise-and': ([I, I], I),
        'bitwise-or': ([I, I], I),
        'bitwise-xor': ([I, I], I),
        'boolean-and': ([B, B], B),
        'boolean-or': ([B, B], B),
        'cmp-equal': ([I, I], B),
        'cmp-not-equal': ([I, I], B),
        'cmp-lower-than': ([I, I], B),
        'cmp-lower-or-equal-than': ([I, I], B),
        'cmp-greater-than': ([I, I], B),
        'cmp-greater-or-equal-than': ([I, I], B),
    }

    def __init__(self, reporter: Reporter):
        self.scope = Scope()
        self.procedures: dict[str, ProcType] = {}
        self.loops = 0
        self.return_type = Type.VOID
        self.reporter = reporter

    def report(self, msg: str, position: Opt[Range] = None):
        self.reporter(msg, position)

    @cl.contextmanager
    def in_loop(self):
        self.loops += 1
        try:
            yield self
        finally:
            self.loops -= 1

    def check_local_free(self, name: Name) -> bool:
        if self.scope.islocal(name.value):
            self.report(
                f"duplicate variable declaration for `{name.value}'",
                position=name.position,
            )
            return False
        return True

    def check_local_bound(self, name: Name) -> Opt[Type]:
        if name.value not in self.scope:
            self.report(
                f"missing variable declaration for `{name.value}'",
                position=name.position,
            )
            return None
        return self.scope[name.value]

    def check_integer_constant_range(self, value: int, position: Opt[Range] = None):
        if value not in range(0, 1 << 63):
            self.report(f'integer literal out of range: {value}', position=position)
            return False
        return True

    @staticmethod
    def parameters(decl: ProcDecl):
        for names, type_ in decl.arguments:
            for name in names:
                yield name, type_

    # ---- expressions
    def for_expression(self, expr: Expression, etype: Opt[Type] = None) -> Opt[Type]:
        type_: Opt[Type] = None

        match expr:
            case VarExpression(name):
                type_ = self.check_local_bound(name)

            case BoolExpression(_):
                type_ = Type.BOOL

            case IntExpression(value):
                self.check_integer_constant_range(value, position=expr.position)
                type_ = Type.INT

            case OpAppExpression(operator, arguments):
                atypes, type_ = self.SIGS[operator]
                for atype, argument in zip(atypes, arguments):
                    self.for_expression(argument, etype=atype)

            case PrintExpression(argument):
                argument_type = self.for_expression(argument)
                if argument_type not in (None, Type.INT, Type.BOOL):
                    self.report(
                        f"invalid type: expected `int' or `bool', got `{argument_type}'",
                        position=argument.position,
                    )
                type_ = Type.VOID

            case CallExpression(proc, arguments):
                signature = self.procedures.get(proc.value)
                if signature is None:
                    self.report(
                        f"missing procedure declaration for `{proc.value}'",
                        position=proc.position,
                    )
                    for argument in arguments:
                        self.for_expression(argument)
                else:
                    if len(arguments) != len(signature.arguments):
                        self.report(
                            f"invalid number of arguments in call to `{proc.value}'",
                            position=expr.position,
                        )
                    for index, argument in enumerate(arguments):
                        expected = (
                            signature.arguments[index]
                            if index < len(signature.arguments)
                            else None
                        )
                        self.for_expression(argument, etype=expected)
                    type_ = signature.result

            case _:
                raise TypeError(f'unsupported expression: {type(expr).__name__}')

        if type_ is not None and etype is not None and type_ != etype:
            self.report(
                f"invalid type: expected `{etype}', got `{type_}'",
                position=expr.position,
            )
        expr.type_ = type_
        return type_

    # ---- statements
    def for_statement(self, stmt: Statement):
        match stmt:
            case VarDeclStatement(name, init, type_):
                self.for_expression(init, etype=type_)
                if self.check_local_free(name):
                    self.scope.push(name.value, type_)

            case AssignStatement(lhs, rhs):
                self.for_expression(rhs, etype=self.check_local_bound(lhs))

            case ExprStatement(expression):
                self.for_expression(expression)

            case ReturnStatement(expr):
                if expr is None:
                    if self.return_type != Type.VOID:
                        self.report(
                            f"missing return value of type `{self.return_type}'",
                            position=stmt.position,
                        )
                elif self.return_type == Type.VOID:
                    self.for_expression(expr)
                    self.report(
                        'a subroutine cannot return a value',
                        position=stmt.position,
                    )
                else:
                    self.for_expression(expr, etype=self.return_type)

            case BlockStatement(body):
                self.for_block(body)

            case IfStatement(condition, then, else_):
                self.for_expression(condition, etype=Type.BOOL)
                self.for_statement(then)
                if else_ is not None:
                    self.for_statement(else_)

            case WhileStatement(condition, body):
                self.for_expression(condition, etype=Type.BOOL)
                with self.in_loop():
                    self.for_statement(body)

            case BreakStatement() | ContinueStatement():
                if self.loops == 0:
                    self.report(
                        'break/continue statement outside of a loop',
                        position=stmt.position,
                    )

            case _:
                raise TypeError(f'unsupported statement: {type(stmt).__name__}')

    def for_block(self, block: Block):
        with self.scope.in_subscope():
            for stmt in block:
                self.for_statement(stmt)

    @staticmethod
    def always_returns(stmt: Statement) -> bool:
        match stmt:
            case ReturnStatement():
                return True
            case BlockStatement(body):
                return any(TypeChecker.always_returns(item) for item in body)
            case IfStatement(_, then, else_) if else_ is not None:
                return (
                    TypeChecker.always_returns(then)
                    and TypeChecker.always_returns(else_)
                )
            case _:
                return False

    # ---- top-level declarations: pass 1 collects names, pass 2 checks bodies
    def collect_topdecl(self, decl: TopDecl):
        match decl:
            case GlobVarDecl(name, _, type_):
                if self.check_local_free(name):
                    self.scope.push(name.value, type_)

            case ProcDecl(name, _, rettype, _):
                if name.value.startswith('__bx_'):
                    self.report(
                        "the `__bx_' prefix is reserved for the runtime",
                        position=name.position,
                    )
                if name.value in self.procedures:
                    self.report(
                        f"duplicate procedure declaration for `{name.value}'",
                        position=name.position,
                    )
                else:
                    self.procedures[name.value] = ProcType(
                        tuple(type_ for _, type_ in self.parameters(decl)),
                        rettype or Type.VOID,
                    )

            case _:
                raise TypeError(f'unsupported declaration: {type(decl).__name__}')

    def check_topdecl(self, decl: TopDecl):
        match decl:
            case GlobVarDecl(_, init, type_):
                if not isinstance(init, (BoolExpression, IntExpression)):
                    self.report(
                        'global variable initializer must be a literal',
                        position=init.position,
                    )
                self.for_expression(init, etype=type_)

            case ProcDecl(name, _, rettype, BlockStatement(body)):
                previous_return_type = self.return_type
                self.return_type = rettype or Type.VOID
                with self.scope.in_subscope():
                    for parameter, type_ in self.parameters(decl):
                        if self.check_local_free(parameter):
                            self.scope.push(parameter.value, type_)
                    # Deliberately do not open another scope here: parameters
                    # and declarations in the procedure's outer body share it.
                    for stmt in body:
                        self.for_statement(stmt)
                self.return_type = previous_return_type

                if rettype is not None and not self.always_returns(decl.body):
                    self.report(
                        f"function `{name.value}' may not return a value",
                        position=decl.body.position,
                    )

            case ProcDecl():
                raise TypeError('procedure body is not a block')

            case _:
                raise TypeError(f'unsupported declaration: {type(decl).__name__}')

    def for_program(self, prgm: Program):
        for decl in prgm:
            self.collect_topdecl(decl)

        main = self.procedures.get('main')
        if main is None:
            self.report("this program has no `main' procedure")
        elif main != ProcType((), Type.VOID):
            main_decl = next(
                decl for decl in prgm
                if isinstance(decl, ProcDecl) and decl.name.value == 'main'
            )
            self.report(
                '`main\' must be a parameterless subroutine',
                position=main_decl.name.position,
            )

        for decl in prgm:
            self.check_topdecl(decl)


def check(prgm: Program, reporter: Reporter) -> bool:
    with reporter.checkpoint() as checkpoint:
        TypeChecker(reporter).for_program(prgm)
        return bool(checkpoint)
