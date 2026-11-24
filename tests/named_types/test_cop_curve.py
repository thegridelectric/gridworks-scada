"""cop.curve 001: the twin agrees with the snapshot on the word's example
and refuses the axiom's violation."""

from gwsproto.named_types import CopCurve
from tests.named_types.sema_oracle import assert_conforms, assert_refused

EXAMPLE = {
    "Intercept": 2.731,
    "LwtMinusOatCoeff": -0.007403,
    "TypeName": "cop.curve",
    "Version": "001",
}


def test_example_conforms() -> None:
    assert_conforms(CopCurve.model_validate(EXAMPLE))


def test_cop_curve_axiom_1_non_positive_lift_coefficient() -> None:
    d = dict(EXAMPLE, LwtMinusOatCoeff=0.001)
    assert_refused(CopCurve, d, match="Axiom 1 \\(NonPositiveLiftCoefficient\\)")
