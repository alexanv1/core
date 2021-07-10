"""Support for WeMo switches."""
import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON, STATE_STANDBY, STATE_UNKNOWN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import convert

from .const import (
    DOMAIN as WEMO_DOMAIN,
    SERVICE_UPDATE_CROCKPOT_SETTINGS,
)
from .entity import WemoSubscriptionEntity

SCAN_INTERVAL = timedelta(seconds=10)
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

# The WEMO_ constants below come from pywemo itself
ATTR_SENSOR_STATE = "sensor_state"
ATTR_SWITCH_MODE = "switch_mode"
ATTR_CURRENT_STATE_DETAIL = "state_detail"
ATTR_COFFEMAKER_MODE = "coffeemaker_mode"

ATTR_CROCKPOT_MODE = 'crockpot_mode'
ATTR_CROCKPOT_REMAINING_TIME = 'crockpot_remaining_time'
ATTR_CROCKPOT_COOKED_TIME = 'crockpot_cooked_time'

MAKER_SWITCH_MOMENTARY = "momentary"
MAKER_SWITCH_TOGGLE = "toggle"

WEMO_ON = 1
WEMO_OFF = 0
WEMO_STANDBY = 8


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up WeMo switches and CrockPots."""
    crockpots = []

    async def _discovered_wemo(device):
        """Handle a discovered Wemo device."""
        if device.model_name == 'Crockpot':
            entity = CrockPot(device)
            crockpots.append(entity)
            async_add_entities([entity])
        else:
            async_add_entities([WemoSwitch(device)])

    async_dispatcher_connect(hass, f"{WEMO_DOMAIN}.switch", _discovered_wemo)

    await asyncio.gather(
        *[
            _discovered_wemo(device)
            for device in hass.data[WEMO_DOMAIN]["pending"].pop("switch")
        ]
    )

    def handle_crockpot_update_settings(service):

        entity_ids = service.data.get(ATTR_ENTITY_ID)
        crockpots_service = [entity for entity in crockpots if entity.entity_id in entity_ids]

        mode = service.data.get('mode', 0)
        time = service.data.get('time', 0)

        for crockpot in crockpots_service:
            crockpot.update_settings(mode, time)

    # Register service(s)
    hass.services.async_register(
        WEMO_DOMAIN, SERVICE_UPDATE_CROCKPOT_SETTINGS, handle_crockpot_update_settings
    )


class WemoSwitch(WemoSubscriptionEntity, SwitchEntity):
    """Representation of a WeMo switch."""

    def __init__(self, device):
        """Initialize the WeMo switch."""
        super().__init__(device)
        self.insight_params = None
        self.maker_params = None
        self.coffeemaker_mode = None
        self._mode_string = None

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        attr = {}
        if self.maker_params:
            # Is the maker sensor on or off.
            if self.maker_params["hassensor"]:
                # Note a state of 1 matches the WeMo app 'not triggered'!
                if self.maker_params["sensorstate"]:
                    attr[ATTR_SENSOR_STATE] = STATE_OFF
                else:
                    attr[ATTR_SENSOR_STATE] = STATE_ON

            # Is the maker switch configured as toggle(0) or momentary (1).
            if self.maker_params["switchmode"]:
                attr[ATTR_SWITCH_MODE] = MAKER_SWITCH_MOMENTARY
            else:
                attr[ATTR_SWITCH_MODE] = MAKER_SWITCH_TOGGLE

        if self.insight_params or (self.coffeemaker_mode is not None):
            attr[ATTR_CURRENT_STATE_DETAIL] = self.detail_state

        if self.insight_params:
            attr["on_latest_time"] = WemoSwitch.as_uptime(self.insight_params["onfor"])
            attr["on_today_time"] = WemoSwitch.as_uptime(self.insight_params["ontoday"])
            attr["on_total_time"] = WemoSwitch.as_uptime(self.insight_params["ontotal"])
            attr["power_threshold_w"] = (
                convert(self.insight_params["powerthreshold"], float, 0.0) / 1000.0
            )

        if self.coffeemaker_mode is not None:
            attr[ATTR_COFFEMAKER_MODE] = self.coffeemaker_mode

        return attr

    @staticmethod
    def as_uptime(_seconds):
        """Format seconds into uptime string in the format: 00d 00h 00m 00s."""
        uptime = datetime(1, 1, 1) + timedelta(seconds=_seconds)
        return "{:0>2d}d {:0>2d}h {:0>2d}m {:0>2d}s".format(
            uptime.day - 1, uptime.hour, uptime.minute, uptime.second
        )

    @property
    def current_power_w(self):
        """Return the current power usage in W."""
        if self.insight_params:
            return convert(self.insight_params["currentpower"], float, 0.0) / 1000.0

    @property
    def today_energy_kwh(self):
        """Return the today total energy usage in kWh."""
        if self.insight_params:
            miliwatts = convert(self.insight_params["todaymw"], float, 0.0)
            return round(miliwatts / (1000.0 * 1000.0 * 60), 2)

    @property
    def detail_state(self):
        """Return the state of the device."""
        if self.coffeemaker_mode is not None:
            return self._mode_string
        if self.insight_params:
            standby_state = int(self.insight_params["state"])
            if standby_state == WEMO_ON:
                return STATE_ON
            if standby_state == WEMO_OFF:
                return STATE_OFF
            if standby_state == WEMO_STANDBY:
                return STATE_STANDBY
            return STATE_UNKNOWN

    @property
    def icon(self):
        """Return the icon of device based on its type."""
        if self.wemo.model_name == "CoffeeMaker":
            return "mdi:coffee"
        return None

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        with self._wemo_exception_handler("turn on"):
            if self.wemo.on():
                self._state = WEMO_ON

        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn the switch off."""
        with self._wemo_exception_handler("turn off"):
            if self.wemo.off():
                self._state = WEMO_OFF

        self.schedule_update_ha_state()

    def _update(self, force_update=True):
        """Update the device state."""
        with self._wemo_exception_handler("update status"):
            self._state = self.wemo.get_state(force_update)

            if self.wemo.model_name == "Insight":
                self.insight_params = self.wemo.insight_params
                self.insight_params["standby_state"] = self.wemo.get_standby_state
            elif self.wemo.model_name == "Maker":
                self.maker_params = self.wemo.maker_params
            elif self.wemo.model_name == "CoffeeMaker":
                self.coffeemaker_mode = self.wemo.mode
                self._mode_string = self.wemo.mode_string

class CrockPot(WemoSwitch):
    """Representation of a WeMo CrockPot."""

    def __init__(self, device):
        """Initialize the WeMo switch."""
        WemoSwitch.__init__(self, device)
        self.crockpot_mode = None
        self.crockpot_remaining_time = None
        self.crockpot_cooked_time = None

        # The crockpot may sometimes disconnect briefly and reconnect
        # Ignore this for brief periods to avoid the switch reporting as off intermittently
        self._ignoreUnavailableCounter = 0

        # After a reconnect, the crockpot may indicate that its state is turned off during the first couple of updates
        # We want to ignore these so ignore the first 2 updates that switch the mode to 0
        self._ignoreUpdatesCounter = 0

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the device."""
        attr = {}

        if self.crockpot_mode is not None:
            attr[ATTR_CROCKPOT_MODE] = self.crockpot_mode
            attr[ATTR_CURRENT_STATE_DETAIL] = self.detail_state
        if self.crockpot_remaining_time is not None:
            attr[ATTR_CROCKPOT_REMAINING_TIME] = self.crockpot_remaining_time
        if self.crockpot_cooked_time is not None:
            attr[ATTR_CROCKPOT_COOKED_TIME] = self.crockpot_cooked_time

        return attr

    @property
    def detail_state(self):
        """Return the state of the device."""
        if self.crockpot_mode is not None:
            return self._mode_string

    @property
    def available(self):
        """Return true if switch is available."""
        if not self._available:
            if self._ignoreUnavailableCounter < 3:
                _LOGGER.warning('Switch not available but ignoring for now. _ignoreUnavailableCounter=' + str(self._ignoreUnavailableCounter))
                self._ignoreUnavailableCounter = self._ignoreUnavailableCounter + 1
                return True

        return self._available

    @property
    def icon(self):
        return 'mdi:stove'

    @property
    def is_on(self):
        """Return true if switch is on. Standby is on."""
        return self.crockpot_mode is not None and int(self.crockpot_mode) > 0

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        self.update_settings("52", "360")       # "High" for 6 hours

    def turn_off(self, **kwargs):
        """Turn the switch off."""
        WemoSwitch.turn_off(self)
        # Make sure the state updates aren't ignored since the update was triggered by HASS
        self._ignoreUpdatesCounter = 2

    def update_settings(self, mode, time):
        """Update CrockPot settings."""
    
        try:
            self.wemo.update_settings(mode, time)

            if int(mode) == 0:
                # Make sure the state updates aren't ignored since the update was triggered by HASS
                self._ignoreUpdatesCounter = 2
            else:
                # Ignore state updates where state=Off since slow cooker sometimes reports wrong values when turning on
                self._ignoreUpdatesCounter = 0
        except ActionException as err:
            _LOGGER.warning("Error while updating settings for %s (%s)", self.name, err)
            self._available = False

        self._update(True)
        self.schedule_update_ha_state()

    def _update(self, force_update):
        """Update the device state."""
        try:
            state = self.wemo.get_state(force_update)
            updateState = True

            if (self.crockpot_mode is None or self.crockpot_mode != "0") and self.wemo.mode == "0":
                if self._ignoreUpdatesCounter != 2:
                    updateState = False
                    self._ignoreUpdatesCounter = self._ignoreUpdatesCounter + 1
                    _LOGGER.warning('Ignoring state update. _ignoreUpdatesCounter=' + str(self._ignoreUpdatesCounter))
                else:
                    self._ignoreUpdatesCounter = 0
            else:
                self._ignoreUpdatesCounter = 0

            if updateState:
                self._state = state
                self._mode_string = self.wemo.mode_string
                self.crockpot_mode = self.wemo.mode
                self.crockpot_remaining_time = self.wemo.remaining_time
                self.crockpot_cooked_time = self.wemo.cooked_time

            if not self._available:
                _LOGGER.warning('Reconnected to %s', self.name)
                self._available = True
                self._ignoreUnavailableCounter = 0
        except (AttributeError, ActionException) as err:
            _LOGGER.warning("Could not update status for %s (%s)", self.name, err)
            self._available = False
            self.wemo.reconnect_with_device()