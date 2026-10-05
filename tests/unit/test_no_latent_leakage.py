"""The generator's latent variables must be unreachable from model code.

`is_churner`, `churn_start_day` and the rest exist only to build the world.
Feeding any of them to XGBoost would replace the research question -- can risk
be inferred from observable payment behaviour? -- with a lookup of the answer
key. The rule is enforced structurally: no module that trains, evaluates,
explains or serves may import the generator at all.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Modules that may not reach the generator. Checked as globs so files added
# later are covered without anyone remembering to update this list.
MODEL_SIDE_GLOBS = (
    "ml/features/*.py",
    "ml/baselines/*.py",
    "ml/train.py",
    "ml/evaluate.py",
    "ml/explain.py",
    "ml/inference.py",
    "ml/splits.py",
    "app/**/*.py",
)

FORBIDDEN_NAMES = frozenset(
    {
        "is_churner",
        "churn_start_day",
        "churn_mode",
        "churn_halflife_days",
        "friction_rises_before_churn",
        "base_rate_per_day",
        "base_failure_p",
        "amount_trend",
        "merchant_profiles",
        "MerchantProfile",
    }
)


def model_side_files() -> list[Path]:
    found: list[Path] = []
    for pattern in MODEL_SIDE_GLOBS:
        found.extend(p for p in ROOT.glob(pattern) if p.is_file())
    return sorted(set(found))


def test_there_is_something_to_check() -> None:
    """Guard against the globs silently matching nothing."""
    assert len(model_side_files()) >= 3


@pytest.mark.parametrize("path", model_side_files(), ids=lambda p: p.name)
def test_model_side_module_does_not_import_the_generator(path: Path) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert "ml.synthetic" not in name, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", model_side_files(), ids=lambda p: p.name)
def test_model_side_module_never_names_a_latent_variable(path: Path) -> None:
    source = path.read_text()
    # Whole words only: `churn_mode` is a substring of the legitimate
    # `churn_model`, and a substring match would forbid the model itself.
    offenders = sorted(
        name
        for name in FORBIDDEN_NAMES
        if re.search(rf"\b{re.escape(name)}\b", source)
    )
    assert not offenders, f"{path.name} mentions latent variables: {offenders}"
