# This subdir is only to ensure the extension module is generated
# inside a directory whose name matches the final installation dir
# to allow in-tree testing

python_files = ['__init__.py', 'flags.py', 'libpkgconf.py']

fs = import('fs')
foreach f: python_files
    fs.copyfile(f)
endforeach

py.extension_module(
    '_libpkgconf',
    [c_bindings],
    dependencies: [libpkgconf_dep],
    c_args: [
        '-DPKGCONFIG_IS_STATIC',  # workaround until the dep contains it
        '-D_CFFI_NO_LIMITED_API',  # workaround until meson support it
    ],
    install: true,
    subdir: meson.project_name(),
)

py.install_sources(
    python_files,
    subdir: meson.project_name()
)
