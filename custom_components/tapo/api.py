from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from tapo import ApiClient

from .const import AUTH_RETRY_SECONDS

_LOGGER = logging.getLogger(__name__)

_S200_EVENT_NAMES = ("SingleClick", "DoubleClick", "Rotation", "LowBattery")


def _click_type_from_entry(log_entry: Any) -> str:
    """Return the button event name from a trigger log.

    tapo < 0.11 exposed each log as its own class (SingleClick, Rotation, ...).
    tapo >= 0.11 always returns an S200Log whose event is an S200Event variant.
    """
    event = getattr(log_entry, "event", None)
    if event is not None:
        matched = _match_s200_event(event)
        if matched:
            return matched
        label = _variant_label(event)
        if label:
            return label
    return type(log_entry).__name__


def _match_s200_event(event: Any) -> str | None:
    try:
        from tapo.responses import S200Event
    except Exception:
        return None

    for name in _S200_EVENT_NAMES:
        variant = getattr(S200Event, name, None)
        if variant is not None and event == variant:
            return name
    return None


def _variant_label(event: Any) -> str | None:
    raw = getattr(event, "name", None)
    text = str(raw if raw is not None else event).strip()
    if text.startswith("<"):
        text = text[1:].split(":", 1)[0].strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.strip(" >")
    if not text or text in {"S200Event", "S200Log", "None"}:
        return None
    return text


def _event_timestamp(log_entry: Any) -> int | None:
    """Unix seconds for a log, from the old timestamp field or triggered_at."""
    timestamp = getattr(log_entry, "timestamp", None)
    if isinstance(timestamp, (int, float)):
        return int(timestamp)

    triggered_at = getattr(log_entry, "triggered_at", None)
    if isinstance(triggered_at, datetime):
        return int(triggered_at.timestamp())
    if isinstance(triggered_at, str):
        try:
            return int(datetime.fromisoformat(triggered_at.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    if hasattr(triggered_at, "timestamp"):
        try:
            return int(triggered_at.timestamp())
        except (TypeError, ValueError):
            return None
    return None


class TapoAPI:
    def __init__(
        self,
        username: str,
        password: str,
        host: str,
    ) -> None:
        self.username = username
        self.password = password
        self.host = host
        self._client: ApiClient | None = None
        self._hub: Any | None = None
        self._device: Any | None = None
        self._s200_handler: Any | None = None
        self._device_id: str | None = None
        self._authenticated = False
        self._last_successful_auth_time: datetime | None = None
        self._auth_lock = asyncio.Lock()
        self._auth_retry_monotonic = 0.0
        self._auth_failure_logged = False

    def _clear_session(self) -> None:
        self._authenticated = False
        self._client = None
        self._hub = None
        self._device = None
        self._s200_handler = None

    @staticmethod
    def _is_auth_rejection(err: BaseException) -> bool:
        message = str(err)
        return (
            "FORBIDDEN" in message
            or "Unauthorized" in message
            or "Third-Party Compatibility" in message
        )

    def _register_auth_failure(self, err: BaseException) -> None:
        self._clear_session()
        self._auth_retry_monotonic = time.monotonic() + AUTH_RETRY_SECONDS
        if self._auth_failure_logged:
            _LOGGER.debug("Authentication still failing: %s", err)
            return
        self._auth_failure_logged = True
        _LOGGER.error(
            "Authentication failed: %s. Will retry every %d seconds.",
            err,
            AUTH_RETRY_SECONDS,
        )

    async def async_authenticate(self) -> bool:
        async with self._auth_lock:
            if self._authenticated and self._hub is not None:
                return True

            remaining = self._auth_retry_monotonic - time.monotonic()
            if remaining > 0:
                _LOGGER.debug(
                    "Skipping authentication for %.0f more seconds after a previous failure",
                    remaining,
                )
                return False

            try:
                self._client = ApiClient(self.username, self.password)
                hub = await self._client.h100(self.host)
                _LOGGER.debug("Hub connected successfully at %s", self.host)

                child_devices = await hub.get_child_device_list()
                if not child_devices:
                    _LOGGER.warning("No child devices found on hub. S200B or S200D may need to be paired.")
                    self._clear_session()
                    return False

                self._device = child_devices[0]
                self._device_id = self._device.device_id if hasattr(self._device, "device_id") else None
                self._hub = hub

                if self._device_id:
                    try:
                        self._s200_handler = await hub.s200(self._device_id)
                        _LOGGER.debug("S200B/S200D handler created for device %s", self._device_id)
                    except Exception as err:
                        _LOGGER.warning("Could not create S200B/S200D handler: %s", err)

                self._authenticated = True
                self._last_successful_auth_time = datetime.now()
                self._auth_retry_monotonic = 0.0
                if self._auth_failure_logged:
                    _LOGGER.info("Authentication succeeded after a previous failure")
                    self._auth_failure_logged = False
                _LOGGER.debug("Authentication successful, found %d child device(s)", len(child_devices))
                return True
            except Exception as err:
                self._register_auth_failure(err)
                return False

    def _extract_device_data(self, device: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}
        
        if hasattr(device, "to_dict"):
            device_dict = device.to_dict()
            result.update(device_dict)
        else:
            if hasattr(device, "device_id"):
                result["device_id"] = device.device_id
            if hasattr(device, "model"):
                result["model"] = device.model
            if hasattr(device, "firmware_version"):
                result["firmware_version"] = device.firmware_version
            if hasattr(device, "hardware_version"):
                result["hardware_version"] = device.hardware_version
            if hasattr(device, "mac"):
                result["mac"] = device.mac
            if hasattr(device, "nickname"):
                result["nickname"] = device.nickname
            if hasattr(device, "device_name"):
                result["device_name"] = device.device_name
            if hasattr(device, "battery_percentage"):
                result["battery_percentage"] = device.battery_percentage
            if hasattr(device, "battery_low"):
                result["battery_low"] = device.battery_low
        
        props = [
            attr
            for attr in dir(device)
            if not attr.startswith("_") and not callable(getattr(device, attr, None))
        ]
        for prop in props:
            try:
                value = getattr(device, prop)
                if prop not in result:
                    result[prop] = value
            except Exception:
                pass
        
        return result

    async def async_get_device_info(self) -> dict[str, Any] | None:
        if not self._authenticated or not self._hub:
            _LOGGER.debug("Not authenticated, authenticating...")
            if not await self.async_authenticate():
                _LOGGER.debug("Authentication unavailable, cannot get device info")
                return None

        try:
            if not self._hub:
                return None
            
            child_devices = await self._hub.get_child_device_list()
            if not child_devices:
                return None
            
            current_device = child_devices[0]
            return self._extract_device_data(current_device)
        except Exception as err:
            _LOGGER.error("Failed to get device info: %s", err, exc_info=True)
            self._authenticated = False
            return None

    async def async_get_battery_status(self) -> dict[str, Any] | None:
        if not self._authenticated or not self._hub:
            _LOGGER.debug("Not authenticated, authenticating...")
            if not await self.async_authenticate():
                _LOGGER.debug("Authentication unavailable, cannot get battery status")
                return None

        try:
            if not self._hub:
                return None
            
            child_devices = await self._hub.get_child_device_list()
            if not child_devices:
                return None
            
            current_device = child_devices[0]
            device_data = self._extract_device_data(current_device)
            result: dict[str, Any] = {}
            
            if "battery_percentage" in device_data:
                result["battery_percentage"] = device_data["battery_percentage"]
            if "battery_low" in device_data:
                result["battery_low"] = device_data["battery_low"]
            if "at_low_battery" in device_data:
                result["at_low_battery"] = device_data["at_low_battery"]
            
            return result if result else None
        except Exception as err:
            _LOGGER.error("Failed to get battery status: %s", err, exc_info=True)
            self._authenticated = False
            return None

    async def async_get_all_child_devices(self) -> list[dict[str, Any]] | None:
        """Get all child devices from the hub."""
        if not self._authenticated or not self._hub:
            _LOGGER.debug("Not authenticated, authenticating...")
            if not await self.async_authenticate():
                _LOGGER.debug("Authentication unavailable, cannot get child devices")
                return None

        try:
            if not self._hub:
                _LOGGER.error("Hub not available")
                return None
            
            child_devices = await self._hub.get_child_device_list()
            if not child_devices:
                _LOGGER.warning("No child devices found")
                return None
            
            devices_data = []
            for device in child_devices:
                device_data = self._extract_device_data(device)
                if device_data:
                    devices_data.append(device_data)
            
            return devices_data if devices_data else None
        except Exception as err:
            _LOGGER.error("Failed to get child devices: %s", err, exc_info=True)
            return None

    async def async_get_sensor_data(self, device_id: str | None = None) -> dict[str, Any] | None:
        """Get sensor data for a specific device or the first device if device_id is None."""
        if not self._authenticated or not self._hub:
            _LOGGER.debug("Not authenticated, authenticating...")
            if not await self.async_authenticate():
                _LOGGER.debug("Authentication unavailable, cannot get sensor data")
                return None

        try:
            if not self._hub:
                _LOGGER.error("Hub not available")
                return None
            
            child_devices = await self._hub.get_child_device_list()
            if not child_devices:
                _LOGGER.warning("No child devices found")
                return None
            
            if device_id:
                for device in child_devices:
                    if hasattr(device, "device_id") and device.device_id == device_id:
                        device_data = self._extract_device_data(device)
                        return device_data if device_data else None
                _LOGGER.warning("Device %s not found", device_id)
                return None
            else:
                current_device = child_devices[0]
                device_data = self._extract_device_data(current_device)
                return device_data if device_data else None
        except Exception as err:
            _LOGGER.error("Failed to get sensor data: %s", err, exc_info=True)
            return None
    
    def _parse_trigger_logs(self, trigger_logs: Any) -> dict[str, Any] | None:
        """Parse trigger logs response into a dictionary format.
        
        Args:
            trigger_logs: Raw trigger logs response from the API
            
        Returns:
            Dictionary with parsed logs, start_id, and sum, or None if parsing fails
        """
        logs_list: list[dict[str, Any]] = []
        
        if hasattr(trigger_logs, "logs") and trigger_logs.logs:
            for log_entry in trigger_logs.logs:
                log_dict: dict[str, Any] = {
                    "click_type": _click_type_from_entry(log_entry),
                    "id": getattr(log_entry, "id", None),
                    "timestamp": _event_timestamp(log_entry),
                }
                
                params = getattr(log_entry, "params", None)
                if params is not None:
                    rotation_degrees = getattr(params, "rotation_degrees", None)
                    if rotation_degrees is None and isinstance(params, dict):
                        rotation_degrees = params.get("rotation_degrees", params.get("rotate_deg"))
                    if rotation_degrees is not None:
                        log_dict["rotation_degrees"] = rotation_degrees
                    elif hasattr(params, "__dict__"):
                        for key, value in params.__dict__.items():
                            log_dict[f"params_{key}"] = value
                
                if hasattr(log_entry, "__dict__"):
                    for key, value in log_entry.__dict__.items():
                        if key not in log_dict and key != "params":
                            log_dict[key] = value
                        elif key == "params" and hasattr(value, "__dict__"):
                            for param_key, param_value in value.__dict__.items():
                                log_dict[f"params_{param_key}"] = param_value
                
                logs_list.append(log_dict)
        elif hasattr(trigger_logs, "__iter__") and not isinstance(trigger_logs, str):
            for log_entry in trigger_logs:
                log_dict: dict[str, Any] = {}
                if hasattr(log_entry, "__dict__"):
                    log_dict.update(log_entry.__dict__)
                elif hasattr(log_entry, "to_dict"):
                    log_dict.update(log_entry.to_dict())
                else:
                    log_dict["raw"] = str(log_entry)
                logs_list.append(log_dict)
        elif hasattr(trigger_logs, "__dict__"):
            logs_list.append(trigger_logs.__dict__)
        elif hasattr(trigger_logs, "to_dict"):
            logs_list.append(trigger_logs.to_dict())
        else:
            _LOGGER.warning("Unexpected trigger logs format: %s", type(trigger_logs))
            return None
        
        result: dict[str, Any] = {
            "logs": logs_list,
            "start_id": getattr(trigger_logs, "start_id", None),
            "sum": getattr(trigger_logs, "sum", None),
        }
        
        return result
    
    async def async_get_trigger_logs(
        self, device_id: str | None = None, page_size: int = 20, start_id: int = 0
    ) -> dict[str, Any] | None:
        """Get trigger logs from S200B/S200D device - contains button click events.
        
        Args:
            page_size: Number of log entries to retrieve (default: 20)
            start_id: Starting log ID (0 for most recent, higher for older logs)
        
        Returns:
            List of trigger log entries, each containing button click information
        """
        if not self._authenticated:
            _LOGGER.debug("Not authenticated, authenticating...")
            if not await self.async_authenticate():
                _LOGGER.debug("Authentication unavailable, cannot get trigger logs")
                return None

        try:
            target_device_id = device_id or self._device_id
            if not target_device_id or not self._hub:
                _LOGGER.warning("S200B/S200D handler not available (device_id: %s)", target_device_id)
                return None
            
            s200_handler = await self._hub.s200(target_device_id)
            trigger_logs = await s200_handler.get_trigger_logs(
                page_size=page_size, start_id=start_id
            )
            
            return self._parse_trigger_logs(trigger_logs)
        except Exception as err:
            if self._is_auth_rejection(err):
                async with self._auth_lock:
                    self._register_auth_failure(err)
                return None

            error_str = str(err)
            is_connection_error = (
                "Connection reset" in error_str
                or "Connection refused" in error_str
                or "Connection closed" in error_str
                or "Connection reset by peer" in error_str
                or "Http" in str(type(err).__name__)
            )
            
            if is_connection_error:
                _LOGGER.warning(
                    "Connection error while getting trigger logs (device_id: %s): %s. Attempting to re-authenticate...",
                    target_device_id,
                    error_str,
                )
                self._authenticated = False
                self._hub = None
                self._s200_handler = None
                
                if await self.async_authenticate():
                    _LOGGER.info("Re-authentication successful, retrying trigger logs request...")
                    try:
                        target_device_id = device_id or self._device_id
                        if target_device_id and self._hub:
                            s200_handler = await self._hub.s200(target_device_id)
                            trigger_logs = await s200_handler.get_trigger_logs(
                                page_size=page_size, start_id=start_id
                            )
                            
                            result = self._parse_trigger_logs(trigger_logs)
                            if result:
                                _LOGGER.info("Successfully retrieved trigger logs after re-authentication")
                            return result
                    except Exception as retry_err:
                        _LOGGER.error("Failed to get trigger logs after re-authentication: %s", retry_err, exc_info=True)
                        return None
                else:
                    _LOGGER.debug("Re-authentication failed after connection error")
                    return None
            else:
                _LOGGER.error("Failed to get trigger logs: %s", err, exc_info=True)
                return None

    def get_last_successful_auth_time(self) -> datetime | None:
        return self._last_successful_auth_time

    async def async_close(self) -> None:
        self._authenticated = False
        self._device = None
        self._s200_handler = None
        self._hub = None
        self._client = None

