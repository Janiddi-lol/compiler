# --------------------------------------------------------------------
from __future__ import annotations
from abc import ABC, abstractmethod
from contextlib import contextmanager
import math
import sys

from typing import Iterator

from .bxast import *

# ====================================================================
class _ReportContextManager:
    def __init__(self, reporter: Reporter) -> None:
        self.cp       = reporter.nerrors
        self.reporter = reporter
    
    def __bool__(self):
        return self.cp == self.reporter.nerrors
        

# --------------------------------------------------------------------
class Reporter(ABC):
    def __init__(self, source: str) -> None:
        self.source = source.splitlines()
        self.nerrors = 0
        
    def __call__(self, message:str, position: Range | None = None) -> None:
        self.nerrors += 1
        self._report(message, position)
        
    @contextmanager
    def checkpoint(self) -> Iterator[_ReportContextManager]:
        yield _ReportContextManager(self)
        
    @abstractmethod
    def _report(self, message:str, position: Range | None) -> None:
        pass
    

# --------------------------------------------------------------------
class DefaultReporter(Reporter):
    def _report(self, message: str, position: Range | None) -> None:
        
        # Print to stderr:
        #   1. a blank line separator if this isn't the first error
        #      (nerrors > 1) -- keeps multiple errors visually apart
        #   2. `line N: message` if the range is on one line, or
        #      `lines N--M: message` if it spans several
        #   3. up to 2 lines of source *before* the error line, plus
        #      the error line(s) themselves, each prefixed with a
        #      right-aligned line-number gutter, e.g. `| 07:  ...`
        #   4. IF the range is single-line: a line of spaces + `^`
        #      characters underneath, aligned under the exact columns
        #      the range covers
        #
        # If `position is None`, just print the bare message -- there's
        # nothing to point at.
        #
        # Two details that are easy to get wrong and not really the
        # point of the exercise, so take them as given:
        #  - gutter width: `max(2, math.ceil(math.log(len(self.source)+1, 10)))`
        #    (just enough digits to right-align the largest line number,
        #    minimum width 2)
        #  - column alignment must go through `str.expandtabs()` on
        #    both the full line and the slice before the error, because
        #    a tab is 1 character but several *visual* columns -- a raw
        #    character-index comparison would misalign the carets on
        #    any line containing a tab.
        def print_error(*x: str) -> None:
            print(*x, file=sys.stderr)
        
        if self.nerrors > 1:
            print_error()
            
        if position is None:
            print_error(message)
        else:
            width = max(2, math.ceil(math.log(len(self.source)+1, 10)))
            
            if position.start[0] == position.end[0]:
                print_error(f"line {position.start[0]}: {message}")
                l2 = position.start[0] - 1
                l1 = max(l2-2,0)
                col_pos = (position.start[1], position.end[1])
            
            else:
                print_error(f'lines {position.start[0]} -- {position.end[0]}: {message}')
                l1 = position.start[0] - 1
                l2 = position.end[0] - 1
                col_pos = None
            
            print_error() # new line 
            
            for i in range(l1, l2+1):
                print_error(f'| {i+1:0{width}}:', self.source[i].expandtabs())
            if col_pos is not None:
                # visual columns for a single-line error case (tabs expanded)
                line = self.source[l2]
                v0 = len(line[:col_pos[0]].expandtabs())
                v1 = len(line[:col_pos[1]].expandtabs())
                print_error(' ' * (v0+width+3), '^' * max(1, v1-v0))
                