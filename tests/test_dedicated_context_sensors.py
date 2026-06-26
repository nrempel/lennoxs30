"""Tests for dedicated read-only diagnostic point sensors."""

from lennoxs30api.lennox_equipment import lennox_equipment_diagnostic

from custom_components.lennoxs30.sensor import (
    S30AirHandlerBlowerCFMDemandSensor,
    S30AirHandlerBlowerPowerSensor,
    S30AirHandlerBlowerRPMSensor,
    S30AirHandlerDischargeAirTemperatureSensor,
    S30HeatPumpCoolingRateSensor,
    S30HeatPumpHeatingRateSensor,
)
from custom_components.lennoxs30.binary_sensor import (
    S30HeatPumpDefrostStatusSensor,
    S30HeatPumpShortCycleDelaySensor,
)


def _set_diag(equipment, diagnostic_id, name, value, unit=""):
    diagnostic = equipment.get_or_create_diagnostic(diagnostic_id)
    diagnostic.name = name
    diagnostic.value = value
    diagnostic.unit = unit
    diagnostic.valid = True
    return diagnostic


def test_dedicated_air_handler_sensors_read_existing_diagnostics(hass, manager):
    system = manager.api.system_list[0]
    air_handler = system.equipment[2]
    _set_diag(air_handler, 1, "Blower CFM Demand", "425", "CFM")
    _set_diag(air_handler, 4, "Indoor Blower RPM", "725", "")
    _set_diag(air_handler, 5, "Indoor Blower Power", "42", "%")
    _set_diag(air_handler, 7, "Discharge Air Temperature", "91", "F")

    cfm = S30AirHandlerBlowerCFMDemandSensor(hass, manager, system)
    rpm = S30AirHandlerBlowerRPMSensor(hass, manager, system)
    power = S30AirHandlerBlowerPowerSensor(hass, manager, system)
    dat = S30AirHandlerDischargeAirTemperatureSensor(hass, manager, system)

    assert cfm.native_value == 425.0
    assert rpm.native_value == 725.0
    assert power.native_value == 42.0
    assert dat.native_value == 91.0
    assert cfm.extra_state_attributes["read_only"] is True
    assert cfm.extra_state_attributes["writes_to_thermostat"] is False


def test_dedicated_heat_pump_sensors_read_existing_diagnostics(hass, manager):
    system = manager.api.system_list[0]
    heat_pump = system.equipment[1]
    _set_diag(heat_pump, 1, "Cooling Rate", "35.5", "%")
    _set_diag(heat_pump, 2, "Heating Rate", "0.0", "%")

    cooling = S30HeatPumpCoolingRateSensor(hass, manager, system)
    heating = S30HeatPumpHeatingRateSensor(hass, manager, system)

    assert cooling.native_value == 35.5
    assert heating.native_value == 0.0
    assert cooling.extra_state_attributes["read_only"] is True
    assert cooling.extra_state_attributes["writes_to_thermostat"] is False


def test_dedicated_heat_pump_binary_sensors_read_existing_diagnostics(hass, manager):
    system = manager.api.system_list[0]
    heat_pump = system.equipment[1]
    _set_diag(heat_pump, 0, "Comp. Short Cycle Delay Active", "Yes", "")
    _set_diag(heat_pump, 7, "Defrost Status", "Yes", "")

    short_cycle = S30HeatPumpShortCycleDelaySensor(hass, manager, system)
    defrost = S30HeatPumpDefrostStatusSensor(hass, manager, system)

    assert short_cycle.is_on is True
    assert defrost.is_on is True
    assert short_cycle.extra_state_attributes["read_only"] is True
    assert short_cycle.extra_state_attributes["writes_to_thermostat"] is False


def test_dedicated_sensors_return_none_when_thermostat_reports_waiting(hass, manager):
    system = manager.api.system_list[0]
    air_handler = system.equipment[2]
    _set_diag(air_handler, 4, "Indoor Blower RPM", "waiting...", "")

    rpm = S30AirHandlerBlowerRPMSensor(hass, manager, system)

    assert rpm.native_value is None
    assert rpm.available is False
