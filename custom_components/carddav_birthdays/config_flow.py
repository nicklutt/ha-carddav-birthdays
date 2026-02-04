"""Config flow for CardDAV Birthdays integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DEFAULT_VERIFY_SSL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    
    auth = aiohttp.BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD])
    
    # Simple GET request to check connectivity. 
    # Ideally we should do a PROPFIND or REPORT, but a GET/HEAD to the URL 
    # is a good first check if it returns 200 or 405 (Method Not Allowed) 
    # instead of 401 (Unauthorized) or Connection Error.
    # Note: Radicale often returns valid responses for PROPFIND.
    # We will try a simple request.
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                data[CONF_URL], 
                auth=auth, 
                ssl=data.get(CONF_VERIFY_SSL, True)
            ) as response:
                if response.status == 401:
                    raise InvalidAuth
                if response.status >= 500:
                    raise CannotConnect
                
                # We don't strictly require 200 here because CardDAV 
                # might return other 2xx or 405 for GET on a collection.
                # But connection + auth seems okay if we are here.
        except aiohttp.ClientError:
            raise CannotConnect

    return {"title": data[CONF_USERNAME]}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CardDAV Birthdays."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
