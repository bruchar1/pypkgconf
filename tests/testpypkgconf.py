from pypkgconf import PkgconfClient

import os
import unittest


class TestLibPkgConf(unittest.TestCase):

    def setUp(self):
        os.environ['PKG_CONFIG_SYSTEM_INCLUDE_PATH'] = '/usr/include'
        os.environ['PKG_CONFIG_SYSTEM_LIBRARY_PATH'] = os.pathsep.join(('/usr/lib', '/lib'))

    def test_version(self):
        client = PkgconfClient()

        version = tuple(map(int, client.version().split('.')))
        self.assertGreaterEqual(version, (1, 9, 5))

    def test_simple_modversion(self):
        client = PkgconfClient()

        self.assertEqual('1.0.0', client.modversion('simple'))

    def test_simple_cflags(self):
        client = PkgconfClient()

        self.assertEqual('-I/usr/include', client.cflags('simple', keep_system=True))

    def test_simple_libs(self):
        client = PkgconfClient()

        self.assertEqual('-lsimple', client.libs('simple'))

    def test_simple_libs_static(self):
        client = PkgconfClient()

        with client.options_ctx(static=True):
            self.assertEqual('-lsimple -lm', client.libs('simple'))

    def test_simple_variable(self):
        client = PkgconfClient()

        self.assertEqual('/usr', client.variable('simple', 'prefix'))

    def test_simple_variable_define(self):
        client = PkgconfClient()

        with client.variables_ctx(prefix='/opt'):
            self.assertEqual('/opt/lib', client.variable('simple', 'libdir'))

    def test_simple_list_variables(self):
        client = PkgconfClient()

        self.assertEqual({
            'exec_prefix',
            'includedir',
            'libdir',
            'pcfiledir',
            'prefix',
        }, set(client.list_variables('simple')))

    def test_list_no_variables(self):
        client = PkgconfClient()

        self.assertEqual({
            'pcfiledir',
        }, set(client.list_variables('no-variables')))

    def test_libs_other_only_ldpath(self):
        client = PkgconfClient()

        self.assertEqual('-L/other/lib', client.libs('other', only_ldpath=True))
    
    def test_libs_other_only_libname(self):
        client = PkgconfClient()

        self.assertEqual('-lother', client.libs('other', only_libname=True))

    def test_libs_other_only_other(self):
        client = PkgconfClient()

        self.assertEqual('-Wl,--as-needed', client.libs('other', only_other=True))

    def test_libs_other_only_ldpath_only_libname(self):
        client = PkgconfClient()

        self.assertEqual('-L/other/lib -lother', client.libs('other', only_ldpath=True, only_libname=True))

    def test_libs_other_only_ldpath_only_other(self):
        client = PkgconfClient()

        self.assertEqual('-L/other/lib -Wl,--as-needed', client.libs('other', only_ldpath=True, only_other=True))

    def test_libs_other_only_libname_only_other(self):
        client = PkgconfClient()

        self.assertEqual('-Wl,--as-needed -lother', client.libs('other', only_libname=True, only_other=True))

    def test_libs_other_only_libname_only_ldpath_only_other(self):
        client = PkgconfClient()

        self.assertEqual('-L/other/lib -Wl,--as-needed -lother', client.libs('other', only_libname=True, only_ldpath=True, only_other=True))

    def test_cflags_other_only_I(self):
        client = PkgconfClient()

        self.assertEqual('-I/other/include', client.cflags('other', only_I=True))

    def test_cflags_other_only_other(self):
        client = PkgconfClient()

        self.assertEqual('-DOTHER', client.cflags('other', only_other=True))

    def test_cflags_other_only_I_only_other(self):
        client = PkgconfClient()

        self.assertEqual('-I/other/include -DOTHER', client.cflags('other', only_I=True, only_other=True))

    def test_no_system_cflags(self):
        client = PkgconfClient()

        self.assertEqual('', client.cflags('system'))

    def test_no_system_libs(self):
        client = PkgconfClient()

        self.assertEqual('-lsystem', client.libs('system'))

    def test_system_cflags(self):
        client = PkgconfClient()

        self.assertEqual('-I/usr/include', client.cflags('system', keep_system=True))

    def test_system_libs(self):
        client = PkgconfClient()

        self.assertEqual('-L/usr/lib -lsystem', client.libs('system', keep_system=True))

if __name__ == '__main__':
    unittest.main()
