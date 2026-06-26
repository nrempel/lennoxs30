"""Tests for schedule period service handling."""

import json
from unittest.mock import AsyncMock

import pytest
from custom_components.lennoxs30 import DOMAIN, MANAGER, async_set_schedule_period


@pytest.mark.asyncio
async def test_async_set_schedule_period_uses_schedule_name(hass, manager):
    """Service data can target a schedule by name and publish a period update."""
    lsystem = manager.api.system_list[0]
    manager.api.publishMessageHelper = AsyncMock()
    hass.data[DOMAIN] = {manager.config_entry.unique_id: {MANAGER: manager}}

    await async_set_schedule_period(
        hass,
        {
            "schedule": "summer",
            "period": 2,
            "enabled": True,
            "start_time": 21600,
            "system_mode": "heat_cool",
            "heat_setpoint": 64,
            "cool_setpoint": 78,
            "fan_mode": "auto",
        },
    )

    manager.api.publishMessageHelper.assert_awaited_once()
    assert manager.api.publishMessageHelper.await_args[0][0] == lsystem.sysId
    payload = json.loads("{" + manager.api.publishMessageHelper.await_args[0][1] + "}")
    schedule = payload["Data"]["schedules"][0]
    assert schedule["id"] == 1
    period = schedule["schedule"]["periods"][0]
    assert period["id"] == 2
    assert period["enabled"] is True
    assert period["period"]["startTime"] == 21600
    assert period["period"]["systemMode"] == "heat and cool"
    assert period["period"]["hsp"] == 64
    assert period["period"]["csp"] == 78
    assert period["period"]["fanMode"] == "auto"


@pytest.mark.asyncio
async def test_async_set_schedule_period_requires_existing_schedule(hass, manager):
    """Unknown schedule names are rejected before publishing anything."""
    manager.api.publishMessageHelper = AsyncMock()
    hass.data[DOMAIN] = {manager.config_entry.unique_id: {MANAGER: manager}}

    with pytest.raises(Exception, match="Schedule not found"):
        await async_set_schedule_period(hass, {"schedule": "does not exist", "period": 0, "heat_setpoint": 64})

    manager.api.publishMessageHelper.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_schedule_period_rejects_empty_update(hass, manager):
    """A write must include enabled or at least one period field."""
    manager.api.publishMessageHelper = AsyncMock()
    hass.data[DOMAIN] = {manager.config_entry.unique_id: {MANAGER: manager}}

    with pytest.raises(Exception, match="enabled or at least one schedule period field"):
        await async_set_schedule_period(hass, {"schedule": "summer", "period": 0})

    manager.api.publishMessageHelper.assert_not_called()
