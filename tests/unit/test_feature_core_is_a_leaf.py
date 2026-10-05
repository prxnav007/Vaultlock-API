"""The feature core must stay importable by the request path.

If pandas, SQLAlchemy or the offline stack ever creep into
`ml.features.definitions`, the serving image grows the whole training toolchain and
the cheap no-database leakage tests stop being cheap. Checked in a subprocess
because the rest of the suite has already imported those packages.
"""
import subprocess
import sys

FORBIDDEN = ("pandas", "sqlalchemy", "sklearn", "shap", "xgboost")


def test_windows_module_imports_nothing_heavy() -> None:
    probe = (
        "import sys; import ml.features.definitions; "
        f"leaked = [m for m in {FORBIDDEN!r} if m in sys.modules]; "
        "print(leaked); sys.exit(1 if leaked else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, f"leaked imports: {result.stdout.strip()}"
