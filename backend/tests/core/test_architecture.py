import subprocess


def test_core_import_contracts():
    result = subprocess.run(["uv", "run", "lint-imports"], capture_output=True, text=True, cwd=".")
    assert result.returncode == 0, result.stdout + result.stderr
