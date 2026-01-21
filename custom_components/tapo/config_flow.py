from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .api import TapoAPI
from .const import (
    CONF_EVENT_POLL_INTERVAL,
    DEFAULT_EVENT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_HOST): str,
        vol.Optional(
            CONF_EVENT_POLL_INTERVAL,
            default=DEFAULT_EVENT_POLL_INTERVAL,
            description="Event polling interval in seconds (0.1-10)",
        ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10.0)),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_HOST): str,
        vol.Optional(
            CONF_EVENT_POLL_INTERVAL,
            default=DEFAULT_EVENT_POLL_INTERVAL,
            description="Event polling interval in seconds (0.1-10)",
        ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10.0)),
    }
)


class TapoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TapoOptionsFlowHandler:
        return TapoOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = f"{user_input[CONF_HOST]}_{user_input[CONF_USERNAME]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            api = TapoAPI(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_HOST],
            )

            try:
                auth_result = await api.async_authenticate()
                if auth_result:
                    await api.async_close()
                    return self.async_create_entry(
                        title=f"Tapo {user_input[CONF_HOST]}",
                        data=user_input,
                    )
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Connection error during authentication: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                await api.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_user(user_input)


class TapoOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        config_entry = self.config_entry

        if user_input is not None:
            if config_entry.entry_id in self.hass.data.get(DOMAIN, {}):
                entry_data = self.hass.data[DOMAIN][config_entry.entry_id]
                if "api" in entry_data:
                    await entry_data["api"].async_close()

            api = TapoAPI(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_HOST],
            )

            try:
                auth_result = await api.async_authenticate()
                if auth_result:
                    await api.async_close()
                    updated_data = dict(config_entry.data)
                    updated_data.update({
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_HOST: user_input[CONF_HOST],
                    })
                    await self.hass.config_entries.async_update_entry(
                        config_entry, data=updated_data
                    )
                    current_interval = (
                        config_entry.options.get(CONF_EVENT_POLL_INTERVAL)
                        or config_entry.data.get(CONF_EVENT_POLL_INTERVAL)
                        or DEFAULT_EVENT_POLL_INTERVAL
                    )
                    return self.async_create_entry(
                        data={CONF_EVENT_POLL_INTERVAL: user_input.get(CONF_EVENT_POLL_INTERVAL, current_interval)}
                    )
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Connection error during authentication: %s", err)
                errors["base"] = "cannot_connect"
            finally:
                await api.async_close()

        event_poll_interval = (
            config_entry.options.get(CONF_EVENT_POLL_INTERVAL)
            or config_entry.data.get(CONF_EVENT_POLL_INTERVAL)
            or DEFAULT_EVENT_POLL_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=config_entry.data.get(CONF_USERNAME),
                    ): str,
                    vol.Required(
                        CONF_PASSWORD,
                        default=config_entry.data.get(CONF_PASSWORD),
                    ): str,
                    vol.Required(
                        CONF_HOST,
                        default=config_entry.data.get(CONF_HOST),
                    ): str,
                    vol.Optional(
                        CONF_EVENT_POLL_INTERVAL,
                        default=event_poll_interval,
                        description="Event polling interval in seconds (0.1-10)",
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10.0)),
                }
            ),
            errors=errors,
        )

