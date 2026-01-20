"""Config flow to configure Exta Life component."""
from __future__ import annotations

import logging
from typing import (
    Any,
)

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import (
    AbortFlow,
)
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .helpers.const import (
    DOMAIN,
    CONF_CONTROLLER_IP,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_RECV_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VER_INTERVAL,
    DEFAULT_RECV_TIMEOUT,
    OPTIONS_LIGHT,
    OPTIONS_GENERAL,
    OPTIONS_COVER,
    OPTIONS_LIGHT_ICONS_LIST,
    OPTIONS_COVER_INVERTED_CONTROL,
    OPTIONS_GENERAL_POLL_INTERVAL,
    OPTIONS_GENERAL_VER_INTERVAL,
    OPTIONS_GENERAL_DISABLE_NOT_RESPONDING
)
from .helpers.core import (
    Core,
)
from .pyextalife import (
    ExtaLifeAPI,
    ExtaLifeCmdError,
    ExtaLifeConnError,
    ExtaLifeCmdErrorCode,
    ExtaLifeConnParams,
    DEVICE_ICON_ARR_LIGHT
)

_LOGGER = logging.getLogger( __name__ )


def get_default_options() -> dict[ str, Any ]:
    options = { }
    options.setdefault( OPTIONS_GENERAL, {
        OPTIONS_GENERAL_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        OPTIONS_GENERAL_VER_INTERVAL: DEFAULT_VER_INTERVAL,
        OPTIONS_GENERAL_DISABLE_NOT_RESPONDING: True
    } )
    options.setdefault( OPTIONS_LIGHT, {
        OPTIONS_LIGHT_ICONS_LIST: DEVICE_ICON_ARR_LIGHT
    } )
    options.setdefault( OPTIONS_COVER, {
        OPTIONS_COVER_INVERTED_CONTROL: False
    } )
    return options.copy()


#  @config_entries.HANDLERS.register(DOMAIN)

class ExtaLifeFlowHandler( ConfigFlow, domain=DOMAIN ):
    """ExtaLife config flow."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__( self ) -> None:
        """Initialize Exta Life configuration flow."""
        self._entry: ConfigEntry | None = None
        self._user_input: dict[ str, Any ] = { }
        self._import_data: dict[ str, Any ] | None = None
        self._controller_addr: str = ""
        self._controller_title: str = ""
        self._controller_name: str = 'EFC-01'
        self._controller_mac: str = ""
        self._username: str = ""
        self._password: str = ""
        self._recv_timeout: int = DEFAULT_RECV_TIMEOUT

    async def _async_exta_life_check( self ) -> str | None:
        """Test Exta Life connection params"""

        # Test connection on this IP - get instance: this will already try to connect and logon
        controller = ExtaLifeAPI( self.hass.loop )

        controller_host, controller_port = ExtaLifeConnParams.get_host_and_port( self._controller_addr )

        # noinspection PyBroadException
        try:
            await controller.async_connect( self._username, self._password, controller_host, controller_port,
                                            conn_timeout=5.0, recv_timeout=self._recv_timeout )
            self._controller_name = controller.name
            self._controller_mac = controller.mac

            return None

        except ExtaLifeConnError:
            return "extalife_no_connection"

        except ExtaLifeCmdError as err:
            if err.code == ExtaLifeCmdErrorCode.INVALID_LOG_PASS:
                return "extalife_invalid_cred"
            else:
                return "extalife_login_failed"

        except Exception:  # pylint: disable=broad-except
            return "extalife_unk_error"

        finally:
            await controller.async_disconnect()  # if we won't do this - it will run forever and ping

    @staticmethod
    @callback
    def async_get_options_flow( config_entry: ConfigEntry ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ExtaLifeOptionsFlowHandler( config_entry )

    async def async_step_user( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return await self.async_step_init( user_input=None )
        return self.async_show_form( step_id="confirm" )

    async def async_step_confirm( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Handle flow start."""
        errors: dict[ str, str ] = { }
        if user_input is not None:
            return await self.async_step_init( user_input=None )
        return self.async_show_form( step_id="confirm", errors=errors )

    async def async_step_init( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Handle flow start. This step can be called either from GUI from step confirm or by step_import
        during entry migration"""

        errors: dict[ str, str ] = { }
        controller_addr: str = self._import_data.get( CONF_CONTROLLER_IP ) if self._import_data else self._controller_addr
        description_placeholders: dict[ str, str ] = { "error_info": "" }
        if user_input is None or (self._import_data is not None and self._import_data.get( CONF_CONTROLLER_IP ) is None):
            controller_addr = await self.hass.async_add_executor_job( ExtaLifeAPI.discover_controller, **{ } )

        if user_input is not None or self._import_data is not None:

            controller_addr = user_input[ CONF_CONTROLLER_IP ] if user_input else self._import_data[ CONF_CONTROLLER_IP ]
            # za-dev-proxy.it.quay.pl:30400
            self._controller_addr = controller_addr

            username: str = user_input[ CONF_USERNAME ] if user_input else self._import_data[ CONF_USERNAME ]
            self._username = username

            password: str = user_input[ CONF_PASSWORD ] if user_input else self._import_data[ CONF_PASSWORD ]
            self._password = password

            recv_timeout: int = user_input[ CONF_RECV_TIMEOUT ] if user_input else self._import_data[ CONF_RECV_TIMEOUT ]
            self._recv_timeout = recv_timeout

            # Test connection on this IP - get instance: this will already try to connect and logon
            controller = ExtaLifeAPI( self.hass.loop )

            controller_host, controller_port = ExtaLifeConnParams.get_host_and_port( controller_addr )

            try:
                await controller.async_connect( username, password, controller_host, controller_port, conn_timeout=5.0, recv_timeout=self._recv_timeout )
                self._controller_name = controller.name

                self._user_input = user_input

                # populate optional IP address if not provided in config already
                if self._import_data:
                    self._import_data[ CONF_CONTROLLER_IP ] = controller_addr

                # check if connection to this controller is already configured (based on MAC address)
                # for controllers accessed through internet this may lead to misidentification due to MAC
                # being MAC of a router, not a real EFC-01 MAC. For connections through VPN this should be ok
                await self.async_set_unique_id( controller.mac )

                self._abort_if_unique_id_configured()

                return await self.async_step_title()

            except AbortFlow as err:
                _LOGGER.error( f"Unable to continue EFC-01 controller setup, {err}" )
                errors = { "base": "extalife_flow_error" }

            except ExtaLifeConnError as err:
                _LOGGER.error( f"Cannot connect to your EFC-01 controller on IP {controller_addr}, {err}" )
                errors = { "base": "extalife_no_connection" }

            except ExtaLifeCmdError as err:
                if err.code == ExtaLifeCmdErrorCode.INVALID_LOG_PASS:
                    _LOGGER.error( f"Cannot login into your EFC-01 controller. Invalid user or password" )
                    errors = { "base": "extalife_invalid_cred" }
                else:
                    _LOGGER.error( f"Cannot login into your EFC-01 controller, {err}" )
                    errors = { "base": "extalife_login_failed" }

            finally:
                await controller.async_disconnect()  # if we won't do this - it will run forever and ping

        recv_timeout_selector = vol.All(
                NumberSelector(
                        NumberSelectorConfig(
                                mode=NumberSelectorMode.BOX, min=5, max=45, step=1, unit_of_measurement="seconds"
                        )
                ),
                vol.Coerce( int )
        )

        return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                        {
                            vol.Required( CONF_CONTROLLER_IP, default=controller_addr ): str,
                            vol.Required( CONF_RECV_TIMEOUT, default=self._recv_timeout ): recv_timeout_selector,
                            vol.Required( CONF_USERNAME, default=self._username ): str,
                            vol.Required( CONF_PASSWORD, default=self._password ): str,
                        }
                ),
                errors=errors,
                description_placeholders=description_placeholders,
        )

    async def async_step_reauth( self, entry_data: dict[ str, Any ] ) -> ConfigFlowResult:
        """Handle flow upon an API authentication error."""
        self._entry = self.hass.config_entries.async_get_entry( self.context[ "entry_id" ] )
        self._controller_title = self._entry.title
        self._controller_addr = entry_data[ CONF_CONTROLLER_IP ]
        self._username = entry_data[ CONF_USERNAME ]
        self._password = entry_data[ CONF_PASSWORD ]
        self._recv_timeout = entry_data[ CONF_RECV_TIMEOUT ]

        return await self.async_step_reauth_confirm()

    def _show_setup_form_reauth_confirm(
            self, user_input: dict[ str, Any ], errors: dict[ str, str ] | None = None
    ) -> ConfigFlowResult:
        """Show the reauth form to the user."""
        default_username: str = user_input.get( CONF_USERNAME, "" )
        default_password: str = user_input.get( CONF_PASSWORD, "" )
        return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                        {
                            vol.Required( CONF_USERNAME, default=default_username ): str,
                            vol.Required( CONF_PASSWORD, default=default_password ): str,
                        }
                ),
                description_placeholders={ "title": self._controller_title, "host": self._controller_addr },
                errors=errors or { }
        )

    async def async_step_reauth_confirm( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""

        if user_input is None:
            return self._show_setup_form_reauth_confirm( { CONF_USERNAME: self._username, CONF_PASSWORD: self._password } )

        self._username = user_input[ CONF_USERNAME ]
        self._password = user_input[ CONF_PASSWORD ]

        if error := await self._async_exta_life_check():
            return self._show_setup_form_reauth_confirm( user_input, errors={ "base": error } )

        assert isinstance( self._entry, ConfigEntry )
        self.hass.config_entries.async_update_entry(
                self._entry,
                data={
                    CONF_CONTROLLER_IP: self._controller_addr,
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_RECV_TIMEOUT: self._recv_timeout,
                },
        )
        await self.hass.config_entries.async_reload( self._entry.entry_id )
        return self.async_abort( reason="reauth_successful" )

    async def async_step_reconfigure(
            self, user_input: dict[ str, Any ] | None = None
    ) -> ConfigFlowResult:
        """reconfigure existing integration entry"""

        self._entry = self.hass.config_entries.async_get_entry( self.context[ "entry_id" ] )
        self._controller_title = self._entry.title
        self._controller_addr = self._entry.data.get( CONF_CONTROLLER_IP, "" )
        self._username = self._entry.data.get( CONF_USERNAME, "" )
        self._password = self._entry.data.get( CONF_PASSWORD, "" )
        self._recv_timeout = self._entry.data.get( CONF_RECV_TIMEOUT, DEFAULT_RECV_TIMEOUT)

        return await self.async_step_reconfigure_confirm( user_input )

    def _show_setup_form_reconfigure_confirm(
            self, user_input: dict[ str, Any ], errors: dict[ str, str ] | None = None
    ) -> ConfigFlowResult:

        default_controller_ip = user_input.get( CONF_CONTROLLER_IP, "" )
        default_username = user_input.get( CONF_USERNAME, "" )
        default_password = user_input.get( CONF_PASSWORD, "" )
        default_recv_timeout = user_input.get( CONF_RECV_TIMEOUT, DEFAULT_RECV_TIMEOUT )

        recv_timeout_selector = vol.All(
                NumberSelector(
                        NumberSelectorConfig(
                                mode=NumberSelectorMode.BOX, min=5, max=45, step=1, unit_of_measurement="seconds"
                        )
                ),
                vol.Coerce( int )
        )

        return self.async_show_form(
                step_id="reconfigure_confirm",
                data_schema=vol.Schema(
                        {
                            vol.Optional( CONF_CONTROLLER_IP, default=default_controller_ip ): str,
                            vol.Required( CONF_RECV_TIMEOUT, default=default_recv_timeout ): recv_timeout_selector,
                            vol.Required( CONF_USERNAME, default=default_username, description={ "suggested_value": "root" } ): str,
                            vol.Required( CONF_PASSWORD, default=default_password ): str
                        }
                ),
                description_placeholders={ "title": self._controller_title, "host": self._controller_addr },
                errors=errors or { }
        )

    async def async_step_reconfigure_confirm(
            self, user_input: dict[ str, Any ] | None = None
    ) -> ConfigFlowResult:

        if user_input is None:
            return self._show_setup_form_reconfigure_confirm(
                    {
                        CONF_CONTROLLER_IP: self._controller_addr,
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                        CONF_RECV_TIMEOUT: self._recv_timeout,
                    }
            )

        self._controller_addr = user_input[ CONF_CONTROLLER_IP ]
        self._username = user_input[ CONF_USERNAME ]
        self._password = user_input[ CONF_PASSWORD ]
        self._recv_timeout = user_input[ CONF_RECV_TIMEOUT ]

        core = Core.get( self.context[ "entry_id" ] )

        was_connected = core.api.is_connected
        if was_connected:
            await core.api.async_disconnect()

        if error := await self._async_exta_life_check():
            if was_connected:
                await core.api.async_reconnect()
            return self._show_setup_form_reconfigure_confirm( user_input, errors={ "base": error } )

        assert isinstance( self._entry, ConfigEntry )
        self.hass.config_entries.async_update_entry(
                self._entry,
                data={
                    CONF_CONTROLLER_IP: self._controller_addr,
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_RECV_TIMEOUT: self._recv_timeout,
                },
        )
        await self.hass.config_entries.async_reload( self._entry.entry_id )

        return self.async_abort( reason="reconfigure_successful" )

    async def async_step_title( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Ask for additional title for Integrations screen. To differentiate in GUI between multiple config entries"""
        if user_input is not None or self._import_data is not None:
            title = user_input.get( "title" ) if user_input else self._controller_name
            data = self._user_input if self._user_input else self._import_data
            return self.async_create_entry( title=title, data=data )

        return self.async_show_form(
                step_id="title",
                data_schema=vol.Schema(
                        { vol.Optional( "title", default=self._controller_name if self._controller_name else '' ): str }
                ),
                errors={ },
                description_placeholders={ },
        )

    async def async_step_import( self, import_data: dict[ str, Any ] ) -> ConfigFlowResult:
        """ This step can only be called from component async_setup() and will migrate configuration.yaml entry
        into a Config Entry """
        self._import_data: dict[ str, Any ] = import_data
        self._import_data.pop( "options" )  # options should not be part of config_entry.data

        # initiate the flow as from GUI, call step `init`
        return await self.async_step_init()


class ExtaLifeOptionsFlowHandler( OptionsFlowWithConfigEntry ):
    """Handle Exta Life options."""

    def __init__( self, config_entry: ConfigEntry ) -> None:
        """Initialize Exta Life options flow."""
        super().__init__( config_entry )
        self._controller_title = config_entry.title
        self._controller_addr = config_entry.data.get( CONF_CONTROLLER_IP, "" )
        self._step_no = 1
        self._step_total = 3

    def _get_description_placeholders( self ) -> dict[ str, any ]:
        """Build common description placeholders for options flow forms"""
        return {
            "title": self._controller_title,
            "host": self._controller_addr,
            "step_no": f"{self._step_no}",
            "step_total": f"{self._step_total}",
        }

    async def async_step_init( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Manage the Exta Life options."""
        return await self.async_step_general( user_input )

    async def async_step_user( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        """Manage the Exta Life options."""
        return await self.async_step_general( user_input )

    async def async_step_general( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        if user_input is not None:
            self.options[ OPTIONS_GENERAL ] = user_input
            return await self.async_step_light()

        status_poll_selector = vol.All(
                NumberSelector(
                        NumberSelectorConfig(
                                mode=NumberSelectorMode.SLIDER, min=1, max=60, step=2, unit_of_measurement="minutes"
                        )
                ),
                vol.Coerce( int )
        )

        version_poll_selector = vol.All(
                NumberSelector(
                        NumberSelectorConfig(
                                mode=NumberSelectorMode.SLIDER, min=0, max=720, step=1, unit_of_measurement="hours"
                        )
                ),
                vol.Coerce( int )
        )

        return self.async_show_form(
                step_id=OPTIONS_GENERAL,
                data_schema=vol.Schema(
                        {
                            vol.Required( OPTIONS_GENERAL_POLL_INTERVAL,
                                          default=self.options[ OPTIONS_GENERAL ].get(
                                                  OPTIONS_GENERAL_POLL_INTERVAL, DEFAULT_POLL_INTERVAL )
                                          ): status_poll_selector,
                            vol.Required( OPTIONS_GENERAL_VER_INTERVAL,
                                          default=self.options[ OPTIONS_GENERAL ].get(
                                                  OPTIONS_GENERAL_VER_INTERVAL, DEFAULT_VER_INTERVAL )
                                          ): version_poll_selector,
                            vol.Required( OPTIONS_GENERAL_DISABLE_NOT_RESPONDING,
                                          default=self.options[ OPTIONS_GENERAL ].get( OPTIONS_GENERAL_DISABLE_NOT_RESPONDING )
                                          ): cv.boolean
                        }
                ),
                description_placeholders=self._get_description_placeholders(),
                last_step=(self._step_no == self._step_total)
        )

    async def async_step_light( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        self._step_no = 2
        if user_input is not None:
            self.options[ OPTIONS_LIGHT ] = user_input
            return await self.async_step_cover()

        return self.async_show_form(
                step_id=OPTIONS_LIGHT,
                data_schema=vol.Schema(
                        {
                            vol.Required( OPTIONS_LIGHT_ICONS_LIST,
                                          default=self.options[ OPTIONS_LIGHT ].get( OPTIONS_LIGHT_ICONS_LIST )
                                          ): cv.multi_select( DEVICE_ICON_ARR_LIGHT ),
                        }
                ),
                description_placeholders=self._get_description_placeholders(),
                last_step=(self._step_no == self._step_total),
        )

    async def async_step_cover( self, user_input: dict[ str, Any ] | None = None ) -> ConfigFlowResult:
        self._step_no = 3
        if user_input is not None:
            self.options[ OPTIONS_COVER ] = user_input
            return self.async_create_entry( title="Exta Life Options", data=self.options )

        return self.async_show_form(
                step_id=OPTIONS_COVER,
                data_schema=vol.Schema(
                        {
                            vol.Required( OPTIONS_COVER_INVERTED_CONTROL,
                                          default=self.options[ OPTIONS_COVER ].get( OPTIONS_COVER_INVERTED_CONTROL )
                                          ): bool,
                        }
                ),
                description_placeholders=self._get_description_placeholders(),
                last_step=(self._step_no == self._step_total),
        )
