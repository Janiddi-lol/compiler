# --------------------------------------------------------------------
import sys
import ply.yacc

from .bxast    import *
from .bxlexer  import Lexer
from .bxerrors import Range, Reporter

# ====================================================================
# BX parser definition

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

    tokens = Lexer.tokens
    
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
        self.lexer    = Lexer(reporter = reporter)
        self.parser   = ply.yacc.yacc(module = self)
        self.reporter = reporter

    def parse(self, program: str):
        with self.reporter.checkpoint() as checkpoint:
            ast = self.parser.parse(
                program,
                lexer    = self.lexer.lexer,
                tracking = True,
            )

            return ast if checkpoint else None

    def _position(self, p) -> Range:
        n = len(p) - 1
        return Range(
            start = (p.linespan(1)[0], self.lexer.column_of_pos(p.lexspan(1)[0])    ),
            end   = (p.linespan(n)[1], self.lexer.column_of_pos(p.lexspan(n)[1])    ),
        )

    def p_name(self, p):
        """name : IDENT"""
        p[0] = Name(
            value = p[1],
            position = self._position(p)
        )

    def p_expression_var(self, p):
        """expr : name"""
        p[0] = VarExpression(
            name     = p[1],
            position = self._position(p)
        )

    def p_expression_int(self, p):
        """expr : NUMBER"""
        p[0] = IntExpression(
            value    = p[1],
            position = self._position(p),
        )
    
    def p_expression_uniop(self, p):
        """expr : DASH expr %prec UMINUS
                | TILD expr %prec UNEG"""
        p[0] = OpAppExpression(
            operator  = self.UNIOP[p[1]],
            arguments = [p[2]],
            position  = self._position(p),
        )

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
            operator  = self.BINOP[p[2]],
            arguments = [p[1], p[3]],
            position  = self._position(p),
        )

    def p_expression_group(self, p):
        """expr : LPAREN expr RPAREN"""
        p[0] = p[2]

    def p_stmt_vardecl(self, p):
        """stmt : VAR name EQ expr COLON INT SEMICOLON"""
        p[0] = VarDeclStatement(
            name     = p[2],
            init     = p[4],
            position = self._position(p),
        )

    def p_stmt_assign(self, p):
        """stmt : name EQ expr SEMICOLON"""
        p[0] = AssignStatement(
            lhs      = p[1],
            rhs      = p[3],
            position = self._position(p),
        )

    def p_stmt_print(self, p):
        """stmt : PRINT LPAREN expr RPAREN SEMICOLON"""
        p[0] = PrintStatement(
            value    = p[3],
            position = self._position(p),
        )

    def p_stmts(self, p):
        """stmts :
                 | stmts stmt"""
        if len(p) == 1:
            p[0] = []
        else:
            p[0] = p[1]
            p[0].append(p[2])

    def p_stmts_error_skip_to_semicolon(self, p):
        """stmts : stmts error SEMICOLON"""
        p[0] = p[1]

    def p_program(self, p):
        """program : DEF MAIN LPAREN RPAREN LBRACE stmts RBRACE"""
        p[0] = p[6]

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
            #self.parser.errok()
        else:
            self.reporter('syntax error at end of file')
