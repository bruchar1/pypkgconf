from pypkgconf import PkgconfClient

import unittest


class TestLibPkgConf(unittest.TestCase):

    def test_simple_modversion(self):
        client = PkgconfClient()

        self.assertEqual('1.0.0', client.modversion('simple'))

    def test_simple_cflags(self):
        client = PkgconfClient()

        self.assertEqual('-I/usr/include', client.cflags('simple'))

    def test_simple_libs(self):
        client = PkgconfClient()

        self.assertEqual('-lsimple', client.libs('simple'))

    def test_simple_variable(self):
        client = PkgconfClient()

        self.assertEqual('/usr', client.variable('simple', 'prefix'))

    def test_simple_variable_define(self):
        client = PkgconfClient()

        self.assertEqual('/opt/lib', client.variable('simple', 'libdir', define_variable='prefix=/opt'))

if __name__ == '__main__':
    unittest.main()
    