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

