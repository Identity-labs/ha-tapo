from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
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


_SENSOR_SPECS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="battery_percentage",
        translation_key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
    ),
    SensorEntityDescription(
        key="battery_low",
        translation_key="battery_low",
        name="Battery low",
        icon="mdi:battery-alert",
    ),
    SensorEntityDescription(
        key="model",
        translation_key="model",
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:information-outline",
    ),
    SensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        name="Firmware version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
    ),
    SensorEntityDescription(
        key="hardware_version",
        translation_key="hardware_version",
        name="Hardware version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
    ),
    SensorEntityDescription(
        key="nickname",
        translation_key="nickname",
        name="Nickname",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:rename-box",
    ),
    SensorEntityDescription(
        key="mac",
        translation_key="mac",
        name="MAC address",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:network",
    ),
    SensorEntityDescription(
        key="device_id",
        translation_key="device_id",
        name="Device ID",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:identifier",
    ),
    SensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        name="Signal strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
    ),
    SensorEntityDescription(
        key="signal_level",
        translation_key="signal_level",
        name="Signal level",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="at_low_battery",
        translation_key="at_low_battery",
        name="Low battery warning",
        icon="mdi:battery-alert-variant-outline",
    ),
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
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        api: TapoAPI,
        device: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry, api, device)
        self.entity_description = description
        self._sensor_key = description.key
        self._attr_unique_id = f"{entry.entry_id}_{self._device_id}_{description.key}"

    @property
    def native_value(self) -> str | int | float | bool | None:
        if isinstance(self.coordinator.data, dict):
            value = self.coordinator.data.get(self._sensor_key)
            return value
        return None

