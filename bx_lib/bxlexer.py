import bisect 
import ply.lex
import re

from typing import Protocol, Any

from .bxerrors import Range, Reporter

# bisect algorithm used for searching an element of pre-sorted list in O(logn)

# =================================================
# TokenLike Protocol for type hinting
class TokenLike(Protocol):
    """Attrubutes expceted on tokens produced by the BX lexer"""
    type: str 
    value : Any
    lineno: int
    lexpos: int
    endlexpos: int
    lexer: ply.lex.Lexer


# =========================================================================
# BX lexer definition

class Lexer:
    keywords = {
        x : x.upper() for x in ('def', 'int', 'main', 'print', 'var')
    }
    tokens: tuple[str, ...] = (
        'IDENT',        # : str
        'NUMBER',       # : int
        
        # Punctuation
        'LPAREN',
        'RPAREN',
        'LBRACE',
        'RBRACE',
        'COLON',
        'SEMICOLON',
        
        'AMP',
        'DASH',
        'EQ',
        'GTGT',
        'HAT',
        'LTLT',
        'PCENT',
        'PIPE',
        'PLUS',
        'SLASH',
        'STAR',
        'TILD',
        ) + tuple(keywords.values())
    
    # --------Reg expres. for punctuations and operators--------
    t_LPAREN = re.escape('(')
    t_RPAREN    = re.escape(')')
    t_LBRACE    = re.escape('{')
    t_RBRACE    = re.escape('}')
    t_COLON     = re.escape(':')
    t_SEMICOLON = re.escape(';')

    t_AMP       = re.escape('&')
    t_DASH      = re.escape('-')
    t_EQ        = re.escape('=')
    t_GTGT      = re.escape('>>')
    t_HAT       = re.escape('^')
    t_LTLT      = re.escape('<<')
    t_PCENT     = re.escape('%')
    t_PIPE      = re.escape('|')
    t_PLUS      = re.escape('+')
    t_SLASH     = re.escape('/')
    t_STAR      = re.escape('*')
    t_TILD      = re.escape('~')
    
    #-----------------Ignore inputs--------------------
    t_ignore = ' \t' # ignore spaces and tabs
    t_ignore_comment = r"//.*"
    
    def __init__(self, reporter: Reporter):
        self.lexer = ply.lex.lex(module=self)
        self.reporter = reporter
        # bol - beginning of the line
        self.bol = [0]
        
        # Record the end position of every token (used for 
        # the source ranges of the AST nodes)
        token = self.lexer.token
        
        def token_with_end() -> TokenLike | None :
            t : TokenLike | None = token()
            if t is not None and not hasattr(t,'endlexpos'):
                t.endlexpos = t.lexpos + len(t.value)
            return t
        
        self.lexer.token = token_with_end
        
    def column_of_pos(self, pos: int) -> int:
        assert (0<= pos)
        return pos - self.bol[bisect.bisect_right(self.bol, pos)-1]
    
    
    def t_newline(self, t: TokenLike) -> None:
        r'\n+' # one or more occurence of new line
        t.lexer.lineno += len(t.value)
        self.bol.append(t.lexer.lexpos)
        
    def t_IDENT(self, t : TokenLike) -> TokenLike:
        r'[a-zA-Z_][a-zA-Z0-9_]*'
        if t.value in self.keywords:
            t.type = self.keywords[t.value]
        return t
    
    def t_NUMBER(self, t: TokenLike) -> TokenLike:
        r'0|[1-9][0-9]*'
        t.endlexpos = t.lexpos + len(t.value)
        t.value = int(t.value)
        return t
    
    def t_error(self, t: TokenLike) -> None:
        position = Range.of_position(t.lineno, self.column_of_pos(t.lexpos))
        self.reporter(
            f"illegal character: `{t.value[0]}` -- skipping",
            position=position
        )
        t.lexer.skip(1)