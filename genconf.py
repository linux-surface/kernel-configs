#!/usr/bin/env python

import sys
import os
import argparse
import kconfiglib as K
import colorama as C

from pathlib import Path


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def print_banner(msg):
    msg = f"-- {msg} ".ljust(100, '-')
    print(f"{C.Style.BRIGHT}{msg}{C.Style.RESET_ALL}")


def build_cli():
    p = argparse.ArgumentParser(description='Utility for merging and sanitizing kernel configs')
    p.add_argument('srctree', metavar='srctree', type=Path, help='path to kernel source tree')
    p.add_argument('conf', metavar='conf', nargs='+', type=Path, help='configuration file(s)')
    p.add_argument('-o', '--output', metavar='out', action='store', type=Path, default='out.config', help='output file')
    p.add_argument('-f', '--try-fix-deps', action='store_true', help='try to automatically fix dependencies')
    return p


def user_value(sym):
    return sym.user_value if sym.user_value is not None else sym.tri_value


def expr_user_value(expr):
    # based on https://github.com/ulfalizer/Kconfiglib expr_value()

    if expr.__class__ is not tuple:
        return user_value(expr)

    if expr[0] is K.AND:
        v1 = expr_user_value(expr[1])
        # Short-circuit the n case as an optimization (~5% faster
        # allnoconfig.py and allyesconfig.py, as of writing)
        return 0 if not v1 else min(v1, expr_user_value(expr[2]))

    if expr[0] is K.OR:
        v1 = expr_user_value(expr[1])
        # Short-circuit the y case as an optimization
        return 2 if v1 == 2 else max(v1, expr_user_value(expr[2]))

    if expr[0] is K.NOT:
        return 2 - expr_user_value(expr[1])

    # Relation
    #
    # Implements <, <=, >, >= comparisons as well. These were added to
    # kconfig in 31847b67 (kconfig: allow use of relations other than
    # (in)equality).

    rel, v1, v2 = expr

    # If both operands are strings...
    if v1.orig_type is K.STRING and v2.orig_type is K.STRING:
        # ...then compare them lexicographically
        comp = K._strcmp(v1.str_value, v2.str_value)
    else:
        # Otherwise, try to compare them as numbers
        try:
            comp = K._sym_to_num(v1) - K._sym_to_num(v2)
        except ValueError:
            # Fall back on a lexicographic comparison if the operands don't
            # parse as numbers
            comp = K._strcmp(v1.str_value, v2.str_value)

    return 2*(comp == 0 if rel is K.EQUAL else
              comp != 0 if rel is K.UNEQUAL else
              comp <  0 if rel is K.LESS else
              comp <= 0 if rel is K.LESS_EQUAL else
              comp >  0 if rel is K.GREATER else
              comp >= 0)


def dep_satisfied(sym, dep):
    sym_value = user_value(sym)
    dep_value = user_value(dep)

    if sym.type == K.BOOL:
        return sym_value == 0 or dep_value != 0
    else:
        return sym_value <= dep_value


def deps_met(sym):
    value = user_value(sym)
    if value > 0:
        if sym.type == K.BOOL:
            return value == 0 or expr_user_value(sym.direct_dep) != 0
        else:
            return value <= expr_user_value(sym.direct_dep)

    return True


def filter_unmet_deps(symbols):
    return [x for x in symbols if x.orig_type in K._BOOL_TRISTATE and not deps_met(x)]


def warn_unmet_deps(kconf):
    syms = filter_unmet_deps(kconf.syms.values())

    for sym in syms:
        eprint(f"warning: Unmet dependency for symbol {sym.name}")

    return len(syms) > 0


def try_fix_deps(symbols):
    while symbols:
        check = set()

        for sym in symbols:
            if deps_met(sym):
                continue

            deps = K.split_expr(sym.direct_dep, K.AND)
            for dep in deps:
                if isinstance(dep, tuple):
                    if dep[0] == K.EQUAL and (dep[1].is_constant or dep[2].is_constant):
                        if dep[1].is_constant:
                            tgt, src = dep[2], dep[1]
                        else:
                            tgt, src = dep[1], dep[2]

                        v_old = K.TRI_TO_STR[user_value(tgt)]
                        v_new = K.TRI_TO_STR[user_value(src)]
                        eprint(f"warning: Changing symbol value: {tgt.name} {v_old} -> {v_new}")

                        tgt.set_value(user_value(src))
                        check.add(tgt)

                        continue

                    if dep[0] == K.UNEQUAL and (dep[1].is_constant or dep[2].is_constant):
                        if dep[1].is_constant:
                            tgt, src = dep[2], dep[1]
                        else:
                            tgt, src = dep[1], dep[2]

                        values = set([1, 2])    # assume that 'n' is not an option
                        values.remove(user_value(src))
                        value = (*values,)[0]

                        v_old = K.TRI_TO_STR[user_value(tgt)]
                        v_new = K.TRI_TO_STR[value]
                        eprint(f"warning: Changing symbol value: {tgt.name} {v_old} -> {v_new}")

                        tgt.set_value(value)
                        check.add(tgt)

                        continue

                    eprint("error: Cannot fix dependencies: Complex dependency statements not suppoted")
                    eprint(f"       On symbol: {sym.name}")
                    exit(1)

                if dep_satisfied(sym, dep):
                    continue

                if dep.orig_type not in K._BOOL_TRISTATE:
                    eprint("error: Cannot fix dependencies: Non-boolean and non-tristate dependency")

                if dep.orig_type == K.TRISTATE and sym.orig_type == K.TRISTATE:
                    value = user_value(sym)         # copy tristate value
                elif dep.orig_type == K.TRISTATE:
                    value = 1                       # prefer M for bool dependents
                else:
                    value = 2                       # set bool dependency to Y

                if value > user_value(dep):
                    v_old = K.TRI_TO_STR[user_value(dep)]
                    v_new = K.TRI_TO_STR[value]
                    eprint(f"warning: Changing symbol value: {dep.name} {v_old} -> {v_new}")

                    dep.set_value(value)
                    check.add(dep)

        symbols = check


def main():
    C.init()

    parser = build_cli()
    args = parser.parse_args()

    # prepare environment for parsing
    os.environ['KERNELVERSION'] = '<kver>'      # this is just a dummy
    os.environ['CC'] = 'gcc'
    os.environ['HOSTCC'] = 'gcc'
    os.environ['HOSTCXX'] = 'g++'
    os.environ['ARCH'] = 'x86'
    os.environ['SRCARCH'] = 'x86'
    os.environ['srctree'] = str(args.srctree)

    # load Kconfig structure (ignore warnings here)
    print_banner(f"Loading '{args.srctree / 'Kconfig'}'")
    kconf = K.Kconfig(args.srctree / 'Kconfig', warn=False)
    kconf.warn = True

    # merge config files
    for c in args.conf:
        print_banner(f"Loading '{c}'")
        kconf.load_config(c, replace=False)

    # check dependencies
    print_banner(f"Checking dependencies")
    unmet = filter_unmet_deps(kconf.syms.values())
    for sym in unmet:
        eprint(f"warning: Unmet dependency for symbol {sym.name}")

    if args.try_fix_deps and unmet:
        print_banner(f"Attempting to fix dependencies")
        try_fix_deps(unmet)

        if(filter_unmet_deps(kconf.syms.values())):
            eprint(f"error: Could not fix dependencies, aborting")
            exit(1)

    elif unmet:
        eprint(f"warning: Unmet dependencies need to be fixed manually")

    # write config
    print_banner(f"Generating '{args.output}'")
    kconf.write_config(args.output)


if __name__ == '__main__':
    main()
