from bx_lib.bxerrors import DefaultReporter
from bx_lib.bxlexer import Lexer

import pytest

def lex_source(source: str):
    reporter = DefaultReporter(source)
    lexer = Lexer(reporter)
    lexer.lexer.input(source)
    tokens = []
    while True:
        token = lexer.lexer.token()
        
        if token is None:
            break
        
        tokens.append(token)
    
    return lexer, tokens, reporter

def test_keywords_and_identifiers():
    source = "def main var print int define main2"
    
    _, tokens, reporter = lex_source(source)
    
    actual_types = [token.type for token in tokens]
    
    expected_types = [
        "DEF",
        "MAIN",
        "VAR",
        "PRINT",
        "INT",
        "IDENT",
        "IDENT",
    ]
    
    assert actual_types == expected_types
    assert reporter.nerrors == 0

def test_number_is_converted_to_integer():
    _, tokens, reporter = lex_source("42")
    
    assert len(tokens) == 1
    token = tokens[0]
    
    assert token.type == "NUMBER"
    assert token.value == 42
    assert isinstance(token.value, int)
    assert reporter.nerrors == 0

@pytest.mark.parametrize(
    ("source", "expected_type"),
    [
        ("(", "LPAREN"),
        (")", "RPAREN"),
        ("{", "LBRACE"),
        ("}", "RBRACE"),
        (":", "COLON"),
        (";", "SEMICOLON"),
        ("&", "AMP"),
        ("-", "DASH"),
        ("=", "EQ"),
        (">>", "GTGT"),
        ("^", "HAT"),
        ("<<", "LTLT"),
        ("%", "PCENT"),
        ("|", "PIPE"),
        ("+", "PLUS"),
        ("/", "SLASH"),
        ("*", "STAR"),
        ("~", "TILD"),
    ],
)

def test_punctuation_and_operators(source, expected_type):
    _, tokens, reporter = lex_source(source)

    assert len(tokens) == 1
    assert tokens[0].type == expected_type
    assert reporter.nerrors == 0
    
def test_whitespace_comments_and_newlines():
    source = "var\tx // ignored comment\n\nprint"

    _, tokens, reporter = lex_source(source)

    assert [token.type for token in tokens] == [
        "VAR",
        "IDENT",
        "PRINT",
    ]

    assert [token.lineno for token in tokens] == [
        1,
        1,
        3,
    ]

    assert reporter.nerrors == 0
    

def test_token_positions():
    source = "var count = 42;"

    _, tokens, reporter = lex_source(source)

    actual = [
        (token.type, token.lexpos, token.endlexpos)
        for token in tokens
    ]

    expected = [
        ("VAR", 0, 3),
        ("IDENT", 4, 9),
        ("EQ", 10, 11),
        ("NUMBER", 12, 14),
        ("SEMICOLON", 14, 15),
    ]

    assert actual == expected
    assert reporter.nerrors == 0
    

def test_column_after_newline():
    source = "var x;\n    print"

    lexer, tokens, reporter = lex_source(source)

    print_token = tokens[-1]

    assert print_token.type == "PRINT"
    assert print_token.lineno == 2
    assert lexer.column_of_pos(print_token.lexpos) == 4
    assert reporter.nerrors == 0
    

def test_illegal_character(capsys):
    _, tokens, reporter = lex_source("var @ x")

    captured = capsys.readouterr()

    assert [token.type for token in tokens] == [
        "VAR",
        "IDENT",
    ]

    assert reporter.nerrors == 1
    assert "illegal character" in captured.err
    assert "@" in captured.err