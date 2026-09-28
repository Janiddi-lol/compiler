# --------------------------------------------------------------------
import bisect
import ply.lex
import re

from .bxerrors import Range, Reporter

# ====================================================================
# BX lexer definition

class Lexer:
    keywords = {
        x: x.upper() for x in (
            'bool'    ,
            'break'   ,
            'continue',
            'def'     ,
            'else'    ,
            'false'   ,
            'if'      ,
            'int'     ,
            'main'    ,
            'print'   ,
            'true'    ,
            'var'     ,
            'while'   ,
        )
    }
    
    tokens = (
        'IDENT' ,               # : str
        'NUMBER',               # : int

        # Punctuation
        'LPAREN'   ,
        'RPAREN'   ,
        'LBRACE'   ,
        'RBRACE'   ,
        'COLON'    ,
        'SEMICOLON',

        'AMP'      ,
        'AMPAMP'   ,
        'BANG'     ,
        'BANGEQ'   ,
        'DASH'     ,
        'EQ'       ,
        'EQEQ'     ,
        'GT'       ,
        'GTEQ'     ,
        'GTGT'     ,
        'HAT'      ,
        'LT'       ,
        'LTEQ'     ,
        'LTLT'     ,
        'PCENT'    ,
        'PIPE'     ,
        'PIPEPIPE' ,
        'PLUS'     ,
        'SLASH'    ,
        'STAR'     ,
        'TILD'     ,
    ) + tuple(keywords.values())

    t_LPAREN    = re.escape('(')
    t_RPAREN    = re.escape(')')
    t_LBRACE    = re.escape('{')
    t_RBRACE    = re.escape('}')
    t_COLON     = re.escape(':')
    t_SEMICOLON = re.escape(';')

    t_AMP       = re.escape('&')
    t_AMPAMP    = re.escape('&&')
    t_BANG      = re.escape('!')
    t_BANGEQ    = re.escape('!=')
    t_DASH      = re.escape('-')
    t_EQ        = re.escape('=')
    t_EQEQ      = re.escape('==')
    t_GT        = re.escape('>')
    t_GTEQ      = re.escape('>=')
    t_GTGT      = re.escape('>>')
    t_HAT       = re.escape('^')
    t_LT        = re.escape('<')
    t_LTEQ      = re.escape('<=')
    t_LTLT      = re.escape('<<')
    t_PCENT     = re.escape('%')
    t_PIPE      = re.escape('|')
    t_PIPEPIPE  = re.escape('||')
    t_PLUS      = re.escape('+')
    t_SLASH     = re.escape('/')
    t_STAR      = re.escape('*')
    t_TILD      = re.escape('~')

    t_ignore = ' \t'            # Ignore all whitespaces
    t_ignore_comment = r'//.*'

    def __init__(self, reporter: Reporter):
        self.lexer    = ply.lex.lex(module = self)
        self.reporter = reporter
        self.bol      = [0]

        # Record the end position of every token (used for the
        # source ranges of the AST nodes)
        token = self.lexer.token

        def token_with_end():
            t = token()
            if t is not None and not hasattr(t, 'endlexpos'):
                t.endlexpos = t.lexpos + len(t.value)
            return t

        self.lexer.token = token_with_end

    def column_of_pos(self, pos: int) -> int:
        assert(0 <= pos)
        return pos - self.bol[bisect.bisect_right(self.bol, pos)-1]

    def t_newline(self, t):
        r'\n+'
        t.lexer.lineno += len(t.value)
        self.bol.append(t.lexer.lexpos)

    def t_IDENT(self, t):
        r'[a-zA-Z_][a-zA-Z0-9_]*'
        if t.value in self.keywords:
            t.type  = self.keywords[t.value]
        return t

    def t_NUMBER(self, t):
        r'0|[1-9][0-9]*'
        t.endlexpos = t.lexpos + len(t.value)
        t.value = int(t.value)
        return t

    def t_error(self, t):
        position = Range.of_position(t.lineno, self.column_of_pos(t.lexpos))
        self.reporter(
            f"illegal character: `{t.value[0]}' -- skipping",
            position = position,
        )
        t.lexer.skip(1)
