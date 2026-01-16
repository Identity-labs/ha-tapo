from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import TapoAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
            if "battery_percentage" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "battery_percentage",
                        f"{device_nickname} Battery",
                        "%",
                        SensorStateClass.MEASUREMENT,
                    )
                )
            
            if "battery_low" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "battery_low",
                        f"{device_nickname} Battery Low",
                        None,
                        None,
                    )
                )
            
            if "model" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "model",
                        f"{device_nickname} Model",
                        None,
                        None,
                    )
                )
            
            if "firmware_version" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "firmware_version",
                        f"{device_nickname} Firmware Version",
                        None,
                        None,
                    )
                )
            
            if "hardware_version" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "hardware_version",
                        f"{device_nickname} Hardware Version",
                        None,
                        None,
                    )
                )
            
            if "nickname" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "nickname",
                        f"{device_nickname} Nickname",
                        None,
                        None,
                    )
                )
            
            if "mac" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "mac",
                        f"{device_nickname} MAC Address",
                        None,
                        None,
                    )
                )
            
            if "device_id" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "device_id",
                        f"{device_nickname} Device ID",
                        None,
                        None,
                    )
                )
            
            if "rssi" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "rssi",
                        f"{device_nickname} Signal Strength (RSSI)",
                        "dBm",
                        SensorStateClass.MEASUREMENT,
                    )
                )
            
            if "signal_level" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "signal_level",
                        f"{device_nickname} Signal Level",
                        None,
                        SensorStateClass.MEASUREMENT,
                    )
                )
            
            if "at_low_battery" in sensors_data:
                sensors.append(
                    TapoSensor(
                        coordinator,
                        entry.entry_id,
                        device_id,
                        "at_low_battery",
                        f"{device_nickname} Low Battery Warning",
                        None,
                        None,
                    )
                )
            
            from .button import TapoButtonCoordinator, TapoButtonSensor
            button_coordinator = TapoButtonCoordinator(hass, api, device_id)
            await button_coordinator.async_config_entry_first_refresh()
            sensors.append(TapoButtonSensor(button_coordinator, entry.entry_id, device_id, device_nickname))

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


class TapoSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        device_id: str,
        sensor_key: str,
        name: str,
        unit: str | None,
        state_class: SensorStateClass | None,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._device_id = device_id
        self._attr_name = name
        self._attr_unique_id = f"{config_entry_id}_{device_id}_{sensor_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class

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

