# --------------------------------------------------------------------
from .bxast import *
from .bxscope import Scope
from .bxtac import *

# ====================================================================
# AST to TAC lowering -- THIS IS YOUR JOB
#
# Integer expressions are lowered bottom-up to a temporary. Boolean
# expressions are lowered top-down to a pair of true/false labels, which
# implements short-circuiting without first materializing a boolean value.

class TACGen:
    COMPARISON_JUMPS = {
        'cmp-equal'                : 'jz',
        'cmp-not-equal'            : 'jnz',
        'cmp-lower-than'           : 'jl',
        'cmp-lower-or-equal-than'  : 'jle',
        'cmp-greater-than'         : 'jnle',
        'cmp-greater-or-equal-than': 'jnl',
    }

    def __init__(self):
        self.tac: list[TAC] = []
        self.scope = Scope()
        self.loops: list[tuple[str, str]] = []
        self.temporary_counter = 0
        self.label_counter = 0

    def fresh_temporary(self) -> str:
        temporary = f'%{self.temporary_counter}'
        self.temporary_counter += 1
        return temporary

    def fresh_label(self) -> str:
        label = f'%.L{self.label_counter}'
        self.label_counter += 1
        return label

    def emit(self, opcode: str, arguments: list[str | int], result: str | None = None):
        self.tac.append(TAC(opcode, arguments, result))

    def emit_label(self, label: str):
        self.emit('label', [label])

    # ---- integer expressions: bottom-up maximal munch
    def integer_expression(self, expr: Expression) -> str:
        assert expr.type_ == Type.INT, expr

        match expr:
            case VarExpression(name):
                return self.scope[name.value]

            case IntExpression(value):
                result = self.fresh_temporary()
                self.emit('const', [value], result)
                return result

            case OpAppExpression(operator, arguments):
                operands = [self.integer_expression(argument) for argument in arguments]
                result = self.fresh_temporary()
                self.emit(OPCODES[operator], operands, result)
                return result

            case _:
                raise TypeError(f'unsupported integer expression: {expr!r}')

    # ---- boolean expressions: top-down maximal munch
    def boolean_expression(self, expr: Expression, true: str, false: str):
        assert expr.type_ == Type.BOOL, expr

        match expr:
            case BoolExpression(value):
                self.emit('jmp', [true if value else false])

            case VarExpression(name):
                self.emit('jnz', [self.scope[name.value], true])
                self.emit('jmp', [false])

            case OpAppExpression('boolean-not', [argument]):
                self.boolean_expression(argument, false, true)

            case OpAppExpression('boolean-and', [left, right]):
                next_ = self.fresh_label()
                self.boolean_expression(left, next_, false)
                self.emit_label(next_)
                self.boolean_expression(right, true, false)

            case OpAppExpression('boolean-or', [left, right]):
                next_ = self.fresh_label()
                self.boolean_expression(left, true, next_)
                self.emit_label(next_)
                self.boolean_expression(right, true, false)

            case OpAppExpression(operator, [left, right]) \
                    if operator in self.COMPARISON_JUMPS:
                left_temp = self.integer_expression(left)
                right_temp = self.integer_expression(right)
                difference = self.fresh_temporary()
                self.emit('sub', [left_temp, right_temp], difference)
                self.emit(self.COMPARISON_JUMPS[operator], [difference, true])
                self.emit('jmp', [false])

            case _:
                raise TypeError(f'unsupported boolean expression: {expr!r}')

    def materialize_boolean(self, expr: Expression) -> str:
        match expr:
            case VarExpression(name):
                return self.scope[name.value]

            case BoolExpression(value):
                result = self.fresh_temporary()
                self.emit('const', [int(value)], result)
                return result

        result = self.fresh_temporary()
        true = self.fresh_label()
        false = self.fresh_label()
        end = self.fresh_label()

        self.boolean_expression(expr, true, false)
        self.emit_label(true)
        self.emit('const', [1], result)
        self.emit('jmp', [end])
        self.emit_label(false)
        self.emit('const', [0], result)
        self.emit_label(end)
        return result

    def expression(self, expr: Expression) -> str:
        match expr.type_:
            case Type.INT:
                return self.integer_expression(expr)
            case Type.BOOL:
                return self.materialize_boolean(expr)
            case _:
                raise TypeError(f'expression has no type: {expr!r}')

    # ---- statements and blocks
    def statement(self, stmt: Statement):
        match stmt:
            case VarDeclStatement(name, init, _):
                # Lower before binding the name: the initializer may refer to
                # an outer variable that this declaration shadows.
                source = self.expression(init)
                destination = self.fresh_temporary()
                self.emit('copy', [source], destination)
                self.scope.push(name.value, destination)

            case AssignStatement(lhs, rhs):
                source = self.expression(rhs)
                self.emit('copy', [source], self.scope[lhs.value])

            case PrintStatement(value):
                self.emit('print', [self.integer_expression(value)])

            case BlockStatement(body):
                self.block(body)

            case IfStatement(condition, then, else_):
                then_label = self.fresh_label()
                end_label = self.fresh_label()

                if else_ is None:
                    self.boolean_expression(condition, then_label, end_label)
                    self.emit_label(then_label)
                    self.statement(then)
                    self.emit_label(end_label)
                else:
                    else_label = self.fresh_label()
                    self.boolean_expression(condition, then_label, else_label)
                    self.emit_label(then_label)
                    self.statement(then)
                    self.emit('jmp', [end_label])
                    self.emit_label(else_label)
                    self.statement(else_)
                    self.emit_label(end_label)

            case WhileStatement(condition, body):
                continue_label = self.fresh_label()
                body_label = self.fresh_label()
                break_label = self.fresh_label()

                self.emit_label(continue_label)
                self.boolean_expression(condition, body_label, break_label)
                self.emit_label(body_label)
                self.loops.append((continue_label, break_label))
                try:
                    self.statement(body)
                finally:
                    self.loops.pop()
                self.emit('jmp', [continue_label])
                self.emit_label(break_label)

            case BreakStatement():
                self.emit('jmp', [self.loops[-1][1]])

            case ContinueStatement():
                self.emit('jmp', [self.loops[-1][0]])

            case _:
                raise TypeError(f'unsupported statement: {stmt!r}')

    def block(self, block: Block):
        with self.scope.in_subscope():
            for stmt in block:
                self.statement(stmt)

    def lower(self, prgm: Program) -> list[TAC]:
        self.block(prgm)
        return self.tac

def lower(prgm: Program) -> list[TAC]:
    """Lower the (typed) AST `prgm` (a list of statements, see
    bxast.py) to the body of the `@main` TAC procedure.

    The result is a list of TAC instructions (see bxtac.py), e.g.:

        TAC('const', [42],         '%0')      # %0 = const 42;
        TAC('add',   ['%0', '%1'], '%2')      # %2 = add %0, %1;
        TAC('label', ['%.L1'])                # %.L1:
        TAC('jz',    ['%2', '%.L1'])          # jz %2, %.L1;
        TAC('print', ['%2'])                  # print %2;
    """

    return TACGen().lower(prgm)
