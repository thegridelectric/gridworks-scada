from gwsproto.decoders import ComponentDecoder, DeviceTypeDecoder

__all__ = [
    "default_component_decoder",
    "default_device_type_decoder",
]


def _get_default_device_type_decoder() -> DeviceTypeDecoder:
    import gwsproto.named_types.device_types

    return DeviceTypeDecoder(
        model_name="DefaultDeviceTypeDecoder",
        modules=[gwsproto.named_types.device_types],
    )


def _get_default_component_decoder() -> ComponentDecoder:
    import gwsproto.named_types.components

    return ComponentDecoder(
        model_name="DefaultComponentDecoder",
        modules=[gwsproto.named_types.components],
    )


default_device_type_decoder = _get_default_device_type_decoder()
default_component_decoder = _get_default_component_decoder()
