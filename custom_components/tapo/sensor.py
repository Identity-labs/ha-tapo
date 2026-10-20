from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import TapoAPI
from .button import TapoButtonCoordinator, TapoButtonSensor
from .const import CONF_EVENT_POLL_INTERVAL, DEFAULT_EVENT_POLL_INTERVAL, DOMAIN
from .entity import TapoChildEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SensorSpec:
    key: str
    translation_key: str
    unit: str | None = None
    state_class: SensorStateClass | None = None
    device_class: SensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None


_SENSOR_SPECS: tuple[_SensorSpec, ...] = (
    _SensorSpec(
        "battery_percentage",
        "battery",
        PERCENTAGE,
        SensorStateClass.MEASUREMENT,
        SensorDeviceClass.BATTERY,
    ),
    _SensorSpec("battery_low", "battery_low", icon="mdi:battery-alert"),
    _SensorSpec(
        "model",
        "model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:information-outline",
    ),
    _SensorSpec(
        "firmware_version",
        "firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
    ),
    _SensorSpec(
        "hardware_version",
        "hardware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
    ),
    _SensorSpec(
        "nickname",
        "nickname",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:rename-box",
    ),
    _SensorSpec(
        "mac",
        "mac",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:network",
    ),
    _SensorSpec(
        "device_id",
        "device_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
    ),
    _SensorSpec(
        "rssi",
        "rssi",
        SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        SensorStateClass.MEASUREMENT,
        SensorDeviceClass.SIGNAL_STRENGTH,
    ),
    _SensorSpec(
        "signal_level",
        "signal_level",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
    ),
    _SensorSpec("at_low_battery", "at_low_battery", icon="mdi:battery-alert-variant-outline"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    api: TapoAPI = entry_data["api"]

    all_devices = await api.async_get_all_child_devices()
    if not all_devices:
        _LOGGER.warning("No child devices found")
        return
    
    _LOGGER.info("Found %d S200B device(s)", len(all_devices))
    
    sensors = []
    
    for device_data in all_devices:
        device_id = device_data.get("device_id")
        device_nickname = device_data.get("nickname", "Unknown")
        
        if not device_id:
            _LOGGER.warning("Device without device_id, skipping")
            continue
        
        _LOGGER.debug("Setting up sensors for device %s (%s)", device_id, device_nickname)
        
        coordinator = TapoCoordinator(hass, api, device_id)
        await coordinator.async_config_entry_first_refresh()

        sensors_data = coordinator.data or {}
        _LOGGER.debug("Sensor setup for device %s: sensors data = %s", device_id, sensors_data)
        
        if sensors_data:
            for spec in _SENSOR_SPECS:
                if spec.key not in sensors_data:
                    continue
                sensors.append(TapoSensor(coordinator, entry, api, device_data, spec))

        poll_interval = entry.options.get(CONF_EVENT_POLL_INTERVAL) or entry.data.get(
            CONF_EVENT_POLL_INTERVAL, DEFAULT_EVENT_POLL_INTERVAL
        )
        button_coordinator = TapoButtonCoordinator(
            hass, api, device_id, poll_interval=poll_interval
        )
        await button_coordinator.async_config_entry_first_refresh()
        sensors.append(TapoButtonSensor(button_coordinator, entry, api, device_data))

    _LOGGER.info("Setting up %d sensor entities", len(sensors))
    async_add_entities(sensors)


class TapoCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: TapoAPI, device_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device_id}",
            update_interval=timedelta(seconds=60),
        )
        self.api = api
        self.device_id = device_id
        self._last_successful_update_time: datetime | None = None

    def get_last_successful_update_time(self) -> datetime | None:
        return self._last_successful_update_time

    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug("Updating sensor coordinator data for device %s", self.device_id)
        try:
            sensor_data = await self.api.async_get_sensor_data(device_id=self.device_id)
            if sensor_data is None:
                _LOGGER.warning("Failed to get sensor data for device %s, returning empty dict", self.device_id)
                return {}
            _LOGGER.debug("Sensor data retrieved for device %s: %s", self.device_id, sensor_data)
            self._last_successful_update_time = datetime.now()
            return sensor_data
        except asyncio.TimeoutError as err:
            _LOGGER.warning("Timeout while getting sensor data for device %s: %s", self.device_id, err)
            return {}
        except Exception as err:
            _LOGGER.error("Unexpected error updating sensor coordinator for device %s: %s", self.device_id, err, exc_info=True)
            return {}


class TapoSensor(TapoChildEntity, SensorEntity):
    _unrecorded_attributes = frozenset(
        {"last_successful_update", "last_successful_auth"}
    )
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        api: TapoAPI,
        device: dict[str, Any],
        spec: _SensorSpec,
    ) -> None:
        super().__init__(coordinator, entry, api, device)
        self._sensor_key = spec.key
        self._attr_translation_key = spec.translation_key
        self._attr_unique_id = f"{entry.entry_id}_{self._device_id}_{spec.key}"
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_state_class = spec.state_class
        self._attr_device_class = spec.device_class
        self._attr_entity_category = spec.entity_category
        if spec.icon:
            self._attr_icon = spec.icon

    @property
    def native_value(self) -> str | int | float | bool | None:
        if isinstance(self.coordinator.data, dict):
            value = self.coordinator.data.get(self._sensor_key)
            return value
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        
        if hasattr(self.coordinator, "get_last_successful_update_time"):
            last_update = self.coordinator.get_last_successful_update_time()
            attrs["last_successful_update"] = last_update.isoformat() if last_update else "Never"
        
        if hasattr(self.coordinator, "api") and hasattr(self.coordinator.api, "get_last_successful_auth_time"):
            last_auth = self.coordinator.api.get_last_successful_auth_time()
            attrs["last_successful_auth"] = last_auth.isoformat() if last_auth else "Never"
        
        return attrs

