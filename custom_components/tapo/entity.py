"""Base entity with hub and child device registry support."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TapoAPI
from .const import DOMAIN, MANUFACTURER

_HUB_REGISTRY_KEYS = (
    "configuration_url",
    "connections",
    "hw_version",
    "identifiers",
    "manufacturer",
    "model",
    "name",
    "serial_number",
    "sw_version",
)


def _text(data: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty string value among keys."""
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _mac_connection(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return (dr.CONNECTION_NETWORK_MAC, dr.format_mac(value))
    except ValueError:
        return None


def button_name(device: dict[str, Any]) -> str:
    """Human-readable name for an S200B/S200D, from its Tapo nickname."""
    return (
        _text(device, "nickname", "device_name")
        or _text(device, "model")
        or str(device.get("device_id") or "Tapo button")
    )


def build_hub_device_info(api: TapoAPI, entry: ConfigEntry) -> DeviceInfo:
    """Build the hub device entry for the H100."""
    hub = api.hub_info
    model = _text(hub, "model", "type") or "H100"
    name = _text(hub, "nickname") or f"Tapo {model}"
    identifier = api.hub_identifier or entry.entry_id

    info = DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        name=name,
        manufacturer=MANUFACTURER,
        model=model,
        configuration_url=f"http://{api.host}",
    )
    if sw_version := _text(hub, "firmware_version", "fw_ver", "fw_version"):
        info["sw_version"] = sw_version
    if hw_version := _text(hub, "hardware_version", "hw_ver", "hw_version"):
        info["hw_version"] = hw_version
    if serial := _text(hub, "device_id", "deviceId"):
        info["serial_number"] = serial
    if connection := _mac_connection(hub.get("mac")):
        info["connections"] = {connection}
    return info


def async_ensure_hub_device(
    hass: HomeAssistant,
    api: TapoAPI,
    entry: ConfigEntry,
) -> None:
    """Register the hub so child devices can reference it by registry id."""
    info = build_hub_device_info(api, entry)
    kwargs = {key: info[key] for key in _HUB_REGISTRY_KEYS if info.get(key) is not None}
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **kwargs,
    )


def build_button_device_info(
    hass: HomeAssistant,
    api: TapoAPI,
    entry: ConfigEntry,
    device: dict[str, Any],
) -> DeviceInfo:
    """Build a device registry entry for one S200B/S200D."""
    hub_id = api.hub_identifier or entry.entry_id
    device_id = str(device.get("device_id") or "")

    # Defensive: never create a second device that shares the hub identifier.
    if device_id and device_id == hub_id:
        return DeviceInfo(identifiers={(DOMAIN, hub_id)})

    via_device_id = None
    if hub_id:
        via_device_id = dr.async_get_device_id_by_identifier(
            hass,
            (DOMAIN, hub_id),
            config_entry_id=entry.entry_id,
        )

    info = DeviceInfo(
        identifiers={(DOMAIN, device_id or hub_id)},
        name=button_name(device),
        manufacturer=MANUFACTURER,
        model=_text(device, "model") or "S200B",
        **({"via_device_id": via_device_id} if via_device_id else {}),
    )
    if sw_version := _text(device, "firmware_version", "fw_ver", "fw_version"):
        info["sw_version"] = sw_version
    if hw_version := _text(device, "hardware_version", "hw_ver", "hw_version"):
        info["hw_version"] = hw_version
    if device_id:
        info["serial_number"] = device_id
    if connection := _mac_connection(device.get("mac")):
        info["connections"] = {connection}
    return info


class TapoChildEntity(CoordinatorEntity):
    """Base class for entities that belong to one button device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        api: TapoAPI,
        device: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._api = api
        self._device_id = str(device.get("device_id") or "")
        self._attr_device_info = build_button_device_info(
            coordinator.hass, api, entry, device
        )
