"""Support for binary sensors."""

# pylint: disable=global-statement
# pylint: disable=broad-except
# pylint: disable=unused-argument
# pylint: disable=line-too-long
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from lennoxs30api import LENNOX_OUTDOOR_UNIT_HP, lennox_system

from custom_components.lennoxs30.binary_sensor_ble import BleBinarySensor

from . import Manager
from .base_entity import S30BaseEntityMixin
from .binary_sensor_ble import BleCommStatusBinarySensor
from .ble_device_21p02 import lennox_21p02_binary_sensors
from .ble_device_22v25 import lennox_22v25_binary_sensors
from .const import (
    MANAGER,
    UNIQUE_ID_SUFFIX_AUX_HI_AMBIENT_LOCKOUT,
    UNIQUE_ID_SUFFIX_CLOUD_CONNECTED_SENSOR,
    UNIQUE_ID_SUFFIX_HP_LOW_AMBIENT_LOCKOUT,
    UNIQUE_ID_SUFFIX_INTENET_STATUS_SENSOR,
    UNIQUE_ID_SUFFIX_RELAY_STATUS_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "lennoxs30"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Set up the binary entities."""
    sensor_list = []

    manager: Manager = hass.data[DOMAIN][entry.unique_id][MANAGER]
    for system in manager.api.system_list:
        _LOGGER.debug("Create S30HomeStateBinarySensor binary_sensor system [%s]", system.sysId)
        sensor = S30HomeStateBinarySensor(hass, manager, system)
        sensor_list.append(sensor)

        if manager.api.isLANConnection:
            sensor = S30InternetStatus(hass, manager, system)
            sensor_list.append(sensor)
            sensor = S30RelayServerStatus(hass, manager, system)
            sensor_list.append(sensor)
        else:
            sensor = S30CloudConnectedStatus(hass, manager, system)
            sensor_list.append(sensor)

        if system.outdoorUnitType == LENNOX_OUTDOOR_UNIT_HP:
            sensor_list.append(S30HeatpumpLowAmbientLockout(hass, manager, system))
            sensor_list.append(S30AuxheatHighAmbientLockout(hass, manager, system))

        if manager.create_sensors:
            sensor_list.append(S30HeatPumpShortCycleDelaySensor(hass, manager, system))
            sensor_list.append(S30HeatPumpDefrostStatusSensor(hass, manager, system))

        for ble_device in system.ble_devices.values():
            if ble_device.deviceType == "tstat":
                continue
            sensor_list.append(BleCommStatusBinarySensor(hass, manager, system, ble_device))

            ble_sensors: dict = None
            if ble_device.controlModelNumber == "22V25":
                ble_sensors = lennox_22v25_binary_sensors
            elif ble_device.controlModelNumber == "21P02":
                ble_sensors = lennox_21p02_binary_sensors
            if ble_sensors:
                for sensor_dict in ble_sensors:
                    if sensor_dict["input_id"] not in ble_device.inputs:
                        _LOGGER.error(
                            "Error BleBinarySensor name [%s] sensor_name [%s] no input_id [%d]",
                            ble_device.deviceName,
                            sensor_dict["name"],
                            sensor_dict["input_id"],
                        )
                        continue
                    sensor_value = ble_device.inputs[sensor_dict["input_id"]]
                    status_value = None
                    if "status_id" in sensor_dict:
                        if sensor_dict["status_id"] not in ble_device.inputs:
                            _LOGGER.error(
                                "Error BleBinarySensor name [%s] sensor_name [%s] no status_id [%d]",
                                ble_device.deviceName,
                                sensor_dict["name"],
                                sensor_dict["status_id"],
                            )
                            continue
                        status_value = ble_device.inputs[sensor_dict["status_id"]]
                    sensor_list.append(BleBinarySensor(hass, manager, system, ble_device, sensor_value, status_value, sensor_dict))
            else:
                _LOGGER.error(
                    "Error unknown BLE sensor name [%s] deviceType [%s] controlModelNumber [%s]- please raise an issue",
                    ble_device.deviceName,
                    ble_device.deviceType,
                    ble_device.controlModelNumber,
                )

    if len(sensor_list) != 0:
        async_add_entities(sensor_list, update_before_add=True)
        _LOGGER.debug("binary_sensor:async_setup_platform exit - created [%d] entitites", len(sensor_list))
    else:
        _LOGGER.warning("binary_sensor:async_setup_platform exit - no S30HomeStateBinarySensor found - this should not happen")
    return True


class S30HomeStateBinarySensor(S30BaseEntityMixin, BinarySensorEntity):
    """Home State Binary Sensor."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        """Create object."""
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_home_state"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30HomeStateBinarySensor myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "manualAwayMode",
                "sa_enabled",
                "sa_state",
                "sa_reset",
                "sa_cancel",
                "sa_setpointState",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self) -> None:
        """Process updates."""
        _LOGGER.debug("update_callback S30HomeStateBinarySensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return unique_id."""
        # HA fails with dashes in IDs
        return (self._system.unique_id + "_HS").replace("-", "")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs: dict[str, Any] = {}
        attrs["manual_away"] = self._system.get_manual_away_mode()
        attrs["smart_away"] = self._system.get_smart_away_mode()
        attrs["smart_away_enabled"] = self._system.sa_enabled
        attrs["smart_away_state"] = self._system.sa_state
        attrs["smart_away_reset"] = self._system.sa_reset
        attrs["smart_away_cancel"] = self._system.sa_cancel
        attrs["smart_away_setpoint_state"] = self._system.sa_setpointState
        return attrs

    @property
    def name(self) -> str:
        """Return entity name."""
        return self._myname

    @property
    def is_on(self) -> bool:
        """Return entity state."""
        return self._system.get_away_mode() is False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }

    @property
    def device_class(self) -> BinarySensorDeviceClass:
        """Return device_class."""
        return BinarySensorDeviceClass.PRESENCE


class S30InternetStatus(S30BaseEntityMixin, BinarySensorEntity):
    """Entity for S30 connected to internet."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        """Create object."""
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_internet_status"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30InternetStatus myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "internetStatus",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self) -> None:
        """Process data change."""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30InternetStatus myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return entity unique_id."""
        # HA fails with dashes in IDs
        return (self._system.unique_id + UNIQUE_ID_SUFFIX_INTENET_STATUS_SENSOR).replace("-", "")

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        return {}

    @property
    def available(self) -> bool:
        """Return entity availability."""
        if self._system.internetStatus is None:
            return False
        return super().available

    @property
    def name(self) -> str:
        """Return entity name."""
        return self._myname

    @property
    def is_on(self) -> bool:
        """Return entity state."""
        return self._system.internetStatus

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }

    @property
    def device_class(self) -> BinarySensorDeviceClass:
        """Return device_class."""
        return BinarySensorDeviceClass.CONNECTIVITY

    @property
    def entity_category(self) -> EntityCategory:
        """Return entity category."""
        return EntityCategory.DIAGNOSTIC


class S30RelayServerStatus(S30BaseEntityMixin, BinarySensorEntity):
    """Relay Server Status."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        """Create object."""
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_relay_server"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30RelayServerStatus myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "relayServerConnected",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self) -> None:
        """Process data change."""
        _LOGGER.debug("update_callback S30RelayServerStatus myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return unique_id."""
        # HA fails with dashes in IDs
        return (self._system.unique_id + UNIQUE_ID_SUFFIX_RELAY_STATUS_SENSOR).replace("-", "")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {}

    @property
    def name(self) -> str:
        """Return entity name."""
        return self._myname

    @property
    def available(self) -> bool:
        """Return entity availability."""
        if self._system.relayServerConnected is None:
            return False
        return super().available

    @property
    def is_on(self) -> bool:
        """Return entity state."""
        return self._system.relayServerConnected

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }

    @property
    def device_class(self) -> BinarySensorDeviceClass:
        """Return device_class."""
        return BinarySensorDeviceClass.CONNECTIVITY

    @property
    def entity_category(self) -> EntityCategory:
        """Return entity cateogory."""
        return EntityCategory.DIAGNOSTIC


class S30CloudConnectedStatus(S30BaseEntityMixin, BinarySensorEntity):
    """Cloud connection status."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        """Create object."""
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_cloud_connected"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30CloudConnectedStatus myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "cloud_status",
            ],
        )
        await super().async_added_to_hass()

    @property
    def base_ignore_cloud_status(self) -> bool:
        """Return whether to ignore cloud status."""
        return True

    def update_callback(self) -> None:
        """Process data change."""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30CloudConnectedStatus myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return entity unique_id."""
        # HA fails with dashes in IDs
        return (self._system.unique_id + UNIQUE_ID_SUFFIX_CLOUD_CONNECTED_SENSOR).replace("-", "")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        return {}

    @property
    def name(self) -> str:
        """Return name."""
        return self._myname

    @property
    def available(self) -> bool:
        """Return entity availability."""
        if self._system.cloud_status is None:
            return False
        return super().available

    @property
    def is_on(self) -> bool:
        """Return entity state."""
        if self._system.cloud_status == "online":
            return True
        if self._system.cloud_status == "offline":
            return False
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }

    @property
    def device_class(self) -> BinarySensorDeviceClass:
        """Return device_class."""
        return BinarySensorDeviceClass.CONNECTIVITY

    @property
    def entity_category(self) -> EntityCategory:
        """Return entity_category."""
        return EntityCategory.DIAGNOSTIC


class S30NamedDiagnosticBinarySensor(S30BaseEntityMixin, BinarySensorEntity):
    """Dedicated read-only binary sensor for one named equipment diagnostic."""

    _suffix = "_RO_DIAG_BINARY"
    _label = "diagnostic_binary"
    _equipment_id = 1
    _diagnostic_names: tuple[str, ...] = ()
    _diagnostic_ids: tuple[int, ...] = ()
    _on_values = {"yes", "on", "active", "true", "1"}

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        super().__init__(manager, system)
        self._hass = hass
        self._myname = (self._system.name or "lennox") + "_" + self._label

    def _equipment(self):
        return self._system.equipment.get(self._equipment_id)

    def _diagnostic(self):
        equipment = self._equipment()
        if equipment is None:
            return None
        wanted_ids = {str(item) for item in self._diagnostic_ids}
        if wanted_ids:
            for diagnostic in equipment.diagnostics.values():
                if str(diagnostic.diagnostic_id) in wanted_ids:
                    return diagnostic
        for diagnostic in equipment.diagnostics.values():
            if diagnostic.name in self._diagnostic_names:
                return diagnostic
        return None

    @property
    def unique_id(self) -> str:
        return (self._system.unique_id + self._suffix).replace("-", "")

    @property
    def name(self) -> str:
        return self._myname

    @property
    def available(self) -> bool:
        diagnostic = self._diagnostic()
        if diagnostic is None or diagnostic.value == "waiting..." or diagnostic.valid is False:
            return False
        return super().available

    @property
    def is_on(self) -> bool:
        diagnostic = self._diagnostic()
        if diagnostic is None or diagnostic.value is None:
            return None
        return str(diagnostic.value).strip().casefold() in self._on_values

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        diagnostic = self._diagnostic()
        equipment = self._equipment()
        return {
            "read_only": True,
            "writes_to_thermostat": False,
            "equipment_id": self._equipment_id,
            "equipment_name": None if equipment is None else equipment.equipment_name,
            "diagnostic_id": None if diagnostic is None else diagnostic.diagnostic_id,
            "diagnostic_name": None if diagnostic is None else diagnostic.name,
            "raw_value": None if diagnostic is None else diagnostic.value,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._system.unique_id + "_ou")},
        }

    @property
    def entity_category(self) -> EntityCategory:
        return EntityCategory.DIAGNOSTIC


class S30HeatPumpShortCycleDelaySensor(S30NamedDiagnosticBinarySensor):
    """Compressor short-cycle delay active sensor."""

    _suffix = "_RO_HP_SHORT_CYCLE_DELAY"
    _label = "heat_pump_short_cycle_delay_active"
    _diagnostic_names = ("Comp. Short Cycle Delay Active", "Compressor Short Cycle Delay Active")
    _diagnostic_ids = (0,)


class S30HeatPumpDefrostStatusSensor(S30NamedDiagnosticBinarySensor):
    """Heat pump defrost active sensor."""

    _suffix = "_RO_HP_DEFROST_ACTIVE"
    _label = "heat_pump_defrost_active"
    _diagnostic_names = ("Defrost Status",)
    _diagnostic_ids = (7,)


class S30HeatpumpLowAmbientLockout(S30BaseEntityMixin, BinarySensorEntity):
    """Heatpump is locked out."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        """Create object."""
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_hp_lo_ambient_lockout"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30HeatpumpLowAmbientLockout myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "heatpump_low_ambient_lockout",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self) -> None:
        """Process data changes."""
        _LOGGER.debug("update_callback S30HeatpumpLowAmbientLockout myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return unique_id."""
        # HA fails with dashes in IDs
        return (self._system.unique_id + UNIQUE_ID_SUFFIX_HP_LOW_AMBIENT_LOCKOUT).replace("-", "")

    @property
    def name(self) -> str:
        """Return name."""
        return self._myname

    @property
    def is_on(self) -> bool:
        """Return entity state."""
        return self._system.heatpump_low_ambient_lockout

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }


class S30AuxheatHighAmbientLockout(S30BaseEntityMixin, BinarySensorEntity):
    """Auxheat lockout."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system) -> None:
        """Create object."""
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_auxheat_hi_ambient_lockout"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30AuxheatHighAmbientLockout myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "aux_heat_high_ambient_lockout",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self) -> None:
        """Process data change."""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30AuxheatHighAmbientLockout myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        """Return entity unique_id."""
        # HA fails with dashes in IDs
        return (self._system.unique_id + UNIQUE_ID_SUFFIX_AUX_HI_AMBIENT_LOCKOUT).replace("-", "")

    @property
    def name(self) -> str:
        """Return entity name."""
        return self._myname

    @property
    def is_on(self) -> bool:
        """Return entitiy state."""
        return self._system.aux_heat_high_ambient_lockout

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }
