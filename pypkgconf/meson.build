# This subdir is only to ensure the extension module is generated
# inside a directory whose name matches the final installation dir
# to allow in-tree testing

fs = import('fs')
fs.copyfile('__init__.py')
fs.copyfile('libpkgconf.py')

py.extension_module(
    '_libpkgconf',
    [c_bindings],
    dependencies: [libpkgconf_dep],
    c_args: ['-DPKGCONFIG_IS_STATIC'],
    install: true,
    subdir: meson.project_name()
)

py.install_sources(
    [
        '__init__.py',
        'libpkgconf.py',
    ],
    subdir: meson.project_name()
)
