from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import TapoAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class TapoButtonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: TapoAPI, device_id: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_button_events_{device_id}",
            update_interval=timedelta(seconds=2),
        )
        self.api = api
        self.device_id = device_id
        self._last_processed_id: int | None = None
        self._last_successful_update_time: datetime | None = None

    def get_last_successful_update_time(self) -> datetime | None:
        return self._last_successful_update_time

    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug("Updating button coordinator data for device %s", self.device_id)
        try:
            trigger_logs = await self.api.async_get_trigger_logs(device_id=self.device_id, page_size=10, start_id=0)
            if trigger_logs is None:
                _LOGGER.warning("Failed to get trigger logs, returning empty dict")
                return {"logs": [], "new_events": [], "last_event": None}

            logs = trigger_logs.get("logs", [])
            new_events: list[dict[str, Any]] = []

            if logs:
                if self._last_processed_id is None:
                    if logs:
                        self._last_processed_id = logs[0].get("id")
                        _LOGGER.debug("Initialized last_processed_id to %s", self._last_processed_id)
                else:
                    for log_entry in logs:
                        log_id = log_entry.get("id")
                        if log_id and log_id > self._last_processed_id:
                            new_events.append(log_entry)
                            _LOGGER.info("New button event detected: %s (ID: %s)", 
                                       log_entry.get("click_type"), log_id)
                    
                    if new_events:
                        self._last_processed_id = new_events[0].get("id")
                        self._fire_events(new_events)

            last_event = logs[0] if logs else None
            self._last_successful_update_time = datetime.now()
            return {"logs": logs, "new_events": new_events, "last_event": last_event}
        except asyncio.TimeoutError as err:
            _LOGGER.warning("Timeout while getting trigger logs: %s", err)
            return {"logs": [], "new_events": [], "last_event": None}
        except Exception as err:
            _LOGGER.error("Unexpected error updating button coordinator: %s", err, exc_info=True)
            return {"logs": [], "new_events": [], "last_event": None}

    @callback
    def _fire_events(self, new_events: list[dict[str, Any]]) -> None:
        for event in reversed(new_events):
            click_type = event.get("click_type", "unknown")
            timestamp = event.get("timestamp")
            event_id = event.get("id")
            
            if click_type == "SingleClick":
                event_type = "single_click"
            elif click_type == "DoubleClick":
                event_type = "double_click"
            else:
                event_type = click_type.lower().replace("click", "_click")
            
            self.hass.bus.async_fire(
                f"{DOMAIN}_button_pressed",
                {
                    "device_id": self.device_id,
                    "click_type": event_type,
                    "event_id": event_id,
                    "timestamp": timestamp,
                },
            )
            _LOGGER.info("Fired button event for device %s: %s (ID: %s)", self.device_id, event_type, event_id)


class TapoButtonSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        coordinator: TapoButtonCoordinator,
        config_entry_id: str,
        device_id: str,
        device_nickname: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = f"{device_nickname} Last Button Press"
        self._attr_unique_id = f"{config_entry_id}_{device_id}_last_button_press"

    @property
    def native_value(self) -> str | None:
        last_event = self.coordinator.data.get("last_event")
        if last_event:
            click_type = last_event.get("click_type", "unknown")
            return click_type.replace("Click", " Click")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        
        if hasattr(self.coordinator, "get_last_successful_update_time"):
            last_update = self.coordinator.get_last_successful_update_time()
            attrs["last_successful_update"] = last_update.isoformat() if last_update else "Never"
        
        last_event = self.coordinator.data.get("last_event")
        if last_event:
            timestamp = last_event.get("timestamp")
            if timestamp:
                dt = datetime.fromtimestamp(timestamp)
                attrs["last_event_time"] = dt.isoformat()
                attrs["last_event_time_readable"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            attrs["last_event_id"] = last_event.get("id")
            attrs["last_event_type"] = last_event.get("click_type")
        
        return attrs

