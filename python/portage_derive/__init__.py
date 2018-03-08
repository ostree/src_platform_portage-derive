#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright © 2015-2018 ANSSI. All Rights Reserved.
#
# Helpers to automate Portage tree management.
#
# Author: Mickaël Salaün <clipos@ssi.gouv.fr>

import logging
import os
import portage
import shutil

PORTAGE_PROFILES = ("hardened/linux/x86", "hardened/x86/2.6", "default/linux/x86", "default-linux/x86")
PORTAGE_ARCH = "amd64"

DRY_RUN = False

def get_atom_dependencies(atom, db=None, all_useflags=False):
    if db is None:
        db = portage.db[portage.root]["porttree"].dbapi
    if atom != "":
        return portage.dep.use_reduce(portage.dep.paren_enclose(db.aux_get(atom, ["DEPEND", "RDEPEND"])), matchall=all_useflags)
    return []

class PkgFound(str):
    pass

class PkgNotFound(str):
    pass

def get_all_dependencies(depends, db=None, pkgs=None, all_useflags=False, exclude=set()):
    if db is None:
        db = portage.db[portage.root]["porttree"].dbapi
    if pkgs is None:
        pkgs = PackageDb(None)
    for dep in depends:
        if isinstance(dep, list):
            for sub in get_all_dependencies(dep, db, pkgs, all_useflags, exclude):
                yield sub
            continue
        if dep.startswith("!"):
            continue
        if dep == u"||":
            continue
        pkgs_deps = pkgs.match(dep)
        if pkgs_deps:
            # Assume we have all the dependencies (i.e. use flags) for our packages
            exclude.update([PkgFound(p) for p in pkgs_deps])
            continue
        atom = db.xmatch("bestmatch-visible", dep)
        if atom == "":
            atom = PkgNotFound(dep)
        else:
            atom = PkgFound(atom)
        if atom in exclude:
            continue
        exclude.add(atom)
        yield atom
        if isinstance(atom, PkgNotFound):
            continue
        for sub in get_all_dependencies(get_atom_dependencies(atom, db, all_useflags), db, pkgs, all_useflags, exclude):
            yield sub

def get_db(portdir):
    init_portage(portdir)
    return portage.db[portage.root]["porttree"].dbapi

# To call before any portage use, if needed
def init_portage(portage_path, profile=None):
    portage_path = os.path.abspath(portage_path)
    if profile is None:
        for p in PORTAGE_PROFILES:
            profile_path = os.path.join(portage_path, "profiles", p)
            if os.path.exists(profile_path):
                profile = p
                break
        if profile is None:
            raise Exception("Could not find a profile in {}".format(portage_path))
    else:
        profile_path = os.path.join(portage_path, "profiles", profile)
        if not os.path.exists(profile_path):
            raise Exception("Profile directory does not exist: {}".format(profile_path))
    os.environ["PORTDIR"] = portage_path
    portage.const.PROFILE_PATH = profile_path
    # PORTAGE_CONFIGROOT: Virtual root to find configuration (e.g. etc/make.conf)
    #os.environ["PORTAGE_CONFIGROOT"] = WORKDIR

def set_stable(db, is_stable):
    db.settings.unlock()
    db.settings["ACCEPT_KEYWORDS"] = "{}{}".format({True:"", False:"~"}[is_stable], PORTAGE_ARCH);
    db.settings.lock()

def assert_beneath_portdir(src):
    # $PORTDIR is set by init_portage()
    portdir = os.environ["PORTDIR"]
    root = "{}/".format(portdir)
    if len(portdir) > 1 and os.path.commonprefix([root, src]) == root:
        return
    raise Exception("Attempt to modify a file outside the Portage tree: {}", src)

def fs_move(common_dir, src, dst):
    src = os.path.join(common_dir, src)
    dst = os.path.join(common_dir, dst)
    assert_beneath_portdir(src)
    assert_beneath_portdir(dst)
    logging.debug("moving {} -> {}".format(src, dst))
    if not DRY_RUN:
        shutil.move(src, dst)

def fs_symlink(common_dir, src, dst):
    src = os.path.join(common_dir, src)
    assert_beneath_portdir(src)
    if dst != os.path.basename(dst):
        raise Exception("Attempt to symlink to an absolute path: {}", dst)
    logging.debug("linking {} -> {}".format(src, dst))
    if not DRY_RUN:
        os.symlink(dst, src)

def fs_remove(src):
    assert_beneath_portdir(src)
    logging.debug("removing file {}".format(src))
    if not DRY_RUN:
        os.unlink(src)

def fs_remove_tree(src):
    assert_beneath_portdir(src)
    logging.debug("removing tree {}".format(src))
    if not DRY_RUN:
        shutil.rmtree(src)

def do_symlinks(db, slots, atom, atom_dir):
    logging.debug("working in {}".format(atom_dir))
    # for each slot, get the best match according to the profile (i.e. newer stable, or newer unstable if the profile whitelist this atom)
    visibles = set()
    for slot in slots:
        cpv = db.xmatch("bestmatch-visible", "{}:{}".format(atom, slot))
        slot, keywords = db.aux_get(cpv, ["SLOT", "KEYWORDS"])
        visibles.add(os.path.basename(cpv))
        # may use isStable() from portage/package/ebuild/_config/KeywordsManager.py
        logging.debug("found {} slot:{}".format(cpv, slot))
    for root, dirs, files in os.walk(atom_dir):
        for name in files:
            head, tail = os.path.splitext(name)
            # remove invisible ebuilds
            if tail == ".ebuild" and head not in visibles:
                fs_remove(os.path.join(atom_dir, name))

    # It's more common to remove an old package version than the more
    # up-to-date (i.e. we don't downgrade packages but can keep and old version
    # for compatibility): decrease order to keep the most up to date at first.
    for i, pvr in enumerate(sorted([portage.pkgsplit(x) for x in visibles], portage.pkgcmp, reverse=True)):
        if pvr[2] == "r0":
            name = "-".join(pvr[:-1])
        else:
            name = "-".join(pvr)
        src = "{}.ebuild".format(name)

        # ignore already equalized ebuilds
        if os.path.islink(os.path.join(atom_dir, src)):
            continue

        # the equalized name should not end with ".ebuild"
        # (cf. dbapi/porttree.py:cp_list "Invalid ebuild name" and
        # versions.py:catpkgsplit)
        dst = ".{}.ebuild.{}".format(pvr[0], i)
        fs_move(atom_dir, src, dst)
        fs_symlink(atom_dir, src, dst)

# @db: get_db(PORTDIR)
def equalize(db):
    # atoms = db.cp_all(categories=["www-client"], sort=False)
    atoms = db.cp_all()
    atom_nb = len(atoms)
    for i, atom in enumerate(atoms, start=1):
        # find all the slots for this atom
        slots = set()
        for cpv in db.match(atom):
            slots.add(db.aux_get(cpv, ["SLOT"])[0])
        logging.debug("")
        logging.info("equalizing {}/{} {}".format(i, atom_nb, atom))
        # check if some slots are visible to the current profile
        if len(slots) != 0:
            # get atom's directory from the last cpv (assume there is only one portdir, no overlay)
            do_symlinks(db, slots, atom, os.path.dirname(db.findname2(cpv)[0]))
            continue
        # remove files which are not usable with the current profile
        cpv = db.xmatch("match-all", atom)[0]
        atom_dir = os.path.dirname(db.findname2(cpv)[0])
        fs_remove_tree(atom_dir)
