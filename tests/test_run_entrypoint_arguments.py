"""Reject incomplete lab options before environment setup or resource creation."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ENTRYPOINT = Path(__file__).resolve().parents[1] / "run.sh"


class LabArgumentTests(unittest.TestCase):
    def test_incomplete_options_exit_without_hanging(self):
        entrypoints = (["bash", str(ENTRYPOINT), "lab"],
                       ["bash", str(ENTRYPOINT.parent / "artifact/run.sh")])
        for command in entrypoints:
            for option in ("--campaign", "--run-root"):
                for suffix in ([], [""], ["--campaign", "0.c0026"]):
                    with self.subTest(command=command, option=option, suffix=suffix):
                        result = subprocess.run(
                            [*command, option, *suffix],
                            capture_output=True, text=True, timeout=3,
                        )
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertIn(option + " requires a value", result.stderr)

    def test_complete_options_preserve_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(ENTRYPOINT, root / "run.sh")
            (root / "scripts").mkdir()
            shutil.copyfile(
                ENTRYPOINT.parent / "scripts/shell_lifecycle.sh",
                root / "scripts/shell_lifecycle.sh",
            )
            (root / "scripts/python_env.sh").write_text(
                "sticks_resolve_python() { printf '%s\\n' /usr/bin/true; }\n"
            )
            (root / "artifact").mkdir()
            (root / "artifact/run.sh").write_text("printf '%s\\0' \"$@\"\n")
            run_root = str(root / "evidence with spaces")
            result = subprocess.run(
                ["bash", str(root / "run.sh"), "lab", "--campaign", "0.c0026",
                 "--run-root", run_root], capture_output=True, timeout=3,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.split(b"\0")[:-1], [
                b"--campaign", b"0.c0026", b"--run-root", run_root.encode()])


if __name__ == "__main__":
    unittest.main()
