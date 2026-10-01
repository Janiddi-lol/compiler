from .bxast import *
from .bxerrors import Reporter

# ========================================================
# Syntax-level checker

# Why this pass exists at all: BNF grammars are context-free, so
# bxparser.py's grammar structurally cannot express "this variable was
# declared earlier" or "no variable is declared twice" -- those require
# carrying state (which names have been seen so far) across the whole
# tree, which a context-free grammar has no mechanism for. Parsing
# produces a tree that's syntactically valid but not yet known to be
# semantically sane; this pass walks that tree afterward and adds
# exactly the checks a CFG can't.

class SynChecker:
    def __init__(self, reporter: Reporter):
        """
        `self.vars` is a flat set of every variable name declared so
        far. One flat namespace is enough because this BX fragment
        (bxparser.py's grammar) has a single `main`, no nested blocks
        or functions yet -- once those exist, this would need to
        become a stack of scopes instead of one set.
        """
        self.reporter = reporter
        self.vars = set()
    
    # Reporting helper    
    def report(self, msg, position = None):
        """
        Thin forwarding wrapper around `self.reporter(...)`. Exists so
        every check_* method below calls `self.report(...)` uniformly,
        rather than reaching into `self.reporter` directly everywhere.
        """
        self.reporter(msg, position)
        
    def check_local_free(self, name: Name):
        """
        Check the declarion is new.
        "Is this name NOT already declared?" -- used right before a
        `var` declaration is allowed to register a new name, to catch
        double-declaration (regression/redeclared.bx). Returns a bool
        so the caller can decide whether to actually add the name to
        `self.vars`; it does not add anything itself.
        """
        if name.value in self.vars:
            self.report(
                f"duplicate variable declaration for `{name.value}`",
                position=name.position
            )
            return False
        return True
    
    # Check that used name exists
    def check_local_bound(
        self,
        name: Name,
        position: Range | None = None,
    ):
        """
        "Is this name ALREADY declared?" -- the opposite check from
        check_local_free, used whenever a variable is REFERENCED
        (read in an expression, or assigned to) rather than declared,
        to catch use-before-declaration
        (regression/undeclaredvar.bx, regression/missinginit.bx).
        `position` is a separate parameter rather than always using
        `name.position`, so a caller can point at something else (e.g.
        the whole containing expression) if that reads better.
        """
        if name.value not in self.vars:
            self.report(
                f"missing variable declaration for `{name.value}`",
                position=position
            )
            return False
        return True
    
    # Check integer-literal range
    def check_integer_constant_range(
        self,
        value : int, 
        position : Range | None = None,
    ):
        """
        BX integer literals must fit in 63 bits, unsigned: `0 <= value
        < 2**63` (regression/bigliteral.bx). Negative numbers are never
        rejected here -- a literal like `-5` isn't a single negative
        IntExpression, it's unary `-` applied to the positive literal
        `5` (see bxparser.py's p_expression_uniop), so this range check
        only ever sees non-negative values in the first place.
        """
        if value not in range(0,1 << 63):
            self.report(
                f"integer literal is out of range: {value}",
                position=position
            )
            return False
        return True

    def check_expression(self, expression: Expression):
        """
        Structural recursion over Expression, dispatched with
        match/case on the concrete dataclass shape -- this works with
        no visitor-pattern boilerplate specifically because bxast.py's
        nodes are plain @dataclass classes, so `case
        VarExpression(name):` destructures the node's fields directly.
        VarExpression -> must already be declared.
        IntExpression -> must be in range.
        OpAppExpression -> no check of its own; just recurse into
        every argument (covers both unary and binary operators, since
        `arguments` is a list either way).
        """
        match expression:
            case VarExpression(name=name):
                self.check_local_bound(
                    name, 
                    position=name.position
                )
            
            case IntExpression(value=value):
                self.check_integer_constant_range(
                    value, 
                    position=expression.position
                    )
            
            case OpAppExpression(_, arguments):
                for argument in arguments:
                    self.check_expression(argument)
            
            case _:
                raise TypeError(
                    f"unsupported expression: {type(expression).__name__}"
                )
                
    def check_statement(self, statement: Statement) -> None:
        """
        Same structural-recursion idea as for_expression, one level up.
        VarDeclStatement: note the ORDER -- `init` is checked BEFORE
        `name` is added to `self.vars`. That's what makes a circular
        initializer like `var x = x : int;` correctly fail
        (regression/circularinit.bx): while `init` (the right-hand
        `x`) is being checked, the left-hand `x` has not been
        registered yet, so it's still "not declared."
        AssignStatement: the target (`lhs`) must already be declared;
        the value (`rhs`) is checked recursively like any expression.
        PrintStatement: just recurse into the printed expression.
        """
        match statement:
            case VarDeclStatement(name, init):
                self.check_expression(init)
                if self.check_local_free(name):
                    self.vars.add(name.value)
            
            case AssignStatement(lhs, rhs):
                self.check_local_bound(lhs, lhs.position)
                self.check_expression(rhs)
            
            case PrintStatement(value=value):
                self.check_expression(value)
            
            case _:
                raise TypeError(
                    f"unsupported statement: {type(statement).__name__}"
                )
                
    def check_program(self, prgm: Program):
        """
        Walks every top-level statement in order. Because `self.vars`
        is mutated in place as VarDeclStatements are seen (see
        for_statement above), this single left-to-right pass is what
        enforces "must declare before use" -- a variable referenced
        before its `var` statement simply hasn't been added to
        `self.vars` yet when that earlier statement is checked.
        """
        for stmt in prgm:
            self.check_statement(stmt)

def check(prgm: Program, reporter : Reporter):
    with reporter.checkpoint() as checkpoint:
        SynChecker(reporter).check_program(prgm)
        return bool(checkpoint)
    
    