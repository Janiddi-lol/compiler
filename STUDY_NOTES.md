# BX Compiler Study Notes

This document records how the BX compiler works. It is organized so that new
compiler stages can be added as the course progresses.

## Compiler overview

A compiler translates a program from a source language into a lower-level
target language while preserving the program's observable behavior.

The BX compiler pipeline is:

```text
BX source text
    -> lexer
token stream
    -> parser
abstract syntax tree (AST)
    -> syntactic and semantic checks
validated AST
    -> IR generation
three-address code (TAC)
    -> assembly generation
assembly
    -> assembler and linker
executable
```

The frontend consists of the lexer, parser, AST representation, and correctness
checks. Lab 1 supplies this frontend and asks us to implement AST-to-TAC
lowering in `bxlib/bxmm.py`.

## Repository structure

```text
compilers/
|-- bxc.py          Compiler driver
|-- bxlib/          Supplied BX compiler package
|-- bx_lib/         Personal learning reimplementation
|-- ply/            Bundled PLY lexer/parser library
|-- examples/       Valid BX programs and expected output
`-- regression/     Invalid BX programs that must be rejected
```

### `examples/`

Every `.bx` file in `examples/` is a valid program. Most have a corresponding
`.expected` file containing the output that the compiled executable must print.

For example:

```text
print42.bx        Source program
print42.expected  Required runtime output
```

A successful test checks both compilation and behavior:

```bash
python3 bxc.py examples/print42.bx
./examples/print42.exe | diff - examples/print42.expected
```

### `regression/`

Every program in `regression/` is intentionally invalid. A correct compiler
must reject it, print a useful diagnostic, and exit with a nonzero status.

Different files exercise different frontend stages:

| Problem | Responsible stage |
|---|---|
| Illegal character such as `@` | Lexer |
| Missing semicolon or unmatched parenthesis | Parser |
| Undeclared or redeclared variable | Syntactic checker |
| Integer literal outside the allowed range | Syntactic checker |

Both directories are necessary. A compiler must accept valid programs and
reject invalid programs.

## Frontend

The BX frontend is implemented by these files:

| File | Responsibility |
|---|---|
| `bxlib/bxlexer.py` | Convert source characters into tokens |
| `bxlib/bxparser.py` | Convert tokens into an AST |
| `bxlib/bxast.py` | Define AST node classes |
| `bxlib/bxsynchecker.py` | Perform context-sensitive correctness checks |
| `bxlib/bxerrors.py` | Report errors with source locations |

### Lexer responsibility

The lexer recognizes categories of source text. It does not decide whether the
whole program is grammatically or semantically valid.

For example:

```bx
print(x + 3);
```

is recognized as the following token stream:

```text
PRINT LPAREN IDENT("x") PLUS NUMBER(3) RPAREN SEMICOLON
```

Whitespace and comments are consumed but do not become tokens.

### Token declarations

PLY requires a `tokens` collection containing all token category names:

```python
tokens: tuple[str, ...] = (
    "IDENT",
    "NUMBER",
    "LPAREN",
    "RPAREN",
    "PLUS",
    "SEMICOLON",
)
```

The annotation `tuple[str, ...]` means an arbitrary-length tuple in which every
element is a string. The ellipsis means "any number of elements," not a literal
element inside the tuple.

### PLY naming convention

`t_<TOKEN-NAME>` is not special Python syntax. It is a convention that PLY
discovers through introspection.

For example:

```python
t_PLUS = re.escape("+")
```

means that text matching this regular expression produces a `PLUS` token.
`PLUS` must also appear in `tokens`.

There are two main forms of rules.

#### String rules

Use a string rule when no payload conversion or additional action is required:

```python
t_LPAREN = re.escape("(")
t_PLUS = re.escape("+")
t_LTLT = re.escape("<<")
```

PLY creates and returns the token directly.

#### Function rules

Use a function when the matched token needs processing:

```python
def t_NUMBER(self, token):
    r"0|[1-9][0-9]*"
    token.value = int(token.value)
    return token
```

The function's docstring is its regular expression. PLY creates a token with
the raw matched text, invokes the function, and uses the returned token.

Returning `None` consumes the text without emitting a token.

### Keywords and identifiers

Identifiers and keywords initially match the same regular expression:

```python
def t_IDENT(self, token):
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    if token.value in self.keywords:
        token.type = self.keywords[token.value]
    return token
```

This produces:

```text
counter -> IDENT("counter")
print   -> PRINT("print")
int     -> INT("int")
```

Recognizing every word as an identifier first avoids separate regular
expressions for every keyword.

### Special lexer rules

#### Ignored characters

```python
t_ignore = " \t"
```

This is a collection of individual characters that PLY skips through a fast
path. It is not a regular expression.

#### Ignored comments

```python
t_ignore_comment = r"//.*"
```

This is a regular-expression rule whose matches are discarded.

#### Newlines

```python
def t_newline(self, token):
    r"\n+"
    token.lexer.lineno += len(token.value)
    self.bol.append(token.lexer.lexpos)
```

The function does not return a token, so newlines do not enter the token
stream. It updates line information instead.

For one newline:

```python
token.value == "\n"
len(token.value) == 1
```

Therefore the line number increases by one. If two consecutive newline
characters match, `len(token.value)` is two and the line number increases by
two.

#### Illegal characters

When no normal rule matches, PLY invokes `t_error()`:

```python
def t_error(self, token):
    position = Range.of_position(
        token.lineno,
        self.column_of_pos(token.lexpos),
    )
    self.reporter(
        f"illegal character: `{token.value[0]}' -- skipping",
        position=position,
    )
    token.lexer.skip(1)
```

Calling `skip(1)` is essential. Without it, the lexer would encounter the same
illegal character repeatedly and make no progress.

### How PLY builds the lexer

The BX constructor contains:

```python
self.lexer = ply.lex.lex(module=self)
```

There are two lexer-related objects:

```text
BX Lexer object (`self`)
|-- BX rules and keywords
|-- Reporter
|-- beginning-of-line positions
`-- self.lexer
    `-- generated PLY runtime lexer
```

`import ply.lex` imports the `ply/lex.py` module. The function
`ply.lex.lex(...)` builds a configured runtime lexer.

The argument name `module` is slightly misleading because PLY also accepts an
object. Given `module=self`, PLY performs the equivalent of:

```python
for name in dir(self):
    value = getattr(self, name)
```

It reads `tokens`, finds the `t_...` rules, validates them, orders them, and
combines them into master regular expressions conceptually similar to:

```regex
(?P<t_IDENT>[a-zA-Z_][a-zA-Z0-9_]*)
|(?P<t_NUMBER>0|[1-9][0-9]*)
|(?P<t_ignore_comment>//.*)
|(?P<t_LPAREN>\()
|(?P<t_PLUS>\+)
|...
```

The named group tells PLY which rule matched.

Function rules are ordered by their location in the source file. String rules
are ordered by regular-expression length from longest to shortest. This helps
multi-character operators match before shorter overlapping rules.

PLY is designed as a generator using composition. Our BX lexer contains a
configured PLY lexer instead of inheriting from PLY's internal runtime class.
Subclassing the runtime class would not automatically discover or compile the
BX rules.

### How source text reaches the lexer

The call path begins in `bxc.py`:

```python
with open(args.input, "r") as stream:
    program = stream.read()

program = Parser(reporter=reporter).parse(program)
```

`bxlib/bxparser.py` passes the source and generated lexer to PLY/Yacc:

```python
ast = self.parser.parse(
    program,
    lexer=self.lexer.lexer,
    tracking=True,
)
```

Inside `ply/yacc.py`, PLY calls:

```python
lexer.input(input)
get_token = lexer.token
```

The `input()` implementation in `ply/lex.py` stores:

```python
self.lexdata = source
self.lexpos = 0
self.lexlen = len(source)
```

The parser then calls `get_token()` whenever it needs another lookahead token.

### How scanning advances

PLY maintains an absolute position named `lexpos`. At a token boundary it calls
the compiled regular expression with `match`, not `search`:

```python
match = master_regex.match(source, lexpos)
```

The match must begin exactly at `lexpos`. A successful rule consumes a complete
lexeme and advances directly to the end of that match.

For:

```text
def main() {
```

the positions advance conceptually as follows:

```text
position 0: match "def"  -> advance to 3
position 3: ignore space -> advance to 4
position 4: match "main" -> advance to 8
position 8: match "("    -> advance to 9
position 9: match ")"    -> advance to 10
```

PLY does not return separate tokens for `d`, `e`, and `f`; the identifier
regular expression consumes `def` in one operation.

### Beginning-of-line positions and columns

PLY records a token's absolute character offset in `token.lexpos`. Error
messages need a column relative to the token's line, so the BX wrapper stores
the positions where lines begin:

```python
self.bol = [0]
```

`bol` means "beginning of lines." For example:

```python
self.bol = [0, 13, 26, 44]
```

means:

```text
line 1 begins at absolute position 0
line 2 begins at absolute position 13
line 3 begins at absolute position 26
line 4 begins at absolute position 44
```

It is not used to give indentation semantic meaning. BX ignores indentation.
It is used for source locations and caret placement in diagnostics.

The conversion function is:

```python
def column_of_pos(self, pos: int) -> int:
    assert 0 <= pos
    line_index = bisect.bisect_right(self.bol, pos) - 1
    line_start = self.bol[line_index]
    return pos - line_start
```

Given:

```python
self.bol = [0, 13, 26, 44]
pos = 34
```

the latest line beginning not greater than 34 is 26, so:

```text
column = 34 - 26 = 8
```

`bisect_right` performs this lookup efficiently in the sorted list. Tabs
require a later visual-column adjustment, which `bxerrors.py` performs with
`expandtabs()`.

### Token end positions

The BX lexer wraps PLY's `token()` method:

```python
original_token = self.lexer.token

def token_with_end():
    token = original_token()
    if token is not None and not hasattr(token, "endlexpos"):
        token.endlexpos = token.lexpos + len(token.value)
    return token

self.lexer.token = token_with_end
```

This gives tokens both a starting and an ending absolute position. Number rules
must calculate `endlexpos` before converting the matched text to an integer,
because `len(42)` is invalid.

### Complete lexer walkthrough

Consider:

```bx
def main() {
  var x = 12 + 3 : int; // initialize x
  print(x);
}
```

The significant matches are:

| Source | Matching rule | Result |
|---|---|---|
| `def` | `t_IDENT()` | Reclassified as `DEF` |
| space | `t_ignore` | Discarded |
| `main` | `t_IDENT()` | Reclassified as `MAIN` |
| `(` | `t_LPAREN` | `LPAREN` |
| `)` | `t_RPAREN` | `RPAREN` |
| `{` | `t_LBRACE` | `LBRACE` |
| newline | `t_newline()` | Updates positions; discarded |
| `var` | `t_IDENT()` | Reclassified as `VAR` |
| `x` | `t_IDENT()` | `IDENT("x")` |
| `=` | `t_EQ` | `EQ` |
| `12` | `t_NUMBER()` | `NUMBER(12)` |
| `+` | `t_PLUS` | `PLUS` |
| `3` | `t_NUMBER()` | `NUMBER(3)` |
| `:` | `t_COLON` | `COLON` |
| `int` | `t_IDENT()` | Reclassified as `INT` |
| `;` | `t_SEMICOLON` | `SEMICOLON` |
| comment | `t_ignore_comment` | Discarded |
| `print` | `t_IDENT()` | Reclassified as `PRINT` |
| `}` | `t_RBRACE` | `RBRACE` |

### The lexer produces a stream, not one list

The formatted token sequence shown in explanations is a human-readable view of
the stream. A single call to `lexer.token()` returns one `LexToken` object, not
the entire sequence:

```python
token1 = lexer.token()  # DEF
token2 = lexer.token()  # MAIN
token3 = lexer.token()  # LPAREN
```

Eventually `lexer.token()` returns `None` to signal the end of input.

PLY/Yacc consumes this lazily:

```text
parser requests token -> lexer returns DEF
parser processes DEF
parser requests token -> lexer returns MAIN
parser processes MAIN
...
```

The lexer and parser therefore work together instead of first creating a full
token list. A test program can collect the stream explicitly if desired:

```python
lexer.input(source)
tokens = list(lexer)
```

### Parser responsibility

The parser interprets the token stream according to the BX grammar and creates
AST nodes. For example:

```python
def p_stmt_print(self, p):
    """stmt : PRINT LPAREN expr RPAREN SEMICOLON"""
    p[0] = PrintStatement(value=p[3], position=self._position(p))
```

The parser also handles operator precedence and associativity. Once parsing is
complete, punctuation used only for structure, such as parentheses and
semicolons, is no longer represented directly in the AST.

### AST responsibility

`bxlib/bxast.py` defines expression and statement nodes.

Expressions include:

- `VarExpression`
- `IntExpression`
- `OpAppExpression`

Statements include:

- `VarDeclStatement`
- `AssignStatement`
- `PrintStatement`

Every node may carry a source range for diagnostics. In straight-line BX, a
program is represented as a list of statements.

### Syntactic checker responsibility

The parser recognizes grammatical structure, but a context-free grammar cannot
conveniently enforce every language rule. `bxsynchecker.py` traverses the AST
and checks that:

- Variables are declared before use.
- Assignment targets have been declared.
- Variables are not declared twice.
- Integer literals are in the supported range.

This separation is important:

```text
Lexer:  Is this text an identifier?
Parser: Does this token sequence form an assignment?
Checker: Was the assigned variable previously declared?
```

### Future project: rewrite the lexer engine for learning

Reimplementing the important ideas from `ply/lex.py` is a useful way to learn
how generated lexers work. The bundled `ply/` directory should remain unchanged
because it is part of the starter kit and is required for submission. The
learning version should live in a separate module, for example:

```text
learning_lexer/
|-- token.py
|-- rules.py
|-- lexer.py
`-- tests/
```

The goal is not initially to reproduce every PLY feature. Start with the subset
needed by straight-line BX, establish behavioral parity, and expand only after
the small implementation is understood.

#### Design principles

- Use modern Python type annotations throughout.
- Represent tokens explicitly with a `dataclass` instead of dynamic attributes.
- Keep the generic scanning engine separate from BX-specific token rules.
- Prefer composition: a BX specification configures a generic lexer engine.
- Require every successful rule to consume at least one character.
- Preserve exact line, column, start, and end positions.
- Make rule priority and longest-match behavior explicit.
- Report illegal input without allowing an infinite loop.
- Avoid module-level mutable state so multiple lexer instances are independent.
- Treat the existing PLY behavior and regression suite as the compatibility
  specification.

#### Phase 1: explicit token model

- [ ] Define a typed `Token` dataclass.
- [ ] Include `type`, `value`, `lineno`, `lexpos`, and `endlexpos`.
- [ ] Decide whether positions should use raw integers or a dedicated source
  position type.
- [ ] Add readable `__repr__` output for debugging.
- [ ] Write construction and representation tests.

One possible starting shape is:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class Token:
    type: str
    value: Any
    lineno: int
    lexpos: int
    endlexpos: int
```

#### Phase 2: typed lexer rules

- [ ] Define a `Rule` dataclass containing a name, compiled regular expression,
  priority, and optional callback.
- [ ] Distinguish emitted-token rules from ignored rules.
- [ ] Reject regular expressions that can match the empty string.
- [ ] Validate that emitted token names appear in the declared token set.
- [ ] Define an explicit and documented rule-ordering policy.

At first, rules may be registered directly instead of discovered through
`t_...` names. Reflection can be added later as a separate learning step.

#### Phase 3: basic scanning loop

- [ ] Implement `input(source)` to store the text and reset scanning state.
- [ ] Implement `token()` to return one token or `None` at end of input.
- [ ] Match only at the current position with `regex.match`, not `search`.
- [ ] Advance to `match.end()` after every successful match.
- [ ] Skip spaces, tabs, and ignored rules without emitting tokens.
- [ ] Invoke callbacks for identifiers and numbers.
- [ ] Ensure an unmatched character is reported and skipped.
- [ ] Make the lexer iterable with `__iter__` and `__next__`.

The initial loop can try rules in priority order. After correctness is clear,
Phase 6 can combine them into a master regular expression.

#### Phase 4: source positions

- [ ] Start line numbering at one and absolute positions at zero.
- [ ] Record beginning-of-line positions.
- [ ] Implement `column_of_pos()` with binary search.
- [ ] Handle one newline and runs of consecutive newlines.
- [ ] Preserve token end positions before converting payloads such as numbers.
- [ ] Test spaces and tabs in error diagnostics.
- [ ] Test tokens before and after empty lines.

#### Phase 5: BX lexical specification

- [ ] Register all BX punctuation and operator rules.
- [ ] Implement identifier recognition.
- [ ] Reclassify reserved identifiers as keywords.
- [ ] Convert number payloads from strings to integers.
- [ ] Ignore `//` comments.
- [ ] Reject unsupported characters such as `@`.
- [ ] Confirm that unary minus remains `DASH` followed by `NUMBER`.
- [ ] Confirm that integer-range validation remains outside the lexer.

#### Phase 6: master regular expression

- [ ] Give every rule a unique named regular-expression group.
- [ ] Join rule expressions with alternation.
- [ ] Compile the combined expression once during lexer construction.
- [ ] Use `match.lastgroup` to identify the selected rule.
- [ ] Preserve priority for overlapping rules.
- [ ] Compare the simple rule-by-rule engine with the master-regex engine.
- [ ] Document the correctness and performance tradeoff.

A simplified master expression may look like:

```regex
(?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*)
|(?P<NUMBER>0|[1-9][0-9]*)
|(?P<COMMENT>//.*)
|(?P<LTLT><<)
|(?P<PLUS>\+)
|...
```

#### Phase 7: compatibility tests

- [ ] Run every program in `examples/` through both lexers.
- [ ] Compare token types, payloads, line numbers, and absolute positions.
- [ ] Run lexer-related programs from `regression/`.
- [ ] Test empty source, whitespace-only source, and comment-only source.
- [ ] Test identifiers adjacent to punctuation.
- [ ] Test all single- and multi-character operators.
- [ ] Test a long identifier and a long integer literal.
- [ ] Test an illegal character at the beginning, middle, and end of input.
- [ ] Test repeated calls to `input()` on the same lexer instance.

The comparison should normalize both implementations to tuples such as:

```python
(token.type, token.value, token.lineno, token.lexpos, token.endlexpos)
```

#### Phase 8: optional PLY-style reflection

- [ ] Discover `tokens` and `t_...` attributes from a specification object.
- [ ] Support both string rules and callback rules.
- [ ] Read a callback's regular expression from its docstring.
- [ ] Recognize special names such as `t_ignore` and `t_error`.
- [ ] Validate callback signatures.
- [ ] Produce clear construction-time diagnostics for invalid rules.
- [ ] Keep reflection separate from the scanning engine so both parts remain
  independently testable.

#### Phase 9: optional advanced features

- [ ] Add inclusive and exclusive lexer states only if a later language feature
  requires them.
- [ ] Add an explicit EOF callback.
- [ ] Add lexer cloning only if a concrete use case appears.
- [ ] Benchmark rule-by-rule matching against the master expression.
- [ ] Document which PLY features are intentionally unsupported.

#### Completion criteria

The learning lexer is ready to integrate only when:

- [ ] Its public interface is documented.
- [ ] All unit tests pass.
- [ ] Its token stream matches PLY for all BX examples.
- [ ] Its diagnostics correctly identify lexer regression cases.
- [ ] Replacing PLY in a separate experimental driver does not change the ASTs.
- [ ] The original `ply/` directory and submission compiler remain untouched.

## IR generation

Lab 1 lowers the validated AST into three-address code in `bxlib/bxmm.py`.
Detailed notes about TAC, bottom-up maximal munch, and top-down maximal munch
will be expanded in this section.

## Backend

The supplied straight-line backend translates TAC into machine-specific
assembly. Detailed backend notes will be added as later labs introduce control
flow, procedures, instruction selection, and register allocation.
