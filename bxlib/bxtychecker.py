# --------------------------------------------------------------------
import contextlib as cl

from typing import Optional as Opt

from .bxast    import *
from .bxerrors import Reporter
from .bxscope  import Scope

# ====================================================================
# Type checker
#
# Checks that variables are declared before use (and only once per
# scope), that `break' / `continue' appear inside loops, and that
# every expression is well typed. Sets the `type_' attribute of every
# expression node on the way.

class TypeChecker:
    B = Type.BOOL
    I = Type.INT

    # operator name -> (argument types, result type)
    SIGS = {
        'opposite'                 : ([I   ], I),
        'bitwise-negation'         : ([I   ], I),
        'boolean-not'              : ([B   ], B),
        'addition'                 : ([I, I], I),
        'subtraction'              : ([I, I], I),
        'multiplication'           : ([I, I], I),
        'division'                 : ([I, I], I),
        'modulus'                  : ([I, I], I),
        'left-shift'               : ([I, I], I),
        'arithmetic-right-shift'   : ([I, I], I),
        'bitwise-and'              : ([I, I], I),
        'bitwise-or'               : ([I, I], I),
        'bitwise-xor'              : ([I, I], I),
        'boolean-and'              : ([B, B], B),
        'boolean-or'               : ([B, B], B),
        'cmp-equal'                : ([I, I], B),
        'cmp-not-equal'            : ([I, I], B),
        'cmp-lower-than'           : ([I, I], B),
        'cmp-lower-or-equal-than'  : ([I, I], B),
        'cmp-greater-than'         : ([I, I], B),
        'cmp-greater-or-equal-than': ([I, I], B),
    }

    def __init__(self, reporter: Reporter):
        self.scope    = Scope()
        self.loops    = 0
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

    # ---- variables
    def check_local_free(self, name: Name):
        if self.scope.islocal(name.value):
            self.report(
                f"duplicate variable declaration for `{name.value}'",
                position = name.position,
            )
            return False
        return True

    def check_local_bound(self, name: Name) -> Opt[Type]:
        if name.value not in self.scope:
            self.report(
                f"missing variable declaration for `{name.value}'",
                position = name.position,
            )
            return None
        return self.scope[name.value]

    def check_integer_constant_range(self, value: int, position: Opt[Range] = None):
        if value not in range(0, 1 << 63):
            self.report(
                f'integer literal out of range: {value}',
                position = position,
            )
            return False
        return True

    # ---- expressions: compute the type, check it against `etype'
    def for_expression(self, expr: Expression, etype: Opt[Type] = None):
        type_ = None

        match expr:
            case VarExpression(name):
                type_ = self.check_local_bound(name)

            case BoolExpression(_):
                type_ = Type.BOOL

            case IntExpression(value):
                self.check_integer_constant_range(value, position = expr.position)
                type_ = Type.INT

            case OpAppExpression(operator, arguments):
                atypes, type_ = self.SIGS[operator]
                for atype, argument in zip(atypes, arguments):
                    self.for_expression(argument, etype = atype)

            case _:
                assert False, expr

        if type_ is not None and etype is not None and type_ != etype:
            self.report(
                f"invalid type: expected `{etype}', got `{type_}'",
                position = expr.position,
            )

        expr.type_ = type_

    # ---- statements
    def for_statement(self, stmt: Statement):
        match stmt:
            case VarDeclStatement(name, init, type_):
                self.for_expression(init, etype = type_)
                if self.check_local_free(name):
                    self.scope.push(name.value, type_)

            case AssignStatement(lhs, rhs):
                lhstype = self.check_local_bound(lhs)
                self.for_expression(rhs, etype = lhstype)

            case PrintStatement(value):
                self.for_expression(value, etype = Type.INT)

            case BlockStatement(body):
                self.for_block(body)

            case IfStatement(condition, then, else_):
                self.for_expression(condition, etype = Type.BOOL)
                self.for_statement(then)
                if else_ is not None:
                    self.for_statement(else_)

            case WhileStatement(condition, body):
                self.for_expression(condition, etype = Type.BOOL)
                with self.in_loop():
                    self.for_statement(body)

            case BreakStatement() | ContinueStatement():
                if self.loops == 0:
                    self.report(
                        'break/continue statement outside of a loop',
                        position = stmt.position,
                    )

            case _:
                assert False, stmt

    def for_block(self, block: Block):
        with self.scope.in_subscope():
            for stmt in block:
                self.for_statement(stmt)

    def for_program(self, prgm: Program):
        self.for_block(prgm)

# --------------------------------------------------------------------
def check(prgm: Program, reporter: Reporter) -> bool:
    with reporter.checkpoint() as checkpoint:
        TypeChecker(reporter).for_program(prgm)
        return bool(checkpoint)
