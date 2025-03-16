"""Support for WeMo switches."""

from datetime import datetime, timedelta
from typing import Any, override

import voluptuous as vol

from pywemo import CoffeeMaker, CrockPot, Insight, Maker, StandbyState, Switch

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_STANDBY, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DOMAIN as WEMO_DOMAIN,
    SERVICE_SET_CROCKPOT_COOK_TIME,
    CrockPotMode,
)
from . import async_wemo_dispatcher_connect
from .coordinator import DeviceCoordinator
from .entity import WemoBinaryStateEntity

SCAN_INTERVAL = timedelta(seconds=10)
PARALLEL_UPDATES = 0

ATTR_COFFEMAKER_MODE = "coffeemaker_mode"
ATTR_CURRENT_STATE_DETAIL = "state_detail"
ATTR_ON_LATEST_TIME = "on_latest_time"
ATTR_ON_TODAY_TIME = "on_today_time"
ATTR_ON_TOTAL_TIME = "on_total_time"
ATTR_POWER_THRESHOLD = "power_threshold_w"
ATTR_SENSOR_STATE = "sensor_state"
ATTR_SWITCH_MODE = "switch_mode"

ATTR_CROCKPOT_MODE = 'crockpot_mode'
ATTR_CROCKPOT_REMAINING_TIME = 'crockpot_remaining_time'
ATTR_CROCKPOT_COOKED_TIME = 'crockpot_cooked_time'

MAKER_SWITCH_MOMENTARY = "momentary"
MAKER_SWITCH_TOGGLE = "toggle"

SERVICE_SET_CROCKPOT_COOK_TIME_SCHEMA = {
    vol.Required("time"): cv.positive_int
}

async def async_setup_entry(
    hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WeMo switches and CrockPots."""

    async def _discovered_wemo(coordinator: DeviceCoordinator) -> None:
        """Handle a discovered Wemo device."""

        if isinstance(coordinator.wemo, CrockPot):
            async_add_entities([WemoCrockPot(coordinator)])
        else:
            async_add_entities([WemoSwitch(coordinator)])

    await async_wemo_dispatcher_connect(hass, _discovered_wemo)

    platform = entity_platform.async_get_current_platform()

    # This will call CrockPot.set_cook_time(time)
    platform.async_register_entity_service(
        SERVICE_SET_CROCKPOT_COOK_TIME, SERVICE_SET_CROCKPOT_COOK_TIME_SCHEMA, WemoCrockPot.set_cook_time.__name__
    )


class WemoSwitch(WemoBinaryStateEntity, SwitchEntity):
    """Representation of a WeMo switch."""

    # All wemo devices used with WemoSwitch are subclasses of Switch.
    wemo: Switch

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the device."""
        attr: dict[str, Any] = {}
        if isinstance(self.wemo, Maker):
            # Is the maker sensor on or off.
            if self.wemo.has_sensor:
                # Note a state of 1 matches the WeMo app 'not triggered'!
                if self.wemo.sensor_state:
                    attr[ATTR_SENSOR_STATE] = STATE_OFF
                else:
                    attr[ATTR_SENSOR_STATE] = STATE_ON

            # Is the maker switch configured as toggle(0) or momentary (1).
            if self.wemo.switch_mode:
                attr[ATTR_SWITCH_MODE] = MAKER_SWITCH_MOMENTARY
            else:
                attr[ATTR_SWITCH_MODE] = MAKER_SWITCH_TOGGLE

        if isinstance(self.wemo, (Insight, CoffeeMaker)):
            attr[ATTR_CURRENT_STATE_DETAIL] = self.detail_state

        if isinstance(self.wemo, Insight):
            attr[ATTR_ON_LATEST_TIME] = self.as_uptime(self.wemo.on_for)
            attr[ATTR_ON_TODAY_TIME] = self.as_uptime(self.wemo.today_on_time)
            attr[ATTR_ON_TOTAL_TIME] = self.as_uptime(self.wemo.total_on_time)
            attr[ATTR_POWER_THRESHOLD] = self.wemo.threshold_power_watts

        if isinstance(self.wemo, CoffeeMaker):
            attr[ATTR_COFFEMAKER_MODE] = self.wemo.mode

        return attr

    @staticmethod
    def as_uptime(_seconds: int) -> str:
        """Format seconds into uptime string in the format: 00d 00h 00m 00s."""
        uptime = datetime(1, 1, 1) + timedelta(seconds=_seconds)
        return (
            f"{uptime.day - 1:0>2d}d {uptime.hour:0>2d}h "
            f"{uptime.minute:0>2d}m {uptime.second:0>2d}s"
        )

    @property
    def detail_state(self) -> str:
        """Return the state of the device."""
        if isinstance(self.wemo, CoffeeMaker):
            return self.wemo.mode_string
        if isinstance(self.wemo, Insight):
            standby_state = self.wemo.standby_state
            if standby_state == StandbyState.ON:
                return STATE_ON
            if standby_state == StandbyState.OFF:
                return STATE_OFF
            if standby_state == StandbyState.STANDBY:
                return STATE_STANDBY
            return STATE_UNKNOWN
        # Unreachable code statement.
        raise RuntimeError

    @property
    @override
    def icon(self) -> str | None:
        """Return the icon of device based on its type."""
        if isinstance(self.wemo, CoffeeMaker):
            return "mdi:coffee"
        return None

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_wemo_call("turn on", self.wemo.on)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_wemo_call("turn off", self.wemo.off)


class WemoCrockPot(WemoSwitch):
    """Representation of a WeMo CrockPot."""

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        attr = {}

        if self.wemo.mode is not None:
            attr[ATTR_CROCKPOT_MODE] = self.wemo.mode
            attr[ATTR_CURRENT_STATE_DETAIL] = self.detail_state
        if self.wemo.remaining_time is not None:
            attr[ATTR_CROCKPOT_REMAINING_TIME] = self.wemo.remaining_time
        if self.wemo.cooked_time is not None:
            attr[ATTR_CROCKPOT_COOKED_TIME] = self.wemo.cooked_time

        return attr

    @property
    def detail_state(self):
        """Return the state of the device."""
        return self.wemo.mode_string

    @property
    def icon(self):
        """Return the icon of the device."""
        return 'mdi:stove'

    @property
    def is_on(self):
        """Return true if CrockPot is on."""
        return self.wemo.mode is not None and self.wemo.mode != CrockPotMode.Off

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self.update_settings(CrockPotMode.High, 360)       # "High" for 6 hours

    def turn_off(self, **kwargs):
        """Turn the switch on."""
        self.update_settings(CrockPotMode.Off, 0)

    def set_cook_time(self, time: int):
        """Update cook time."""
        self.update_settings(self.wemo.mode, time)

    def update_settings(self, mode: int, time: int):
        """Update CrockPot settings."""

        with self._wemo_call_wrapper("update settings"):
            self.wemo.update_settings(mode, time)
            self.wemo.get_state(True)
