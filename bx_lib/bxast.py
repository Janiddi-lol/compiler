#--------------------------------------------------------------------

from dataclasses import dataclass, field

# ====================================================================
# Parse tree / Abstract Syntax Tree

@dataclass
class Range:
    start: tuple[int, int]
    end: tuple[int, int]
    
    @staticmethod
    def of_position(line: int, column: int) -> 'Range':
        return Range((line, column), (line, column+1))

# --------------------------------------------------------------------
@dataclass
class AST:
    position: None | Range = field(kw_only=True, default=None)

# --------------------------------------------------------------------
@dataclass
class Name(AST):
    value: str

# --------------------------------------------------------------------
@dataclass
class Expression(AST):
    pass

# --------------------------------------------------------------------
@dataclass
class VarExpression(Expression):
    name: Name
    
    
# --------------------------------------------------------------------
@dataclass
class IntExpression(Expression):
    value: int
    
# --------------------------------------------------------------------
@dataclass
class OpAppExpression(Expression):
    operator: str
    arguments: list[Expression]
    
# --------------------------------------------------------------------
class Statement(AST):
    pass

# --------------------------------------------------------------------
@dataclass
class VarDeclStatement(Statement):
    name: Name
    init: Expression

# --------------------------------------------------------------------
@dataclass
class AssignStatement(Statement):
    lhs: Name
    rhs: Expression

@dataclass
class PrintStatement(Statement):
    value: Expression

# --------------------------------------------------------------------
Block   = list[Statement]
Program = Block
    