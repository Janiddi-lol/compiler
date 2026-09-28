#--------------------------------------------------------------------
from typing import Optional as Opt

from .bxast    import *
from .bxerrors import Reporter

# ====================================================================
# Syntax-level checker

class SynChecker:
    def __init__(self, reporter: Reporter):
        self.reporter = reporter
        self.vars     = set()

    def report(self, msg, position = None):
        self.reporter(msg, position)

    def check_local_free(self, name: Name):
        if name.value in self.vars:
            self.report(
                f"duplicate variable declaration for `{name.value}'",
                position = name.position,
            )
            return False
        return True

    def check_local_bound(
            self,
            name    : Name,
            position: Opt[Range] = None,
    ):
        if name.value not in self.vars:
            self.report(
                f"missing variable declaration for `{name.value}'",
                position = position,
            )
            return False
        return True

    def check_integer_constant_range(
            self,
            value   : int,
            position: Opt[Range] = None,
    ):
        if value not in range(0, 1 << 63):
            self.report(
                f'integer literal out of range: {value}',
                position = position
            )
            return False
        return True

    def for_expression(self, expr: Expression):
        match expr:
            case VarExpression(name):
                self.check_local_bound(name, position = name.position)

            case IntExpression(value):
                self.check_integer_constant_range(value, position = expr.position)

            case OpAppExpression(_, arguments):
                for argument in arguments:
                    self.for_expression(argument)

    def for_statement(self, stmt: Statement):
        match stmt:
            case VarDeclStatement(name, init):
                self.for_expression(init)
                if self.check_local_free(name):
                    self.vars.add(name.value)

            case AssignStatement(lhs, rhs):
                self.check_local_bound(lhs, position = lhs.position)
                self.for_expression(rhs)

            case PrintStatement(init):
                self.for_expression(init)

    def for_program(self, prgm: Program):
        for stmt in prgm:
            self.for_statement(stmt)

    def check(self, prgm: Program):
        self.reporter.checkpoint()
        self.for_program(prgm)

# --------------------------------------------------------------------
def check(prgm : Program, reporter : Reporter):
    with reporter.checkpoint() as checkpoint:
        SynChecker(reporter).check(prgm)
        return bool(checkpoint)
