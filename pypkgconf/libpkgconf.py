from __future__ import annotations

from . import flags
from ._libpkgconf import ffi, lib

from dataclasses import dataclass, field, fields
from contextlib import contextmanager
import logging
import os
import sys
import typing as T


logger = logging.getLogger(__name__)

@ffi.def_extern()
def error_handler(msg: str, client, data) -> bool:
    """ This is a Python callback to handle errors """
    log_level = ffi.from_handle(data)

    logger.log(log_level, ffi.string(msg).decode(errors='replace').rstrip())
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

    define_prefix: bool = True if sys.platform == 'win32' else False
    skip_root_virtual: bool = False
    static: bool = False

    debug: bool = False
    maximum_traverse_depth = 2000

    def __post_init__(self):
        if os.environ.get('PKG_CONFIG_DONT_DEFINE_PREFIX'):
            self.define_prefix = False

        if os.environ.get('PKG_CONFIG_EARLY_TRACE'):
            self.debug = True
        
        mtd = os.environ.get("PKG_CONFIG_MAXIMUM_TRAVERSE_DEPTH")
        if mtd is not None:
            self.maximum_traverse_depth = int(mtd)

    @property
    def flags(self) -> int:
        f = flags.PKGF_NONE

        if self.define_prefix:
            f |= flags.PKGF_REDEFINE_PREFIX
        if self.skip_root_virtual:
            f |= flags.PKGF_SKIP_ROOT_VIRTUAL
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

    def __init__(self, define_variables: T.Optional[T.Dict[str, str]] = None,
                 with_paths: T.Optional[T.List[str]] = None, **kwargs):
        self._personality = lib.pkgconf_cross_personality_default()
        if with_paths:
            self.__add_paths(with_paths)

        self._options = PkgconfFlags(**kwargs)
        self.__init_client(self._options.debug)

        self._variables = {}
        if define_variables:
            self.define_variables(**define_variables)

        lib.pkgconf_client_set_flags(self._client, self._options.flags)

        # at this point, want_client_flags should be set, so build the dir list
        lib.pkgconf_client_dir_list_build(self._client, self._personality)

    def __init_client(self, debug: bool):
        self.__debug_level = ffi.new_handle(logging.DEBUG)
        self.__error_level = ffi.new_handle(logging.ERROR)

        self._client = lib.pkgconf_client_new(lib.error_handler, self.__error_level, self._personality)
        if debug:
            lib.pkgconf_client_set_trace_handler(self._client, lib.error_handler, self.__debug_level)

    def __add_paths(self, paths: T.List[str]):
        dir_list = ffi.new('pkgconf_list_t *')
        for p in paths:
            lib.pkgconf_path_add(p.encode(), dir_list, True)
        lib.pkgconf_path_copy_list(ffi.addressof(self._personality.dir_list), dir_list)
        lib.pkgconf_path_free(dir_list)

    def __getstate__(self) -> object:
        d = self.__dict__.copy()

        d['_paths'] = []
        for p in NodeIter(self._personality.dir_list, 'pkgconf_path_t *'):
            d['_paths'].append(ffi.string(p.path).decode())

        sysroot = lib.pkgconf_client_get_sysroot_dir(self._client)
        if sysroot != ffi.NULL:
            d['_sysroot'] = ffi.string()
        del d['_client']
        del d['_personality']
        del d['_PkgconfClient__error_level']
        del d['_PkgconfClient__debug_level']
        return d

    def __setstate__(self, d: T.Dict) -> None:
        self._personality = lib.pkgconf_cross_personality_default()
        self.__add_paths(d['_paths'])
        del d['_paths']

        sysroot = d.get('_sysroot')
        if sysroot:
            del d['_sysroot']

        self.__dict__.update(d)
        self.__init_client(self._options.debug)

        if sysroot:
            self.set_sysroot(sysroot)

        if self._variables:
            self.define_variables(**self._variables)

        lib.pkgconf_client_set_flags(self._client, self._options.flags)
        lib.pkgconf_client_dir_list_build(self._client, self._personality)
    
    def __del__(self):
        if hasattr(self, '_personality'):
            lib.pkgconf_cross_personality_deinit(self._personality)
        
        if hasattr(self, '_client'):
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
    
    def set_sysroot(self, sysroot: str) -> None:
        lib.pkgconf_client_set_sysroot_dir(sysroot.encode())
        
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
    
    @contextmanager
    def _solve(self, packages: T.List[str], maximum_traverse_depth=None):
        lib.pkgconf_cache_free(self._client)

        world = ffi.new('pkgconf_pkg_t *')
        id = ffi.new('char[]', 'virtual:world'.encode())
        world.id = id
        realname = ffi.new('char[]', 'virtual world package'.encode())
        world.realname = realname
        world.flags = flags.PROPF_STATIC | flags.PROPF_VIRTUAL
    
        pkgq = ffi.new("pkgconf_list_t *")
        for p in packages:
            if not p:
                continue
            lib.pkgconf_queue_push(pkgq, p.encode())

        if maximum_traverse_depth is None:
            maximum_traverse_depth = self._options.maximum_traverse_depth
        r = lib.pkgconf_queue_solve(self._client, pkgq, world, maximum_traverse_depth)
        
        yield world if r else None

        lib.pkgconf_solution_free(self._client, world)
        lib.pkgconf_queue_free(pkgq)

    def _iter_world(self, packages: T.List[str], maximum_traverse_depth=None):
        with self._solve(packages, maximum_traverse_depth) as world:
            if world:
                for pkg_dep in NodeIter(world.required, 'pkgconf_dependency_t *'):
                    yield pkg_dep.match

    def modversion(self, package: str) -> T.Optional[str]:
        version = []
        
        for pkg in self._iter_world([package], maximum_traverse_depth=1):
            if pkg.version != ffi.NULL:
                version.append(ffi.string(pkg.version).decode())
        
        return "\n".join(version) if version else None

    def cflags(self, packages: T.Union[str, T.List[str]], **kwargs) -> T.Optional[str]:
        if isinstance(packages, str):
            packages = [packages]
        with self._solve(packages) as world:
            if not world:
                return None
            
            unfiltered_list = ffi.new('pkgconf_list_t *')
            filtered_list = ffi.new('pkgconf_list_t *')

            try:
                eflag = lib.pkgconf_pkg_cflags(self._client, world, unfiltered_list, 2)
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

    def libs(self, packages: T.Union[str, T.List[str]], **kwargs) -> T.Optional[str]:
        if isinstance(packages, str):
            packages = [packages]
        with self._solve(packages) as world:
            if not world:
                return None

            unfiltered_list = ffi.new('pkgconf_list_t *')
            filtered_list = ffi.new('pkgconf_list_t *')

            try:
                eflag = lib.pkgconf_pkg_libs(self._client, world, unfiltered_list, 2)
                if eflag != flags.ERRF_OK:
                    return None
                
                kwargs.setdefault('keep_system', os.environ.get('PKG_CONFIG_ALLOW_SYSTEM_LIBS', False))
                data = ffi.new_handle(LibsFilterData(**kwargs))
                lib.pkgconf_fragment_filter(self._client, filtered_list, unfiltered_list, lib.filter_libs, data)

                result_str = lib.pkgconf_fragment_render(filtered_list, True, ffi.NULL)
                return ffi.string(result_str).decode()
            
            finally:
                lib.pkgconf_fragment_free(filtered_list)
                lib.pkgconf_fragment_free(unfiltered_list)

    def variable(self, package: str, variable_name: str) -> T.Optional[str]:
        found_vars = []

        with self.options_ctx(skip_root_virtual=True):
            for pkg in self._iter_world([package], maximum_traverse_depth=1):
                var = lib.pkgconf_tuple_find(self._client, ffi.addressof(pkg.vars), variable_name.encode())
                if var != ffi.NULL:
                    found_vars.append(ffi.string(var).decode())
        
        return ' '.join(found_vars) if found_vars else None

    def list_variables(self, package: str) -> T.Optional[T.List[str]]:
        variables = []
        for pkg in self._iter_world([package], maximum_traverse_depth=1): 
            for variable in NodeIter(pkg.vars):
                variables.append(ffi.string(variable.key).decode())
        return variables or None
