"""Support for Lennoxs30 outdoor temperature sensor"""

# pylint: disable=global-statement
# pylint: disable=broad-except
# pylint: disable=unused-argument
# pylint: disable=line-too-long
# pylint: disable=invalid-name
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from lennoxs30api import (
    LENNOX_BAD_STATUS,
    LENNOX_STATUS_NOT_EXIST,
    lennox_equipment,
    lennox_equipment_diagnostic,
    lennox_system,
    lennox_zone,
)

from . import Manager
from .base_entity import S30BaseEntityMixin
from .ble_device_21p02 import lennox_21p02_sensors, lennox_iaq_sensors
from .ble_device_22v25 import lennox_22v25_sensors
from .const import (
    MANAGER,
    UNIQUE_ID_SUFFIX_ACTIVE_ALERTS_SENSOR,
    UNIQUE_ID_SUFFIX_ALERT_SENSOR,
    UNIQUE_ID_SUFFIX_DIAG_SENSOR,
)
from .helpers import helper_create_system_unique_id, helper_get_equipment_device_info, lennox_uom_to_ha_uom
from .sensor_ble import S40BleSensor
from .sensor_iaq import S40IAQSensor
from .sensor_wifi import WifiRSSISensor
from .sensor_wt_env import WTEnvSensor, lennox_wt_env_sensors, lennox_wt_env_sensors_metric, lennox_wt_env_sensors_us

_LOGGER = logging.getLogger(__name__)

DOMAIN = "lennoxs30"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Setup the home assistant entities"""
    sensor_list = []
    manager: Manager = hass.data[DOMAIN][entry.unique_id][MANAGER]
    for system in manager.api.system_list:
        if system.outdoorTemperatureStatus != LENNOX_STATUS_NOT_EXIST:
            _LOGGER.debug("Create S30OutdoorTempSensor system [%s]", system.sysId)
            sensor = S30OutdoorTempSensor(hass, manager, system)
            sensor_list.append(sensor)

        if manager.create_inverter_power:
            _LOGGER.debug("Create S30InverterPowerSensor system [%s]", system.sysId)
            if system.diagLevel != 2:
                _LOGGER.warning("Power Inverter Sensor requires S30 to be in diagLevel 2, currently in [%s]", system.diagLevel)
            if system.internetStatus or system.relayServerConnected:
                _LOGGER.warning(
                    "To prevent S30 instability - Power Inverter Sensor requires S30 to be isolated from internet - internetStatus [%s] relayServerConnected [%s] - https://github.com/PeteRager/lennoxs30/blob/master/docs/diagnostics.md",
                    system.internetStatus,
                    system.relayServerConnected,
                )
            power_sensor = S30InverterPowerSensor(hass, manager, system)
            sensor_list.append(power_sensor)

        if manager.create_diagnostic_sensors:
            _LOGGER.debug("Create Diagnostic Sensors system [%s]", system.sysId)
            if system.diagLevel != 2:
                _LOGGER.warning("Diagnostics requires S30 to be in diagLevel 2, currently in [%s]", system.diagLevel)
            if system.internetStatus or system.relayServerConnected:
                _LOGGER.warning(
                    "To prevent S30 instability - diagnostics requires S30 to be isolated from internet - internetStatus [%s] relayServerConnected [%s] - https://github.com/PeteRager/lennoxs30/blob/master/docs/diagnostics.md",
                    system.internetStatus,
                    system.relayServerConnected,
                )

            for _, eq in system.equipment.items():
                equip: lennox_equipment = eq
                if equip.equipment_id != 0:
                    for _, diagnostic in equip.diagnostics.items():
                        if diagnostic.valid:
                            _LOGGER.debug(
                                "Create Diagsensor system [%s] eid [%s] did [%s] name [%s]",
                                system.sysId,
                                equip.equipment_id,
                                diagnostic.diagnostic_id,
                                diagnostic.name,
                            )
                            diagsensor = S30DiagSensor(hass, manager, system, equip, diagnostic)
                            sensor_list.append(diagsensor)

        if system.is_s40:
            for env in lennox_wt_env_sensors:
                wt_sensor = WTEnvSensor(hass, manager, system, env)
                sensor_list.append(wt_sensor)
            if manager.is_metric:
                for env in lennox_wt_env_sensors_metric:
                    wt_sensor = WTEnvSensor(hass, manager, system, env)
                    sensor_list.append(wt_sensor)
            else:
                for env in lennox_wt_env_sensors_us:
                    wt_sensor = WTEnvSensor(hass, manager, system, env)
                    sensor_list.append(wt_sensor)

        if manager.create_sensors:
            sensor_list.extend(
                [
                    S30EquipmentInventorySensor(hass, manager, system),
                    S30EquipmentParameterInventorySensor(hass, manager, system),
                    S30ScheduleInventorySensor(hass, manager, system),
                    S30HeatPumpDiagnosticsSensor(hass, manager, system),
                    S30AirHandlerDiagnosticsSensor(hass, manager, system),
                    S30AirflowHealthSensor(hass, manager, system),
                    S30AirHandlerBlowerCFMDemandSensor(hass, manager, system),
                    S30AirHandlerBlowerRPMSensor(hass, manager, system),
                    S30AirHandlerBlowerPowerSensor(hass, manager, system),
                    S30AirHandlerDischargeAirTemperatureSensor(hass, manager, system),
                    S30HeatPumpCoolingRateSensor(hass, manager, system),
                    S30HeatPumpHeatingRateSensor(hass, manager, system),
                    S30HumidityIntelligenceSensor(hass, manager, system),
                ]
            )
            for zone in system.zone_list:
                if zone.is_zone_active():
                    _LOGGER.debug("Create S30TempSensor sensor system [%s] zone [%s]", system.sysId, zone.id)
                    sensor_list.append(S30TempSensor(hass, manager, system, zone))
                    _LOGGER.debug("Create S30HumSensor sensor system [%s] zone [%s]", system.sysId, zone.id)
                    sensor_list.append(S30HumiditySensor(hass, manager, system, zone))

        if manager.create_alert_sensors:
            sensor_list.append(S30AlertSensor(hass, manager, system))
            sensor_list.append(S30ActiveAlertsList(hass, manager, system))

        for ble_device in system.ble_devices.values():
            if ble_device.deviceType == "tstat":
                continue
            ble_sensors: dict = None
            if ble_device.controlModelNumber == "22V25":
                ble_sensors = lennox_22v25_sensors
            elif ble_device.controlModelNumber == "21P02":
                for sensor_item in lennox_iaq_sensors:
                    sensor_list.append(S40IAQSensor(hass, manager, system, ble_device, sensor_item))
                ble_sensors = lennox_21p02_sensors
            if ble_sensors:
                for sensor_dict in ble_sensors:
                    if sensor_dict["input_id"] not in ble_device.inputs:
                        _LOGGER.error(
                            "Error S40BleSensor name [%s] sensor_name [%s] no input_id [%d]",
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
                                "Error S40BleSensor name [%s] sensor_name [%s] no status_id [%d]",
                                ble_device.deviceName,
                                sensor_dict["name"],
                                sensor_dict["status_id"],
                            )
                            continue
                        status_value = ble_device.inputs[sensor_dict["status_id"]]
                    sensor_list.append(S40BleSensor(hass, manager, system, ble_device, sensor_value, status_value, sensor_dict))
            else:
                _LOGGER.error(
                    "Error unknown BLE sensor name [%s] deviceType [%s] controlModelNumber [%s]- please raise an issue",
                    ble_device.deviceName,
                    ble_device.deviceType,
                    ble_device.controlModelNumber,
                )

        if manager.api.isLANConnection:
            sensor_list.append(WifiRSSISensor(hass, manager, system))

    if len(sensor_list) != 0:
        async_add_entities(sensor_list, True)
        return True
    return False


def _system_name(system: lennox_system) -> str:
    """Return a safe system name for entity names."""
    return system.name or "lennox"


def _safe_float(value) -> float | None:
    """Convert numeric Lennox strings to floats, ignoring placeholders."""
    if value in (None, "", "waiting..."):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _diagnostic_map(equipment: lennox_equipment | None) -> dict[str, Any]:
    """Serialize existing diagnostic values for one equipment object."""
    if equipment is None:
        return {}
    result: dict[str, Any] = {}
    for diagnostic_id, diagnostic in sorted(equipment.diagnostics.items()):
        if diagnostic.valid is False:
            continue
        result[str(diagnostic_id)] = {
            "name": diagnostic.name,
            "value": None if diagnostic.value == "waiting..." else diagnostic.value,
            "unit": diagnostic.unit,
            "waiting": diagnostic.value == "waiting...",
        }
    return result


def _parameter_map(equipment: lennox_equipment | None) -> list[dict[str, Any]]:
    """Serialize equipment parameters without exposing write controls."""
    if equipment is None:
        return []
    params = []
    for _, parameter in sorted(equipment.parameters.items()):
        params.append(
            {
                "parameter_id": parameter.pid,
                "name": parameter.name,
                "value": parameter.value,
                "unit": parameter.unit,
                "enabled": parameter.enabled,
                "descriptor": parameter.descriptor,
                "range_min": parameter.range_min,
                "range_max": parameter.range_max,
                "range_inc": parameter.range_inc,
                "radio": parameter.radio,
            }
        )
    return params


class S30ReadOnlyContextSensor(S30BaseEntityMixin, SensorEntity):
    """Base class for read-only context sensors."""

    _suffix = "RO"
    _label = "read_only_context"

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = f"{_system_name(system)}_{self._label}"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        self._system.registerOnUpdateCallback(self.update_callback, [])
        await super().async_added_to_hass()

    def update_callback(self, *args) -> None:
        """Callback to execute on data change."""
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        return helper_create_system_unique_id(self._system, self._suffix)

    @property
    def name(self):
        return self._myname

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        return helper_get_equipment_device_info(self._manager, self._system, 0)


class S30EquipmentInventorySensor(S30ReadOnlyContextSensor):
    """Read-only equipment inventory."""

    _suffix = "_RO_EQUIPMENT_INVENTORY"
    _label = "equipment_inventory"

    @property
    def native_value(self):
        return len(self._system.equipment)

    @property
    def extra_state_attributes(self):
        return {
            "read_only": True,
            "equipment": [
                {
                    "equipment_id": equipment.equipment_id,
                    "name": equipment.equipment_name,
                    "type": equipment.equipment_type_name,
                    "type_id": equipment.equipType,
                    "model": equipment.unit_model_number,
                    "serial_present": equipment.unit_serial_number is not None,
                    "diagnostics_count": len(equipment.diagnostics),
                    "parameters_count": len(equipment.parameters),
                }
                for _, equipment in sorted(self._system.equipment.items())
            ],
        }


class S30EquipmentParameterInventorySensor(S30ReadOnlyContextSensor):
    """Read-only equipment parameter inventory."""

    _suffix = "_RO_PARAMETER_INVENTORY"
    _label = "equipment_parameter_inventory"

    @property
    def native_value(self):
        return sum(1 for equipment in self._system.equipment.values() for parameter in equipment.parameters.values() if parameter.enabled)

    @property
    def extra_state_attributes(self):
        return {
            "read_only": True,
            "writes_to_thermostat": False,
            "note": "parameter_safety_switch_required_for_writes; this entity only reports current parameter values",
            "equipment_parameters": [
                {
                    "equipment_id": equipment.equipment_id,
                    "equipment_name": equipment.equipment_name,
                    "equipment_type": equipment.equipment_type_name,
                    "parameters": _parameter_map(equipment),
                }
                for _, equipment in sorted(self._system.equipment.items())
            ],
        }


class S30ScheduleInventorySensor(S30ReadOnlyContextSensor):
    """Read-only schedule/period inventory."""

    _suffix = "_RO_SCHEDULE_INVENTORY"
    _label = "schedule_inventory"

    @property
    def native_value(self):
        return len(self._system.getSchedules())

    @property
    def extra_state_attributes(self):
        schedules = []
        for schedule in self._system.getSchedules():
            periods = []
            for period in schedule._periods:
                periods.append(
                    {
                        "period_id": period.id,
                        "enabled": period.enabled,
                        "start_time": period.startTime,
                        "system_mode": period.systemMode,
                        "heat_setpoint": period.hsp,
                        "cool_setpoint": period.csp,
                        "setpoint": period.sp,
                        "humidity_mode": period.humidityMode,
                        "humidify_setpoint": period.husp,
                        "dehumidify_setpoint": period.desp,
                        "fan_mode": period.fanMode,
                    }
                )
            schedules.append({"schedule_id": schedule.id, "name": schedule.name, "period_count": schedule.periodCount, "periods": periods})
        return {"read_only": True, "schedules": schedules}


class S30HeatPumpDiagnosticsSensor(S30ReadOnlyContextSensor):
    """Read-only heat pump diagnostic summary."""

    _suffix = "_RO_HEAT_PUMP_DIAGNOSTICS"
    _label = "heat_pump_diagnostics"

    def _outdoor_equipment(self):
        return self._system.get_outdoor_unit_equipment() or self._system.equipment.get(1)

    @property
    def native_value(self):
        equipment = self._outdoor_equipment()
        diagnostics = _diagnostic_map(equipment)
        if not diagnostics:
            return "unavailable"
        if any(item["waiting"] for item in diagnostics.values()):
            return "waiting"
        return "ok"

    @property
    def extra_state_attributes(self):
        equipment = self._outdoor_equipment()
        return {
            "read_only": True,
            "equipment_id": None if equipment is None else equipment.equipment_id,
            "equipment_name": None if equipment is None else equipment.equipment_name,
            "equipment_type": None if equipment is None else equipment.equipment_type_name,
            "model": None if equipment is None else equipment.unit_model_number,
            "diagnostics": _diagnostic_map(equipment),
        }


class S30AirHandlerDiagnosticsSensor(S30ReadOnlyContextSensor):
    """Read-only air handler diagnostic summary."""

    _suffix = "_RO_AIR_HANDLER_DIAGNOSTICS"
    _label = "air_handler_diagnostics"

    def _indoor_equipment(self):
        return self._system.get_indoor_unit_equipment() or self._system.equipment.get(2)

    @property
    def native_value(self):
        equipment = self._indoor_equipment()
        diagnostics = _diagnostic_map(equipment)
        if not diagnostics:
            return "unavailable"
        if any(item["waiting"] for item in diagnostics.values()):
            return "waiting"
        return "ok"

    @property
    def extra_state_attributes(self):
        equipment = self._indoor_equipment()
        return {
            "read_only": True,
            "equipment_id": None if equipment is None else equipment.equipment_id,
            "equipment_name": None if equipment is None else equipment.equipment_name,
            "equipment_type": None if equipment is None else equipment.equipment_type_name,
            "model": None if equipment is None else equipment.unit_model_number,
            "diagnostics": _diagnostic_map(equipment),
        }


class S30AirflowHealthSensor(S30ReadOnlyContextSensor):
    """Read-only airflow/filter health summary derived from existing diagnostics."""

    _suffix = "_RO_AIRFLOW_HEALTH"
    _label = "airflow_health"

    def _diagnostic_by_name(self, names: tuple[str, ...]):
        equipment = self._system.get_indoor_unit_equipment() or self._system.equipment.get(2)
        if equipment is None:
            return None
        for diagnostic in equipment.diagnostics.values():
            if diagnostic.name in names:
                return diagnostic.value
        return None

    @property
    def native_value(self):
        values = [
            self._diagnostic_by_name(("Blower CFM Demand",)),
            self._diagnostic_by_name(("Indoor Blower RPM",)),
            self._diagnostic_by_name(("Indoor Blower Power",)),
        ]
        if all(value in (None, "waiting...") for value in values):
            return "waiting"
        return "ok"

    @property
    def extra_state_attributes(self):
        return {
            "read_only": True,
            "writes_to_thermostat": False,
            "blower_cfm_demand": self._diagnostic_by_name(("Blower CFM Demand",)),
            "indoor_blower_rpm": self._diagnostic_by_name(("Indoor Blower RPM",)),
            "indoor_blower_power": self._diagnostic_by_name(("Indoor Blower Power",)),
            "discharge_air_temperature": self._diagnostic_by_name(("Discharge Air Temperature",)),
            "line_voltage": self._diagnostic_by_name(("Line Voltage",)),
            "low_airflow_hint": "compare CFM demand, RPM, and blower power trends against a clean-filter baseline",
        }


class S30NamedDiagnosticSensor(S30ReadOnlyContextSensor):
    """Dedicated read-only sensor for one named equipment diagnostic."""

    _label = "diagnostic"
    _suffix = "_RO_DIAGNOSTIC"
    _equipment_id = 0
    _diagnostic_names: tuple[str, ...] = ()
    _unit = None
    _device_class = None

    def _equipment(self):
        return self._system.equipment.get(self._equipment_id)

    def _diagnostic(self):
        equipment = self._equipment()
        if equipment is None:
            return None
        for diagnostic in equipment.diagnostics.values():
            if diagnostic.name in self._diagnostic_names:
                return diagnostic
        return None

    @property
    def available(self):
        diagnostic = self._diagnostic()
        if diagnostic is None or diagnostic.value == "waiting..." or diagnostic.valid is False:
            return False
        return super().available

    @property
    def native_value(self):
        diagnostic = self._diagnostic()
        if diagnostic is None or diagnostic.value == "waiting...":
            return None
        numeric = _safe_float(diagnostic.value)
        return numeric if numeric is not None else diagnostic.value

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_class(self):
        return self._device_class

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT if self._unit is not None else None

    @property
    def extra_state_attributes(self):
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


class S30AirHandlerBlowerCFMDemandSensor(S30NamedDiagnosticSensor):
    """Dedicated blower CFM demand sensor."""

    _suffix = "_RO_AH_BLOWER_CFM_DEMAND"
    _label = "air_handler_blower_cfm_demand"
    _equipment_id = 2
    _diagnostic_names = ("Blower CFM Demand",)
    _unit = UnitOfVolumeFlowRate.CUBIC_FEET_PER_MINUTE


class S30AirHandlerBlowerRPMSensor(S30NamedDiagnosticSensor):
    """Dedicated indoor blower RPM sensor."""

    _suffix = "_RO_AH_BLOWER_RPM"
    _label = "air_handler_blower_rpm"
    _equipment_id = 2
    _diagnostic_names = ("Indoor Blower RPM",)
    _unit = REVOLUTIONS_PER_MINUTE


class S30AirHandlerBlowerPowerSensor(S30NamedDiagnosticSensor):
    """Dedicated indoor blower power sensor."""

    _suffix = "_RO_AH_BLOWER_POWER"
    _label = "air_handler_blower_power"
    _equipment_id = 2
    _diagnostic_names = ("Indoor Blower Power",)
    _unit = PERCENTAGE


class S30AirHandlerDischargeAirTemperatureSensor(S30NamedDiagnosticSensor):
    """Dedicated discharge air temperature sensor."""

    _suffix = "_RO_AH_DISCHARGE_AIR_TEMPERATURE"
    _label = "air_handler_discharge_air_temperature"
    _equipment_id = 2
    _diagnostic_names = ("Discharge Air Temperature",)
    _unit = UnitOfTemperature.FAHRENHEIT
    _device_class = SensorDeviceClass.TEMPERATURE


class S30HeatPumpCoolingRateSensor(S30NamedDiagnosticSensor):
    """Dedicated heat pump cooling rate sensor."""

    _suffix = "_RO_HP_COOLING_RATE"
    _label = "heat_pump_cooling_rate"
    _equipment_id = 1
    _diagnostic_names = ("Cooling Rate",)
    _unit = PERCENTAGE


class S30HeatPumpHeatingRateSensor(S30NamedDiagnosticSensor):
    """Dedicated heat pump heating rate sensor."""

    _suffix = "_RO_HP_HEATING_RATE"
    _label = "heat_pump_heating_rate"
    _equipment_id = 1
    _diagnostic_names = ("Heating Rate",)
    _unit = PERCENTAGE


class S30HumidityIntelligenceSensor(S30ReadOnlyContextSensor):
    """Read-only humidity/dehumidification comfort summary."""

    _suffix = "_RO_HUMIDITY_INTELLIGENCE"
    _label = "humidity_intelligence"

    @property
    def native_value(self):
        humidities = [_safe_float(zone.getHumidity()) for zone in self._system.zone_list if zone.is_zone_active()]
        humidities = [value for value in humidities if value is not None]
        if not humidities:
            return "unknown"
        max_humidity = max(humidities)
        min_humidity = min(humidities)
        if max_humidity >= 60:
            return "humid"
        if min_humidity <= 30:
            return "dry"
        return "ok"

    @property
    def extra_state_attributes(self):
        return {
            "read_only": True,
            "writes_to_thermostat": False,
            "system_dehumidification_mode": getattr(self._system, "dehumidificationMode", None),
            "system_humidification_mode": getattr(self._system, "humidificationMode", None),
            "enhanced_dehumidification_overcooling_f_enabled": getattr(
                self._system, "enhancedDehumidificationOvercoolingF_enable", None
            ),
            "zones": [
                {
                    "zone_id": zone.id,
                    "name": zone.name,
                    "humidity": zone.getHumidity(),
                    "humidity_mode": getattr(zone, "humidityMode", None),
                    "dehumidify_setpoint": getattr(zone, "desp", None),
                    "humidify_setpoint": getattr(zone, "husp", None),
                }
                for zone in self._system.zone_list
                if zone.is_zone_active()
            ],
        }


class S30DiagSensor(S30BaseEntityMixin, SensorEntity):
    """Diagnostic Data Sensor"""

    def __init__(
        self,
        hass,
        manager: Manager,
        system: lennox_system,
        equipment: lennox_equipment,
        diagnostic: lennox_equipment_diagnostic,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._equipment: lennox_equipment = equipment
        self._diagnostic: lennox_equipment_diagnostic = diagnostic

        self.uom = diagnostic.unit.strip()
        if self.uom == "":
            # Lennox does not provide a unit for RPM
            if self._diagnostic.name.endswith("RPM"):
                self.uom = REVOLUTIONS_PER_MINUTE

        if self.uom == "":
            self._state_class = None
        else:
            self._state_class = SensorStateClass.MEASUREMENT

        suffix = str(self._equipment.equipment_id)
        if self._equipment.equipment_id == 1:
            suffix = "ou"
        elif self._equipment.equipment_id == 2:
            suffix = "iu"
        self._myname = f"{self._system.name}_{suffix}_{self._diagnostic.name}".replace(" ", "_")
        _LOGGER.debug("Create S30DiagSensor myname [%s]", self._myname)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30DiagSensor myname [%s]", self._myname)
        self._system.registerOnUpdateCallbackDiag(
            self.update_callback,
            [f"{self._equipment.equipment_id}_{self._diagnostic.diagnostic_id}"],
        )
        self._system.registerOnUpdateCallback(self.system_update_callback, ["diagLevel"])
        await super().async_added_to_hass()

    def update_callback(self, eid_did, newval):
        """Callback to execute on data change"""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30DiagSSensor myname [%s] value [%s]", self._myname, newval)
        self.schedule_update_ha_state()

    def system_update_callback(self):
        """Callback to execute on system data change"""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("system_update_callback S30DiagSSensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        if self._diagnostic.value == "waiting...":
            return False
        if self._system.diagLevel not in (1, 2):
            return False
        return super().available

    @property
    def native_value(self):
        """Return native value of the sensor."""
        if self._diagnostic.value == "waiting...":
            return None
        if self._state_class == SensorStateClass.MEASUREMENT:
            try:
                _ = float(self._diagnostic.value)
            except ValueError:
                return None
        return self._diagnostic.value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (f"{self._system.unique_id}_{UNIQUE_ID_SUFFIX_DIAG_SENSOR}_{self._equipment.equipment_id}_{self._diagnostic.name}").replace(
            "-", ""
        )

    @property
    def name(self):
        return self._myname

    @property
    def native_unit_of_measurement(self):
        return lennox_uom_to_ha_uom(self.uom)

    @property
    def device_class(self):
        uom = self.native_unit_of_measurement
        if uom == UnitOfTemperature.FAHRENHEIT or uom == UnitOfTemperature.CELSIUS:
            return SensorDeviceClass.TEMPERATURE
        elif uom == UnitOfElectricPotential.VOLT:
            return SensorDeviceClass.VOLTAGE
        elif uom == UnitOfElectricCurrent.AMPERE:
            return SensorDeviceClass.CURRENT
        elif uom == UnitOfFrequency.HERTZ:
            return SensorDeviceClass.FREQUENCY
        return None

    @property
    def state_class(self):
        return self._state_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        equip_device_map = self._manager.system_equip_device_map.get(self._system.sysId)
        if equip_device_map is not None:
            device = equip_device_map.get(self._equipment.equipment_id)
            if device is not None:
                return {
                    "identifiers": {(DOMAIN, device.unique_name)},
                }
            _LOGGER.warning(
                "Unable to find equipment in device map [%s] [%s] [%s] [%s], please raise an issue and post a message log",
                self._equipment.equipment_id,
                self._equipment.equipment_name,
                self._equipment.equipment_type_name,
                self._equipment.equipType,
            )
        else:
            _LOGGER.error(
                "No equipment device map found for sysId [%s] equipment [%s] [%s] [%s] [%s], please raise an issue and post a message log",
                self._system.sysId,
                self._equipment.equipment_id,
                self._equipment.equipment_name,
                self._equipment.equipment_type_name,
                self._equipment.equipType,
            )
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC


class S30OutdoorTempSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_outdoor_temperature"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30OutdoorTempSensor myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            ["outdoorTemperature", "outdoorTemperatureC", "outdoorTemperatureStatus"],
        )
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug("update_callback S30OutdoorTempSensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._system.unique_id + "_OT").replace("-", "")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def name(self):
        return self._myname

    @property
    def available(self):
        if self._system.outdoorTemperatureStatus in LENNOX_BAD_STATUS:
            return False
        return super().available

    @property
    def native_value(self):
        if self._system.outdoorTemperatureStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                "S30OutdoorTempSensor [%s] has bad data quality [%s] returning None",
                self._myname,
                self._system.outdoorTemperatureStatus,
            )
            return None
        if self._manager.is_metric is False:
            return self._system.outdoorTemperature
        return self._system.outdoorTemperatureC

    @property
    def native_unit_of_measurement(self):
        if self._manager.is_metric is False:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id + "_ou")},
        }


class S30TempSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
        zone: lennox_zone,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._zone = zone
        self._myname = self._zone.system.name + "_" + self._zone.name + "_temperature"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30TempSensor myname [%s]", self._myname)
        self._zone.registerOnUpdateCallback(self.update_callback, ["temperature", "temperatureC", "temperatureStatus"])
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug("update_callback S30TempSensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._zone.system.unique_id + "_" + str(self._zone.id)).replace("-", "") + "_T"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def available(self):
        if self._zone.temperatureStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                "S30TempSensor [%s] has bad data quality [%s] returning Not Available",
                self._myname,
                self._zone.temperatureStatus,
            )
            return False
        return super().available

    @property
    def name(self):
        return self._myname

    @property
    def native_value(self):
        if self._zone.temperatureStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                "S30TempSensor [%s] has bad data quality [%s] returning None",
                self._myname,
                self._zone.temperatureStatus,
            )
            return None
        if self._manager.is_metric is False:
            return self._zone.getTemperature()
        return self._zone.getTemperatureC()

    @property
    def native_unit_of_measurement(self):
        if self._manager.is_metric is False:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._zone.unique_id)},
        }


class S30HumiditySensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
        zone: lennox_zone,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._zone = zone
        self._myname = self._zone.system.name + "_" + self._zone.name + "_humidity"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30TempSensor myname [%s]", self._myname)
        self._zone.registerOnUpdateCallback(self.update_callback, ["humidity", "humidityStatus"])
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug("update_callback S30HumiditySensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._zone.system.unique_id + "_" + str(self._zone.id)).replace("-", "") + "_H"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def name(self):
        return self._myname

    @property
    def available(self):
        if self._zone.humidityStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                "S30HumiditySensor [%s] has bad data quality [%s] returning Not Available",
                self._myname,
                self._zone.humidityStatus,
            )
            return False
        return super().available

    @property
    def native_value(self):
        if self._zone.humidityStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                "S30HumiditySensor [%s] has bad data quality [%s] returning None",
                self._myname,
                self._zone.humidityStatus,
            )
            return None
        return self._zone.getHumidity()

    @property
    def native_unit_of_measurement(self):
        return PERCENTAGE

    @property
    def device_class(self):
        return SensorDeviceClass.HUMIDITY

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._zone.unique_id)},
        }


class S30InverterPowerSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 inverter power."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_inverter_energy"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30TempSensor myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            ["diagInverterInputVoltage", "diagInverterInputCurrent"],
        )
        self._system.registerOnUpdateCallback(self.system_update_callback, ["diagLevel"])
        await super().async_added_to_hass()

    def system_update_callback(self):
        """Callback to execute on data change"""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("system_update_callback S30InverterPowerSensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    def update_callback(self):
        """Callback to execute on data change"""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30InverterPowerSensor [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        if self._system.diagLevel not in (1, 2):
            return False
        return super().available

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._system.unique_id + "_IE").replace("-", "")

    @property
    def name(self):
        return self._myname

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def native_value(self):
        if self._system.diagInverterInputVoltage is None or self._system.diagInverterInputCurrent is None:
            _LOGGER.debug("Values are None for diagnostic sensors  [%s]", self._myname)
            return None
        if self._system.diagInverterInputVoltage == "waiting..." or self._system.diagInverterInputCurrent == "waiting...":
            _LOGGER.debug("System is waiting for values for diagnostic sensors [%s]", self._myname)
            return None
        try:
            return int(float(self._system.diagInverterInputVoltage) * float(self._system.diagInverterInputCurrent))
        except ValueError as e:
            _LOGGER.warning(
                "state myname [%s] diagInverterInputVoltage [%s] diagInverterInputCurrent [%s] exception: [%s]",
                self._myname,
                self._system.diagInverterInputVoltage,
                self._system.diagInverterInputCurrent,
                e,
            )
        return None

    @property
    def native_unit_of_measurement(self):
        return UnitOfPower.WATT

    @property
    def device_class(self):
        return SensorDeviceClass.POWER

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._system.unique_id + "_ou")},
        }


class S30AlertSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_alert"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30AlertSensor myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(self.update_callback, ["alert"])
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30AlertSensor myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        return helper_create_system_unique_id(self._system, UNIQUE_ID_SUFFIX_ALERT_SENSOR)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def name(self):
        return self._myname

    @property
    def native_value(self):
        return self._system.alert

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return helper_get_equipment_device_info(self._manager, self._system, 0)


class S30ActiveAlertsList(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_active_alerts"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug("async_added_to_hass S30ActiveAlertList myname [%s]", self._myname)
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "active_alerts",
                "alerts_num_cleared",
                "alerts_last_cleared_id",
                "alerts_num_in_active_array",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("update_callback S30ActiveAlertList myname [%s]", self._myname)
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        return helper_create_system_unique_id(self._system, UNIQUE_ID_SUFFIX_ACTIVE_ALERTS_SENSOR)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs: dict[str, Any] = {}
        attrs["alert_list"] = self._system.active_alerts
        val = self._system.alerts_num_cleared
        attrs["alerts_num_cleared"] = 0 if val is None else val
        val = self._system.alerts_last_cleared_id
        attrs["alerts_last_cleared_id"] = 0 if val is None else val
        val = self._system.alerts_num_in_active_array
        attrs["alerts_num_in_active_array"] = 0 if val is None else val
        return attrs

    @property
    def name(self):
        return self._myname

    @property
    def native_value(self):
        if not self._system.active_alerts:
            return 0
        return len(self._system.active_alerts)

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return helper_get_equipment_device_info(self._manager, self._system, 0)
