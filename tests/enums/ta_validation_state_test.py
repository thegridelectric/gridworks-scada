from gwsproto.enums import TaValidationState


def test_ta_validation_state() -> None:
    assert set(TaValidationState.values()) == {
        "UnValidated",
        "ValidatedRealAssetAndGps",
        "ValidatedRealAssetIncorrectGps",
        "ValidatedSimulatedAsset",
    }

    assert TaValidationState.default() == TaValidationState.UnValidated
    assert TaValidationState.enum_name() == "ta.validation.state"
    assert TaValidationState.enum_version() == "000"
