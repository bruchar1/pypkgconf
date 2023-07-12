from pypkgconf import PkgconfClient

import os
import pickle
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
    
    def test_modversion_nonexistent(self):
        client = PkgconfClient()
        self.assertIsNone(client.modversion('nonexistent'))

    def test_with_paths(self):
        env = os.environ.copy()
        del os.environ['PKG_CONFIG_PATH']
        datapath = os.path.join(os.path.dirname(__file__), 'data')
        client = PkgconfClient(with_paths=[datapath])
        
        self.assertEqual('1.0.0', client.modversion('simple'))
        os.environ = env

    def test_pickle(self):
        client = PkgconfClient()
        self.assertEqual('1.0.0', client.modversion('simple'))

        d = pickle.dumps(client)

        c2 = pickle.loads(d)

        self.assertEqual('1.0.0', c2.modversion('simple'))

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

    def test_circular_requires(self):
        client = PkgconfClient()

        self.assertEqual('-lcirc3 -lcirc2 -lcirc1', client.libs('circular-1'))
    
    def test_dependencies_shared(self):
        datapath = os.path.join(os.path.dirname(__file__), 'data', 'dependencies')
        client = PkgconfClient(with_paths=[datapath])

        self.assertEqual('-lb_dep_c -la_dep_c -lc_dep', client.libs(['a_dep_c', 'b_dep_c']))
        self.assertEqual('-lb_dep_c -la_dep_c -lc_dep', client.libs(['c_dep', 'a_dep_c', 'b_dep_c']))
        self.assertEqual('-lb_dep_c -la_dep_c -lc_dep', client.libs(['a_dep_c', 'c_dep', 'b_dep_c']))
        self.assertEqual('-lb_dep_c -la_dep_c -lc_dep', client.libs(['a_dep_c', 'b_dep_c', 'c_dep']))

    def test_dependencies_redundancy(self):
        datapath = os.path.join(os.path.dirname(__file__), 'data', 'dependencies')
        client = PkgconfClient(with_paths=[datapath])

        self.assertEqual('-lb_dep_c -lc_dep -la_dep_c', client.libs(['a_dep_c', 'a_dep_c', 'b_dep_c']))
        self.assertEqual('-la_dep_c -lb_dep_c -lc_dep', client.libs(['b_dep_c', 'a_dep_c', 'b_dep_c']))

    def test_dependencies_diamond(self):
        datapath = os.path.join(os.path.dirname(__file__), 'data', 'dependencies')
        client = PkgconfClient(with_paths=[datapath])

        self.assertEqual('-le_dep_g_f -ld_dep_e_f -lg_dep -lf_dep_g', client.libs('d_dep_e_f'))
        self.assertEqual('-le_dep_g_f -ld_dep_f_e -lg_dep -lf_dep_g', client.libs('d_dep_f_e'))

    def test_dependencies_nested(self):
        datapath = os.path.join(os.path.dirname(__file__), 'data', 'dependencies')
        client = PkgconfClient(with_paths=[datapath])

        self.assertEqual('-li_dep_k_j -lh_dep_k_i_j -lj_dep_k -lk_dep', client.libs('h_dep_k_i_j'))
        self.assertEqual('-lh_dep_k_i_j -lj_dep_k -li_dep_k_j -lk_dep', client.libs(['h_dep_k_i_j', 'i_dep_k_j']))
        self.assertEqual('-lh_dep_k_i_j -li_dep_k_j -lj_dep_k -lk_dep', client.libs(['k_dep', 'j_dep_k', 'i_dep_k_j', 'h_dep_k_i_j']))


if __name__ == '__main__':
    unittest.main()
