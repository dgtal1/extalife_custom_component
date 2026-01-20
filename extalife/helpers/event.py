import logging
from datetime import datetime, timedelta

from homeassistant.const import (
    CONF_TYPE
)
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_EXTALIFE_EVENT_UNIQUE_ID,
    CONF_PROCESSOR_EVENT_STAT_NOTIFICATION,
    CONF_PROCESSOR_EVENT_UNKNOWN,
    EVENT_TIMESTAMP,
    EVENT_DATA,
    TRIGGER_BUTTON_LONG_PRESS,
    TRIGGER_BUTTON_DOUBLE_CLICK,
    TRIGGER_BUTTON_DOWN,
    TRIGGER_BUTTON_UP,
    TRIGGER_BUTTON_SINGLE_CLICK,
    TRIGGER_SUBTYPE_BUTTON_TEMPLATE,
    TRIGGER_BUTTON_TRIPLE_CLICK,
    TRIGGER_SUBTYPE, TRIGGER_TYPE
)
from .core import Core
from .device import Device
from ..pyextalife import DEVICE_ARR_ALL_TRANSMITTER

_LOGGER = logging.getLogger(__name__)


class ExtaLifeEventProcessor:
    """ Processes status notification events from controller """
    def __init__(self, device: Device):
        self._device = device

    @staticmethod
    def factory(device: Device) -> 'ExtaLifeTransmitterEventProcessor':
        if device.type in DEVICE_ARR_ALL_TRANSMITTER:
            return ExtaLifeTransmitterEventProcessor(device)

    def process_event(self, data: dict, event_type=CONF_PROCESSOR_EVENT_UNKNOWN):
        if event_type == CONF_PROCESSOR_EVENT_UNKNOWN:
            raise NotImplementedError()


class ExtaLifeTransmitterEventProcessor(ExtaLifeEventProcessor):
    def __init__(self, device: Device):
        super().__init__(device)
        self._device = device
        self._event_data = dict()
        self._event_window = dict()

    def check_supported(self, event_type):
        if event_type != CONF_PROCESSOR_EVENT_STAT_NOTIFICATION:
            raise NotImplementedError()

    @staticmethod
    def encapsulate(event_data) -> dict:
        event = dict()
        event[EVENT_TIMESTAMP] = datetime.now()
        event[EVENT_DATA] = event_data
        return event

    def process_event(self, data, event_type=CONF_PROCESSOR_EVENT_UNKNOWN):
        _LOGGER.debug(f"process_event data: {data}")
        super().process_event(data, event_type)
        self.check_supported(event_type)

        hass = Core.get_hass()

        # assumption: data fields in JSON protocol: button & state
        button = data.get('button')
        state = data.get('state')

        event_data = {
            CONF_EXTALIFE_EVENT_UNIQUE_ID: self._device.event.unique_id,
            TRIGGER_SUBTYPE: TRIGGER_SUBTYPE_BUTTON_TEMPLATE.format(button)
            }

        if state == 1:
            event_data[CONF_TYPE] = TRIGGER_BUTTON_DOWN
        else:
            event_data[CONF_TYPE] = TRIGGER_BUTTON_UP

        # noinspection PyUnusedLocal
        def _timeout_callback(now=None):
            # assumption: state = 0 or 1
            # assumption: variable 'button' = value at the moment of callback registration
            _LOGGER.debug(f"_timeout_callback.self._event_window[button]: {self._event_window[button]}")
            remove_listener()
            value = ''
            for event in self._event_window[button]:
                value = value + str(event[EVENT_DATA]['state'])

            _LOGGER.debug(f"_timeout_callback.value: {value}")

            event_data[TRIGGER_SUBTYPE] = TRIGGER_SUBTYPE_BUTTON_TEMPLATE.format(button)
            if value == '1':  # long press
                event_data[CONF_TYPE] = TRIGGER_BUTTON_LONG_PRESS

            elif value == '10':  # single click
                event_data[CONF_TYPE] = TRIGGER_BUTTON_SINGLE_CLICK

            elif value == '1010':  # double click
                event_data[CONF_TYPE] = TRIGGER_BUTTON_DOUBLE_CLICK

            elif value == '101010':  # triple click
                event_data[CONF_TYPE] = TRIGGER_BUTTON_TRIPLE_CLICK

            if event_data.get(TRIGGER_TYPE):
                # raise event to HA event bus
                _LOGGER.debug(f"_timeout_callback.async_fire event_data: {event_data}")
                hass.bus.async_fire(self._device.event.event, event_data=event_data)

            # reset time window for button
            self._event_window[button] = None

        if self._event_window.get(button) is None:
            # maximum triple click
            remove_listener = async_track_time_interval(hass, _timeout_callback, timedelta(milliseconds=600))

        self._event_window.setdefault(button, []).append(self.encapsulate(data))

        if event_data.get(TRIGGER_TYPE):
            _LOGGER.debug(f"process_event.async_fire event_data: {event_data}")
            hass.bus.async_fire(self._device.event.event, event_data=event_data)
