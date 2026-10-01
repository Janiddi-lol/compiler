import sys
import ply.yacc

from .bxast import *
from .bxlexer import Lexer
from .bxerrors import Range, Reporter

# ========================================================
# BX Parser definition
"""
The lexer produces tokens one at a time. 
The parser groups tokens and previously reduced values 
according to grammar rules. Every reduction assigns the left-hand-side value to p[0].
# This class IS a PLY/yacc grammar specification -- and, in the same
# pass, the AST builder. The compiler-stages slide draws "parsing" and
# "syntactic analysis -> AST" as separate steps with a generic parse
# tree in between; this frontend skips that intermediate tree, since
# BX's grammar is simple enough that each grammar rule can just build
# its final AST node directly.
#
# PLY convention used throughout: every method named `p_xxx` is a
# GRAMMAR RULE, and its docstring is not documentation -- PLY parses
# it literally as BNF ("lhs : rhs1 rhs2 ..."). Those specific
# docstrings must never be edited or removed; that's why the
# explanations added below sit as SEPARATE standalone strings just
# above each method, never touching the real grammar docstring.
#
# `p` (PLY's YaccProduction object) is the other running theme: p[0]
# is the slot THIS rule produces (assign the AST node here); p[1],
# p[2], ... are the already-reduced values of the right-hand-side
# symbols, in left-to-right order.
"""

class Parser:
    UNIOP = {
        '-' : 'opposite'        ,
        '~' : 'bitwise-negation',
        '!' : 'boolean-not'     ,
    }

    BINOP = {
        '+'  : 'addition'                 ,
        '-'  : 'subtraction'              ,
        '*'  : 'multiplication'           ,
        '/'  : 'division'                 ,
        '%'  : 'modulus'                  ,
        '>>' : 'arithmetic-right-shift'   ,
        '<<' : 'left-shift'               ,
        '&'  : 'bitwise-and'              ,
        '|'  : 'bitwise-or'               ,
        '^'  : 'bitwise-xor'              ,
    }
    
    # PLY requires the full set of legal token names here -- reused
    # directly from Lexer.tokens so the lexer and parser never drift
    # apart from each other.
    tokens = Lexer.tokens
    
    # The grammar's root nonterminal: PLY tries to reduce the whole
    # input down to exactly one of these.
    start = 'program'

    precedence = (
        ('left'    , 'PIPE'                    ),
        ('left'    , 'HAT'                     ),
        ('left'    , 'AMP'                     ),
        ('left'    , 'LTLT', 'GTGT'            ),
        ('left'    , 'PLUS', 'DASH'            ),
        ('left'    , 'STAR', 'SLASH', 'PCENT'  ),
        ('right'   , 'UMINUS'                  ),
        ('right'   , 'UNEG'                    )
    )

    def __init__(self, reporter: Reporter):
        self.lexer = Lexer(reporter=reporter)
        self.parser = ply.yacc.yacc(module=self)
        self.reporter = reporter
    
    def parse(self, program:str):
        with self.reporter.checkpoint() as checkpoint:
            ast = self.parser.parse(
                program,
                lexer = self.lexer.lexer,
                tracking = True
            )
            
            return ast if checkpoint else None
    
    def _position(self, p) -> Range:
        n = len(p) - 1
        return Range(
            start = (p.linespan(1)[0], self.lexer.column_of_pos(p.lexspan(1)[0]) ),
            end   = (p.linespan(n)[1], self.lexer.column_of_pos(p.lexspan(n)[1]) ),
        )
    
    """
    Grammar: name -> IDENT
    Builds a Name node (an identifier's text + position) from a single
    IDENT token. p[1] is that token's value -- already a str, set by
    t_IDENT during lexing.
    """
    def p_name (self, p):
        """name : IDENT"""
        p[0] = Name(
            value=p[1],
            position= self._position(p)
        )
    

    """
    Grammar: expr -> name
    Wraps a bare variable reference (already a Name, from p_name above)
    into a VarExpression.
    """
    def p_expression_var(self, p):
        """ expr : name"""
        p[0] = VarExpression(
            name     = p[1],
            position = self._position(p)
        )
    
    
    """
    Grammar: expr -> NUMBER
    A literal integer constant. p[1] is already an int -- t_NUMBER
    converts it from its matched string during lexing.
    """
    def p_epxression_int(self, p):
        """expr : NUMBER""" # p[0] = expr 
        p[0] = IntExpression(
            value = p[1],
            position=self._position(p)
        ) 
    
    """
    Grammar: expr -> DASH expr   (unary '-', e.g. `-x`)
           | TILD expr   (unary '~', e.g. `~x`)
    `%prec UMINUS` / `%prec UNEG` override this rule's default
    precedence (which PLY would otherwise take from its rightmost
    terminal, DASH/TILD) with the synthetic UMINUS/UNEG levels
    declared in `precedence` above -- that's the mechanism that makes
    unary minus bind tighter than binary minus in e.g. `-x + y`.
    One operand -> `arguments` is a single-element list.
    """
    def p_expression_uniop(self, p):
        """expr : DASH expr %prec UMINUS
                | TILD expr %prec UNEG"""
        p[0] = OpAppExpression(
            operator  = self.UNIOP[p[1]],
            arguments = [p[2]],
            position  = self._position(p) 
        )
    
    """
    Grammar: expr -> expr <op> expr, for every binary operator at
    once. p[2] is whichever operator token actually matched -- used to
    look its name up in BINOP. Two operands -> `arguments` is a
    two-element list, [left, right].
    """
    def p_expression_binop(self, p):
        """expr : expr PLUS     expr
                | expr DASH     expr
                | expr STAR     expr
                | expr SLASH    expr
                | expr PCENT    expr
                | expr AMP      expr
                | expr PIPE     expr
                | expr HAT      expr
                | expr LTLT     expr
                | expr GTGT     expr"""
        p[0] = OpAppExpression(
            operator = self.BINOP[p[2]],
            arguments = [p[1], p[3]],
            position=self._position(p)
        )
    
    # Parenthesized expression
    """
    Grammar: expr -> LPAREN expr RPAREN
    Parenthesized grouping. p[0] = p[2] -- the parentheses themselves
    produce no AST node of their own; the inner expression is passed
    through unchanged (its own position, from when IT was built, is
    already correct).
    """
    def p_expression_group(self, p):
        """expr : LPAREN expr RPAREN"""
        p[0] = p[2] 
    
    """
    Grammar: stmt -> VAR name EQ expr COLON INT SEMICOLON
    `var <name> = <expr> : int;` -- a variable declaration with its
    initializer.
    """
    def p_stmnt_vardecl(self, p):
        """stmt : VAR name EQ expr COLON INT SEMICOLON"""
        
        p[0] = VarDeclStatement(
            name = p[2],
            init = p[4],
            position = self._position(p)
        )
    
    """
    Grammar: stmt -> name EQ expr SEMICOLON
    `<name> = <expr>;` -- reassigning an already-declared variable.
    """
    def p_stmt_assign(self,p):
        """stmt : name EQ expr SEMICOLON"""
        
        p[0] = AssignStatement(
            lhs = p[1],
            rhs = p[3],
            position=self._position(p)
        )    
    
    def p_stmt_print(self, p):
        """stmt : PRINT LPAREN expr RPAREN SEMICOLON"""
        p[0] = PrintStatement(
            value=p[3],
            position=self._position(p),
        )
    
    
    """
    Grammar: stmts -> (empty)
           | stmts stmt
    The list-building rule: a program body is zero or more statements.
    `len(p) == 1` means only p[0] exists (the empty alternative
    matched, nothing on the right-hand side) -> start a fresh empty
    list. Otherwise p[1] is the list built so far and p[2] is the
    newly parsed statement to append -- the standard left-recursive
    "build a list one element at a time" pattern.
    """
    def p_stmts(self, p):
        """ stmts : 
                  | stmts stmt"""
        if len(p) == 1:
            p[0] = []
        else: 
            p[0] = p[1]
            p[0].append(p[2])
        
    
    
    """
    Grammar: stmts -> stmts error SEMICOLON
    Error-recovery rule: PLY's special `error` token matches whatever
    broke parsing. On a syntax error, discard tokens up through the
    next SEMICOLON and resume with the statements already collected
    (p[1]) -- so one malformed statement doesn't abort parsing of the
    rest of the file. This is what makes the "batch multiple errors
    into one run" philosophy work at the PARSING level, the same way
    t_error makes it work at the lexing level.
    """
    def p_stmts_error_skip_to_semicolon(self, p):
        """stmts : stmts error SEMICOLON"""
        p[0] = p[1]
        
    """
    Grammar: program -> DEF MAIN LPAREN RPAREN LBRACE stmts RBRACE
    `def main() { <stmts> }` -- the whole program. p[6] is the stmts
    list; the fixed `def main() { ... }` wrapper contributes no AST
    node of its own -- this lab's BX fragment IS just its statement
    list (see Block = Program in bxast.py).
    """
    def p_program(self, p):
        """program : DEF MAIN LPAREN RPAREN LBRACE stmts RBRACE"""
        p[0] = p[6]
       
     
    """
    PLY's special error handler, called whenever no grammar rule
    matches the current input. `p` is the offending token -- or None
    if the error happened at end-of-input, when there's no token left
    to point a Range at, hence the separate branch below with no
    `position=` at all.
    """
    def p_error(self, p):
        if p:
            position = Range.of_position(
                p.lineno,
                self.lexer.column_of_pos(p.lexpos),
            )
            
            self.reporter(
                f'syntax error',
                position = position,
            )
        else:
            self.reporter('syntax error at the end of file')
            
            