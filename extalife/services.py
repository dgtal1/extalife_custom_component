""" definition of all services for this integration """
from homeassistant.helpers.typing import HomeAssistantType
from .const import DOMAIN, DATA_CONTROLLER
from .pyextalife import ExtaLifeAPI

# services
SVC_RESTART = "restart"  # restart controller


class ExtaLifeServices:
    """ handle Exta Life services """

    def __init__(self, hass: HomeAssistantType):
        self._hass = hass

    @property
    def controller(self) -> ExtaLifeAPI:
        """ return the controller object """
        return self._hass.data[DOMAIN][DATA_CONTROLLER]

    def register_services(self):
        """ register all Exta Life integration services """
        self._hass.services.register(DOMAIN, SVC_RESTART, self._handle_restart)

    def _handle_restart(self, call):
        """ service: extalife.restart """
        self.controller.restart()
