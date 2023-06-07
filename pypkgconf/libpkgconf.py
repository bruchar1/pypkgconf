from __future__ import annotations

from . import flags
from ._libpkgconf import ffi, lib

from dataclasses import dataclass, field, fields
import logging
import os
import typing as T


@ffi.def_extern()
def error_handler(msg: str, client, data) -> bool:
    """ This is a Python callback to handle errors """
    logging.error(msg.rstrip())
    return True


@dataclass(kw_only=True)
class FilterData:
    keep_system: bool = False
    fragment_filter: T.Optional[str] = None

    def __post_init__(self):
        self._known_flags = {f.metadata.get('type'): f.name for f in fields(self) if 'type' in f.metadata}
        self._has_filter = any(getattr(self, f) for f in self._known_flags.values())
        self._other_name = self._known_flags.pop('*', None)

    def filter(self, type: str) -> bool:
        if self.fragment_filter and type not in self.fragment_filter:
            return False
        
        if type in self._known_flags:
            if getattr(self, self._known_flags[type]):
                return True

        elif self._other_name and getattr(self, self._other_name):
            return True
        
        return not self._has_filter
        
@dataclass(kw_only=True)
class CflagFilterData(FilterData):
    only_I: bool = field(default=False, metadata={'type': 'I'})
    only_other: bool = field(default=False, metadata={'type': '*'})


@dataclass(kw_only=True)
class LibsFilterData(FilterData):
    only_ldpath: bool = field(default=False, metadata={'type': 'L'})
    only_libname: bool = field(default=False, metadata={'type': 'l'})
    only_other: bool = field(default=False, metadata={'type': '*'})


def _filter_func(client, frag, flags: FilterData):
    if not flags.keep_system and lib.pkgconf_fragment_has_system_dir(client, frag):
        return False
    
    return flags.filter(frag.type.decode())


@ffi.def_extern()
def filter_cflags(client, frag, data) -> bool:
    flags: CflagFilterData = ffi.from_handle(data)

    return _filter_func(client, frag, flags)


@ffi.def_extern()
def filter_libs(client, frag, data) -> bool:
    flags: LibsFilterData = ffi.from_handle(data)

    return _filter_func(client, frag, flags)


class PkgconfClient:

    def __init__(self):
        self._personality = lib.pkgconf_cross_personality_default()
        self._client = lib.pkgconf_client_new(lib.error_handler, ffi.NULL, self._personality)

        self._packages = {}

        want_client_flags = flags.PKGF_NONE
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

    def cflags(self, package: str, **kwargs) -> T.Optional[str]:
        pkg = self._get(package)
        if pkg is None:
            return None

        unfiltered_list = ffi.new('pkgconf_list_t *')
        filtered_list = ffi.new('pkgconf_list_t *')

        try:
            eflag = lib.pkgconf_pkg_cflags(self._client, pkg, unfiltered_list, 2)
            if eflag != flags.ERRF_OK:
                return None
            
            kwargs.setdefault('keep_system', os.environ.get('PKG_CONFIG_ALLOW_SYSTEM_CFLAGS', False))
            data = ffi.new_handle(CflagFilterData(**kwargs))
            lib.pkgconf_fragment_filter(self._client, filtered_list, unfiltered_list, lib.filter_cflags, data)

            result_str = lib.pkgconf_fragment_render(filtered_list, False, ffi.NULL)
            return ffi.string(result_str).decode()
        
        finally:
            lib.pkgconf_fragment_free(filtered_list)
            lib.pkgconf_fragment_free(unfiltered_list)

    def libs(self, package: str, static: bool = False, **kwargs) -> T.Optional[str]:
        pkg = self._get(package)
        if pkg is None:
            return None

        unfiltered_list = ffi.new('pkgconf_list_t *')
        filtered_list = ffi.new('pkgconf_list_t *')

        try:
            eflag = lib.pkgconf_pkg_libs(self._client, pkg, unfiltered_list, 2)
            if eflag != flags.ERRF_OK:
                return None
            
            kwargs.setdefault('keep_system', os.environ.get('PKG_CONFIG_ALLOW_SYSTEM_LIBS', False))
            data = ffi.new_handle(LibsFilterData(**kwargs))
            lib.pkgconf_fragment_filter(self._client, filtered_list, unfiltered_list, lib.filter_libs, data)

            result_str = lib.pkgconf_fragment_render(filtered_list, False, ffi.NULL)
            return ffi.string(result_str).decode()
        
        finally:
            lib.pkgconf_fragment_free(filtered_list)
            lib.pkgconf_fragment_free(unfiltered_list)

    def variable(self, package: str, variable_name: str, define_variable: T.Optional[str]=None) -> T.Optional[str]:
        pkg = self._get(package, define_variable)
        if pkg is None:
            return None
        
        var = lib.pkgconf_tuple_find(self._client, ffi.addressof(pkg.vars), variable_name.encode())
        if var == ffi.NULL:
            return None
        
        return ffi.string(var).decode()
