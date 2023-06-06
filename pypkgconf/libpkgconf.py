from __future__ import annotations

from pypkgconf._libpkgconf import ffi, lib

import logging
import os
import typing as T


@ffi.def_extern()
def error_handler(msg: str, client: PkgconfClient, data: T.Any) -> bool:
    """ This is a Python callback to handle errors """
    logging.error(msg.rstrip())
    return True


class PkgconfClient:

    def __init__(self):
        self._personality = lib.pkgconf_cross_personality_default()
        self._client = lib.pkgconf_client_new(lib.error_handler, ffi.NULL, self._personality)

        self._packages = {}

        want_client_flags = 0
        lib.pkgconf_client_set_flags(self._client, want_client_flags)

        # at this point, want_client_flags should be set, so build the dir list
        lib.pkgconf_client_dir_list_build(self._client, self._personality)
    
    def __del__(self):
        for pkg in self._packages.values():
            lib.pkgconf_pkg_unref(self._client, pkg)

        lib.pkgconf_cross_personality_deinit(self._personality)
        lib.pkgconf_client_free(self._client)

    def _get(self, package: str, define_variable: T.Optional[str]=None):
        key = (package, define_variable)
        if key not in self._packages:
            if define_variable:
                lib.pkgconf_tuple_define_global(self._client, define_variable.encode())

            pkg = lib.pkgconf_pkg_find(self._client, package.encode())
            if pkg is None:
                lib.pkgconf_error(self._client, f"Package '{package}' was not found\n")
            self._packages[key] = pkg

            if define_variable:
                lib.pkgconf_tuple_free_global(self._client)

        return self._packages[key]

    def modversion(self, package: str) -> T.Optional[str]:
        pkg = self._get(package)
        if pkg is None:
            return None
        return ffi.string(pkg.version).decode()

    def cflags(self, package: str, allow_system_cflags = None) -> T.Optional[str]:
        pkg = self._get(package)
        if pkg is None:
            return None

        unfiltered_list = ffi.new('pkgconf_list_t *')

        try:
            eflag = lib.pkgconf_pkg_cflags(self._client, pkg, unfiltered_list, 2)
            if eflag != 0:
                return None
            
            # TODO: apply filter...

            result_str = lib.pkgconf_fragment_render(unfiltered_list, False, ffi.NULL)
            return ffi.string(result_str).decode()
        
        finally:
            lib.pkgconf_fragment_free(unfiltered_list)

    def libs(self, package: str, static: bool = False, allow_system_libs = None) -> T.Optional[str]:
        pkg = self._get(package)
        if pkg is None:
            return None

        unfiltered_list = ffi.new('pkgconf_list_t *')

        try:
            eflag = lib.pkgconf_pkg_libs(self._client, pkg, unfiltered_list, 2)
            if eflag != 0:
                return None
            
            # TODO: apply filter...

            result_str = lib.pkgconf_fragment_render(unfiltered_list, False, ffi.NULL)
            return ffi.string(result_str).decode()
        
        finally:
            lib.pkgconf_fragment_free(unfiltered_list)

    def variable(self, package: str, variable_nane: str, define_variable: T.Optional[str]=None) -> T.Optional[str]:
        pkg = self._get(package, define_variable)
        if pkg is None:
            return None
        
        var = lib.pkgconf_tuple_find(self._client, ffi.addressof(pkg.vars), variable_nane.encode())
        if var == ffi.NULL:
            return None
        
        return ffi.string(var).decode()
    
