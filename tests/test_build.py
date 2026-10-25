"""Build and use a copy of compiler/ without the rest of the repository."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StandaloneCompiler(unittest.TestCase):
    def test_standalone_build_and_custom_toolchain_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compiler = root / 'compiler source'
            output = root / 'compiler output'
            shutil.copytree(ROOT / 'compiler', compiler,
                            ignore=shutil.ignore_patterns('build', '.deps'))
            env = dict(os.environ, CVCC_DEPS_DIR=str((ROOT / 'compiler/.deps').resolve()),
                       CVCC_BUILD_DIR='compiler output')
            result = subprocess.run([compiler / 'build.sh'], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            executable = output / 'cvcc'
            source = root / 'main.cvc'
            source.write_text('void setup(){} void loop(){waitVBlank();}')
            result = subprocess.run([executable, source], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('call cvcc_wait', result.stdout)
            self.assertFalse((root / 'ide').exists())
            self.assertFalse((root / 'runtime').exists())
            # The standalone executable is also a supported input to ROM builds.
            result = subprocess.run([sys.executable, ROOT / 'toolchain/build_rom.py',
                                     source, '--frontend', executable, '--out-dir', root / 'rom'],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'rom/program.sg').stat().st_size, 8192)

    def test_missing_dependencies_explain_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, CVCC_DEPS_DIR=directory,
                       CVCC_BUILD_DIR=str(Path(directory) / 'output'))
            result = subprocess.run([ROOT / 'compiler/build.sh'], cwd=directory, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing dependency source:', result.stderr)
            self.assertIn('CVCC_DEPS_DIR', result.stderr)
            self.assertFalse((Path(directory) / 'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
