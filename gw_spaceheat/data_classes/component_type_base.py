""" ComponentType Base Class Definition """

from abc import ABC, abstractproperty
from typing import Optional

from data_classes.mixin import StreamlinedSerializerMixin


class ComponentTypeBase(ABC, StreamlinedSerializerMixin):
    by_id = {}
    
    base_props = []
    base_props.append('value')
    base_props.append('expected_startup_seconds')
    base_props.append('expected_shutdown_seconds')
    base_props.append('is_resistive_load')
    base_props.append('display_name')
    base_props.append('component_sub_category_value')

    def __new__(cls, value, *args, **kwargs):
        try:
            return cls.by_id[value]
        except KeyError:
            instance = super().__new__(cls)
            cls.by_id[value] = instance
            return instance

    def __init__(self,
                 value: Optional[str] = None,
                 expected_startup_seconds: Optional[float] = None,
                 expected_shutdown_seconds: Optional[float] = None,
                 is_resistive_load: Optional[bool] = None,
                 display_name: Optional[str] = None,
                 component_sub_category_value: Optional[str] = None):
        self.value = value
        if expected_startup_seconds:
            self.expected_startup_seconds = float(expected_startup_seconds)
        else:
            self.expected_startup_seconds = None
        if expected_shutdown_seconds:
            self.expected_shutdown_seconds = float(expected_shutdown_seconds)
        else:
            self.expected_shutdown_seconds = None
        self.is_resistive_load = is_resistive_load
        self.display_name = display_name
        self.component_sub_category_value = component_sub_category_value

    """ Derived attributes """

    @abstractproperty
    def component_category(self):
        """From Airtable Axioms:  """
        raise NotImplementedError
