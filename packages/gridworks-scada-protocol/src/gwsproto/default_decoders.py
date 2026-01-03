from gwsproto.decoders import CacDecoder, ComponentDecoder

__all__ = [
    "default_cac_decoder",
    "default_component_decoder",
]


def _get_default_cac_decoder() -> CacDecoder:
    import gwproto.named_types.cacs

    return CacDecoder(
        model_name="DefaultCacDecoder",
        modules=[gwproto.named_types.cacs],
    )


def _get_default_component_decoder() -> ComponentDecoder:
    import gwsproto.named_types.components

    return ComponentDecoder(
        model_name="DefaultComponentDecoder",
        modules=[gwsproto.named_types.components],
    )


default_cac_decoder = _get_default_cac_decoder()
default_component_decoder = _get_default_component_decoder()
