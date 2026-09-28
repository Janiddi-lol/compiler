#! /usr/bin/env python3

# --------------------------------------------------------------------
# Requires Python3 >= 3.10

# --------------------------------------------------------------------
import argparse
import os
import platform
import pprint
import subprocess as sp
import sys

from bxlib.bxast        import *
from bxlib.bxerrors     import DefaultReporter
from bxlib.bxmm         import lower
from bxlib.bxtac        import tac_to_string
from bxlib.bxtacrun     import run as runtac, TACError
from bxlib.bxasmgen     import AsmGen, AsmGenError
from bxlib.bxparser     import Parser
from bxlib.bxtychecker  import check as tycheck

# ====================================================================
# Parse command line arguments

def parse_args():
    parser = argparse.ArgumentParser(prog = os.path.basename(sys.argv[0]))

    parser.add_argument('input', help = 'input file (.bx)')

    parser.add_argument(
        '--dump-ast', action = 'store_true',
        help = 'print the AST on the standard output and exit')

    parser.add_argument(
        '--tac-only', action = 'store_true',
        help = 'stop after the generation of the TAC (.tac) file')

    parser.add_argument(
        '--run-tac', action = 'store_true',
        help = 'interpret the TAC instead of compiling it to assembly')

    parser.add_argument(
        '--arch', choices = sorted(AsmGen.BACKENDS.keys()),
        help = 'target architecture (default: the current machine)')

    aout = parser.parse_args()

    if os.path.splitext(aout.input)[1].lower() != '.bx':
        parser.error('input filename must end with the .bx extension')

    return aout

# --------------------------------------------------------------------
def select_backend(arch):
    system, machine = platform.system(), platform.machine()

    if arch is None:
        backend = AsmGen.select_backend(system, machine)
        if backend is None:
            print(
                f'no assembly backend for this machine ({system}/{machine}): '
                f'use --arch to select one, or --tac-only',
                file = sys.stderr)
            exit(1)
    else:
        backend = AsmGen.get_backend(arch)

    native = (system, machine) == (backend.SYSTEM, backend.MACHINE)

    return backend, native

# ====================================================================
# Main entry point

def _main():
    args = parse_args()

    # The frontend (and your lowering) are recursive: allow deep ASTs
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20_000))

    # Read the source file
    try:
        with open(args.input, 'r') as stream:
            prgm = stream.read()

    except IOError as e:
        print(f'cannot read input file {args.input}: {e}', file = sys.stderr)
        exit(1)

    # Frontend (provided): lexing, parsing, type checking.
    # Errors are reported on the standard error by `reporter`.
    reporter = DefaultReporter(source = prgm)
    prgm = Parser(reporter = reporter).parse(prgm)
    basename = os.path.splitext(args.input)[0]

    if prgm is None:
        exit(1)

    if not tycheck(prgm, reporter):
        exit(1)

    if args.dump_ast:
        pprint.pprint(prgm)
        exit(0)

    # Lowering (yours): AST -> TAC
    body = lower(prgm)

    # Write the TAC program, in its textual form
    try:
        with open(f'{basename}.tac', 'w') as stream:
            stream.write(tac_to_string('@main', body))

    except IOError as e:
        print(f'cannot write output file {basename}.tac: {e}', file = sys.stderr)
        exit(1)

    if args.tac_only:
        exit(0)

    if args.run_tac:
        try:
            runtac(body)
        except TACError as e:
            print(f'{basename}.tac: {e}', file = sys.stderr)
            exit(1)
        exit(0)

    # Backend: TAC -> assembly -> executable
    backend, native = select_backend(args.arch)

    try:
        asm = backend.lower(body)

    except AsmGenError as e:
        print(f'{args.input}: {e}', file = sys.stderr)
        exit(1)

    try:
        with open(f'{basename}.s', 'w') as stream:
            stream.write(asm)

    except IOError as e:
        print(f'cannot write output file {basename}.s: {e}', file = sys.stderr)
        exit(1)

    if not native:
        print(
            f'{basename}.s targets {backend.NAME}, not this machine: '
            'not assembling it', file = sys.stderr)
        exit(0)

    try:
        sp.check_call(['gcc', '-o', f'{basename}.exe', f'{basename}.s'])

    except FileNotFoundError:
        print('cannot find gcc: the executable has not been produced', file = sys.stderr)
        exit(1)

    except sp.CalledProcessError as e:
        print(f'gcc failed with exit code {e.returncode}', file = sys.stderr)
        exit(1)

# --------------------------------------------------------------------
if __name__ == '__main__':
    _main()
