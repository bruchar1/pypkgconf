project('pypkgconf',
    'c',
    license: 'Apache-2.0',
    meson_version: '>=1.0',
    version: '0.1.0',
    default_options: [
        'buildtype=release',
    ])

pkgconf_proj = subproject('pkgconf', default_options: ['default_library=static'])
libpkgconf_dep = dependency('libpkgconf')

pymod = import('python')
py = pymod.find_installation(modules: ['cffi'], pure: true)

libpkgconf_c = '_libpkgconf.c'

build_libpkgconf_py = configure_file(
    input: 'build_libpkgconf.py.in',
    output: 'build_libpkgconf.py',
    configuration: {
        'SOURCE_FILE': libpkgconf_c,
    }
)

c_bindings = custom_target(
    'libpkgconf_c',
    command: [py, build_libpkgconf_py],
    output: [libpkgconf_c],
)

subdir('pypkgconf')

testenv = environment(
    {
        'PKG_CONFIG_PATH': meson.current_source_dir() / 'tests' / 'data',
        'PYTHONPATH': meson.current_build_dir(),
    }
)

test('testpypkgconf',
    py,
    args: [meson.current_source_dir() / 'tests' / 'testpypkgconf.py'],
    env: testenv,
)
