#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright © 2015-2018 ANSSI. All Rights Reserved.
#
# Tool to automate Portage tree management.
#
# Author: Mickaël Salaün <clipos@ssi.gouv.fr>

import argparse
import logging

from . import get_db, equalize, DRY_RUN

def _print_atom(db, atom):
    slot, keywords = db.aux_get(atom, ["SLOT", "KEYWORDS"])
    print("{} slot:{} keywords:{}".format(atom, slot, keywords))

def main_list(args):
    db = get_db(args.portdir, args.profile)
    for pkg in args.packages:
        # "match-all" "bestmatch-visible" "match-visible" "minimum-all" "list-visible"
        atoms = db.xmatch("list-visible", pkg)
        if atoms == "":
            print("Failed to find a package named \"{}\"".format(pkg))
            return 1
        if isinstance(atoms, list):
            for atom in atoms:
                _print_atom(db, atom)
        else:
            _print_atom(db, atoms)

def main_shell(args):
    from IPython.terminal.embed import InteractiveShellEmbed
    import portage
    db = get_db(args.portdir, args.profile)
    banner = "Use the \"db\" object to explore the portage database."
    ipshell = InteractiveShellEmbed(banner1=banner)
    ipshell()

def main_equalize(args):
    db = get_db(args.portdir, args.profile)
    equalize(db, atoms=args.packages)

def main():
    parser = argparse.ArgumentParser(description="Tool to automate Portage tree management.")

    parser.add_argument("-d", "--portdir", help="Portage tree directory", required=True)
    parser.add_argument("-n", "--dry-run", help="do not perform any action on the file system", action="store_true")
    parser.add_argument("-p", "--profile", help="Portage profile", required=True)
    parser.add_argument("-q", "--quiet", help="do not output anything except errors", action="store_true")
    parser.add_argument("-v", "--verbose", help="print debug informations", action="store_true")
    subparser = parser.add_subparsers()

    parser_list = subparser.add_parser("list", help="list visible packages")
    parser_list.add_argument("packages", help="packages or atom names", nargs="+")
    parser_list.set_defaults(func=main_list)

    parser_shell = subparser.add_parser("shell", help="launch an IPython shell to hack with the Portage tree database")
    parser_shell.set_defaults(func=main_shell)

    parser_equalize = subparser.add_parser("equalize", help="equalize a Portage tree (make it Git-friendly to ease merges with stable ebuild names and their symlinks); operate on the whole tree if no package/atom is given; otherwise operate on given packages/atoms only")
    parser_equalize.add_argument("packages", help="packages or atoms", nargs="*", default=[])
    parser_equalize.set_defaults(func=main_equalize)

    args = parser.parse_args()
    if not args.quiet:
        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
    DRY_RUN = args.dry_run
    args.func(args)

if __name__ == '__main__':
    main()