from __future__ import annotations

from . import flags
from ._libpkgconf import ffi, lib

from dataclasses import dataclass, field, fields
from contextlib import contextmanager
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


class NodeIter:

    def __init__(self, pkgconf_list, ctype: str = "pkgconf_tuple_t*"):
        self._cur = pkgconf_list.head
        self._ctype = ctype

    def __iter__(self):
        return self

    def __next__(self):
        if self._cur == ffi.NULL:
            raise StopIteration
        data = self._cur.data
        self._cur = self._cur.next
        return ffi.cast(self._ctype, data)


@dataclass(kw_only=True)
class PkgconfFlags:

    static: bool = False

    @property
    def flags(self) -> int:
        f = flags.PKGF_NONE

        if self.static:
            f |= flags.PKGF_SEARCH_PRIVATE | flags.PKGF_MERGE_PRIVATE_FRAGMENT
        
        return f
    
    def update(self, **options) -> bool:
        changed = False
        for key, value in options.items():
            if getattr(self, key) != value:
                changed = True
                setattr(self, key, value)
        return changed


class PkgconfClient:

    def __init__(self, define_variables: T.Optional[T.Dict[str, str]] = None, **kwargs):
        self._personality = lib.pkgconf_cross_personality_default()
        self._client = lib.pkgconf_client_new(lib.error_handler, ffi.NULL, self._personality)

        self._packages = {}
        self._variables = {}
        if define_variables:
            self.define_variables(**define_variables)

        self._options = PkgconfFlags(**kwargs)
        lib.pkgconf_client_set_flags(self._client, self._options.flags)

        # at this point, want_client_flags should be set, so build the dir list
        lib.pkgconf_client_dir_list_build(self._client, self._personality)
    
    def __del__(self):
        for pkg in self._packages.values():
            lib.pkgconf_pkg_unref(self._client, pkg)

        lib.pkgconf_cross_personality_deinit(self._personality)
        lib.pkgconf_client_free(self._client)

    def version(self) -> T.Optional[str]:
        return self.modversion('pkgconf')

    def define_variables(self, **variables) -> None:
        self._variables.update(variables)
        for key, value in variables.items():
            lib.pkgconf_tuple_define_global(self._client, f'{key}={value}'.encode())

    def set_options(self, **options) -> bool:
        if self._options.update(**options):
            lib.pkgconf_client_set_flags(self._client, self._options.flags)
            lib.pkgconf_cache_free(self._client)
            return True
        return False
        
    @contextmanager
    def variables_ctx(self, **kwargs):
        current_variables = self._variables.copy()
        self.define_variables(**kwargs)

        yield

        lib.pkgconf_tuple_free_global(self._client)
        self._variables = {}
        self.define_variables(**current_variables)

    @contextmanager
    def options_ctx(self, **kwargs):
        current_flags = self._options.flags
        modified = self.set_options(**kwargs)

        yield

        if modified:
            lib.pkgconf_client_set_flags(self._client, current_flags)
            lib.pkgconf_cache_free(self._client)

    def _hash(self) -> int:
        """Return a hash for the current state"""
        return hash(tuple(sorted(self._variables.items())))

    def _get(self, package: str):
        key = (package, self._hash())
        if key not in self._packages:
            pkg = lib.pkgconf_pkg_find(self._client, package.encode())
            if pkg is None:
                lib.pkgconf_error(self._client, f"Package '{package}' was not found\n")
            self._packages[key] = pkg

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

    def variable(self, package: str, variable_name: str) -> T.Optional[str]:
        pkg = self._get(package)
        if pkg is None:
            return None
        
        var = lib.pkgconf_tuple_find(self._client, ffi.addressof(pkg.vars), variable_name.encode())
        if var == ffi.NULL:
            return None
        
        return ffi.string(var).decode()

    def list_variables(self, package: str) -> T.Optional[T.List[str]]:
        pkg = self._get(package)
        if pkg is None:
            return None
        
        variables = []
        for variable in NodeIter(pkg.vars):
            variables.append(ffi.string(variable.key).decode())
        return variables
