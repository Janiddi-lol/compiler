from bx_lib.bxast import *
from bx_lib.bxerrors import DefaultReporter
from bx_lib.bxparser import Parser

    
def parse_source(source:str):
    reporter = DefaultReporter(source)
    program = Parser(reporter).parse(source)
    
    return program, reporter

def test_empty_program():
    program, reporter = parse_source(
        """
        def main() {
        }
        """
    )
    
    assert program == []
    assert reporter.nerrors == 0
    
#----------Test an integer print statement------------
def test_print_integer():
    program, reporter = parse_source(
        """
        def main() {
        print(42);
        }
        """
    )
    
    assert reporter.nerrors == 0
    assert len(program) == 1
    
    statement = program[0]
    
    assert isinstance(statement, PrintStatement)
    assert isinstance(statement.value, IntExpression)
    assert statement.value.value == 42
    
#-----------Test a variable declaration---------------
def test_variable_declaration():
    program, reporter = parse_source(
    """
    def main() {
        var count = 42 : int;
    }
    """
    )
    
    assert reporter.nerrors == 0
    assert len(program) == 1
    
    declaration = program[0]
    
    assert isinstance(declaration, VarDeclStatement)
    assert isinstance(declaration.init, IntExpression)
    assert declaration.name.value == "count"
    assert declaration.init.value == 42

#------------Test assignment----------------
def test_assignment():
    program, reporter = parse_source(
    """
    def main() {
        x = 10;
    }
    """
    )
    
    assert reporter.nerrors == 0
    assert len(program) == 1
    
    assignment = program[0]
    
    assert isinstance(assignment, AssignStatement)
    assert assignment.lhs.value == "x"
    assert isinstance(assignment.rhs, IntExpression)
    assert assignment.rhs.value == 10
    
#---------------Test Variable expression-------------
def test_variable_expression():
    program, reporter = parse_source(
    """
    def main() {
        print(x);
    }
    """
    )
    
    assert reporter.nerrors == 0
    statement = program[0]
    
    assert isinstance(statement, PrintStatement)
    assert isinstance(statement.value, VarExpression)
    assert statement.value.name.value == "x"

#--------------------Test operator precedence--------------
def test_multiplication_has_higher_precedence_than_addition():
    program, reporter = parse_source(
        """
        def main() {
            print(1 + 2 * 3);
        }
        """
    )

    assert reporter.nerrors == 0

    expression = program[0].value

    assert isinstance(expression, OpAppExpression)
    assert expression.operator == "addition"

    left, right = expression.arguments

    assert isinstance(left, IntExpression)
    assert left.value == 1

    assert isinstance(right, OpAppExpression)
    assert right.operator == "multiplication"
    assert [argument.value for argument in right.arguments] == [2, 3]
    
# ------------ Test Parantheses---------------------------------
def test_parentheses_override_precedence():
    program, reporter = parse_source(
        """
        def main() {
            print((1 + 2) * 3);
        }
        """
    )

    assert reporter.nerrors == 0

    expression = program[0].value

    assert expression.operator == "multiplication"

    left, right = expression.arguments

    assert isinstance(left, OpAppExpression)
    assert left.operator == "addition"
    assert right.value == 3
    
# --------------------Test unary precedence----------------------
def test_unary_minus_binds_before_addition():
    program, reporter = parse_source(
        """
        def main() {
            print(-1 + 2);
        }
        """
    )

    assert reporter.nerrors == 0

    expression = program[0].value

    assert expression.operator == "addition"

    left, right = expression.arguments

    assert isinstance(left, OpAppExpression)
    assert left.operator == "opposite"
    assert left.arguments[0].value == 1
    assert right.value == 2

# ---------- Test multiple statements---------------
def test_multiple_statements_preserve_order():
    program, reporter = parse_source(
        """
    def main() {
        var x = 1 : int;
        x = 2;
        print(x);
    }
    """
    )

    assert reporter.nerrors == 0
    assert len(program) == 3

    assert isinstance(program[0], VarDeclStatement)
    assert isinstance(program[1], AssignStatement)
    assert isinstance(program[2], PrintStatement)
    
# ---------------Test a syntax error-----------------

def test_missing_semicolon_reports_error(capsys):
    program, reporter = parse_source(
        """
        def main() {
            print(42)
        }
        """
    )

    captured = capsys.readouterr()

    assert program is None
    assert reporter.nerrors >= 1
    assert "syntax error" in captured.err