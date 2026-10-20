from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import TapoAPI
from .const import DOMAIN
from .entity import async_ensure_hub_device

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    
    api = TapoAPI(
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_HOST],
    )
    
    await api.async_authenticate()
    api.set_hub_info(await api.async_get_hub_info())

    hass.data[DOMAIN][entry.entry_id] = {"api": api}

    # via_device_id is a registry id, so the hub must exist before child
    # button devices that connect through it are added.
    async_ensure_hub_device(hass, api, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        if "api" in entry_data:
            await entry_data["api"].async_close()
    
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

