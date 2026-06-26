"""Tests for read-only Lennox context sensors."""

from custom_components.lennoxs30.sensor import (
    S30AirflowHealthSensor,
    S30AirHandlerDiagnosticsSensor,
    S30EquipmentInventorySensor,
    S30EquipmentParameterInventorySensor,
    S30HeatPumpDiagnosticsSensor,
    S30HumidityIntelligenceSensor,
    S30ScheduleInventorySensor,
)


def test_equipment_inventory_sensor_reports_read_only_equipment_summary(hass, manager):
    system = manager.api.system_list[0]
    sensor = S30EquipmentInventorySensor(hass, manager, system)

    assert sensor.native_value == len(system.equipment)
    attrs = sensor.extra_state_attributes
    assert attrs["read_only"] is True
    assert len(attrs["equipment"]) == len(system.equipment)
    assert attrs["equipment"][0]["equipment_id"] == 0
    assert "parameters_count" in attrs["equipment"][0]
    assert "diagnostics_count" in attrs["equipment"][0]


def test_equipment_parameter_inventory_sensor_exposes_parameter_values_without_write_controls(hass, manager):
    system = manager.api.system_list[0]
    sensor = S30EquipmentParameterInventorySensor(hass, manager, system)

    assert sensor.native_value > 0
    attrs = sensor.extra_state_attributes
    assert attrs["read_only"] is True
    assert "parameter_safety_switch_required_for_writes" in attrs["note"]
    assert attrs["equipment_parameters"]
    first_equipment = attrs["equipment_parameters"][0]
    assert "parameters" in first_equipment
    assert "value" in first_equipment["parameters"][0]


def test_schedule_inventory_sensor_exposes_schedules_as_attributes(hass, manager):
    system = manager.api.system_list[0]
    sensor = S30ScheduleInventorySensor(hass, manager, system)

    assert sensor.native_value == len(system.getSchedules())
    attrs = sensor.extra_state_attributes
    assert attrs["read_only"] is True
    assert attrs["schedules"]
    assert "periods" in attrs["schedules"][0]


def test_heat_pump_and_air_handler_diagnostics_aggregate_existing_diagnostic_values(hass, manager):
    system = manager.api.system_list[0]

    heat_pump = S30HeatPumpDiagnosticsSensor(hass, manager, system)
    assert heat_pump.native_value in ("ok", "waiting", "unavailable")
    assert heat_pump.extra_state_attributes["read_only"] is True

    air_handler = S30AirHandlerDiagnosticsSensor(hass, manager, system)
    assert air_handler.native_value in ("ok", "waiting", "unavailable")
    assert air_handler.extra_state_attributes["read_only"] is True


def test_airflow_health_and_humidity_intelligence_are_read_only_derived_sensors(hass, manager):
    system = manager.api.system_list[0]
    zone = system.zone_list[0]
    zone.humidity = 61
    zone.humidityStatus = "Good"

    airflow = S30AirflowHealthSensor(hass, manager, system)
    assert airflow.native_value in ("ok", "waiting", "unavailable")
    assert airflow.extra_state_attributes["read_only"] is True
    assert airflow.extra_state_attributes["writes_to_thermostat"] is False

    humidity = S30HumidityIntelligenceSensor(hass, manager, system)
    assert humidity.native_value in ("ok", "humid", "dry", "unknown")
    assert humidity.extra_state_attributes["read_only"] is True
    assert humidity.extra_state_attributes["writes_to_thermostat"] is False
