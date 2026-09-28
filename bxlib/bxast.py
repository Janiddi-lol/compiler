# --------------------------------------------------------------------
import dataclasses as dc
import enum

from typing import Optional as Opt

# ====================================================================
# Parse tree / Abstract Syntax Tree

# --------------------------------------------------------------------
@dc.dataclass
class Range:
    start: tuple[int, int]
    end: tuple[int, int]

    @staticmethod
    def of_position(line: int, column: int):
        return Range((line, column), (line, column+1))
    
# --------------------------------------------------------------------
class Type(enum.Enum):
    BOOL = 1
    INT  = 2

    def __str__(self):
        return self.name.lower()

# --------------------------------------------------------------------
@dc.dataclass
class AST:
    position: Opt[Range] = dc.field(kw_only = True, default = None)

# --------------------------------------------------------------------
@dc.dataclass
class Name(AST):
    value: str

# --------------------------------------------------------------------
@dc.dataclass
class Expression(AST):
    type_: Opt[Type] = dc.field(kw_only = True, default = None)

# --------------------------------------------------------------------
@dc.dataclass
class VarExpression(Expression):
    name: Name

# --------------------------------------------------------------------
@dc.dataclass
class BoolExpression(Expression):
    value: bool

# --------------------------------------------------------------------
@dc.dataclass
class IntExpression(Expression):
    value: int

# --------------------------------------------------------------------
@dc.dataclass
class OpAppExpression(Expression):
    operator: str
    arguments: list[Expression]

# --------------------------------------------------------------------
class Statement(AST):
    pass

# --------------------------------------------------------------------
Block = list[Statement]

# --------------------------------------------------------------------
@dc.dataclass
class VarDeclStatement(Statement):
    name: Name
    init: Expression    
    type_: Type

# --------------------------------------------------------------------
@dc.dataclass
class AssignStatement(Statement):
    lhs: Name
    rhs: Expression

# --------------------------------------------------------------------
@dc.dataclass
class PrintStatement(Statement):
    value: Expression
 
# --------------------------------------------------------------------
@dc.dataclass
class BlockStatement(Statement):
    body: list[Statement]

# --------------------------------------------------------------------
@dc.dataclass
class IfStatement(Statement):
    condition: Expression
    then: Statement
    else_: Opt[Statement] = None

# --------------------------------------------------------------------
@dc.dataclass
class WhileStatement(Statement):
    condition: Expression
    body: Statement

# --------------------------------------------------------------------
@dc.dataclass
class BreakStatement(Statement):
    pass

# --------------------------------------------------------------------
@dc.dataclass
class ContinueStatement(Statement):
    pass

# --------------------------------------------------------------------
Program = Block
