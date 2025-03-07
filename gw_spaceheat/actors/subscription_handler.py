from pydantic import BaseModel
from gwproto.property_format import SpaceheatName

class StateMachineSubscription(BaseModel):
    subscriber_name: SpaceheatName
    publisher_name: SpaceheatName

class ChannelSubscription(BaseModel):
    subscriber_name: SpaceheatName
    channel_name: SpaceheatName