"""Support for Mode in WeMo CrockPot devices."""
import asyncio

from pywemo import CrockPot

from homeassistant.components.select import (
    SelectEntity,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN as WEMO_DOMAIN,
    CrockPotMode,
    CROCKPOT_MODE_MAP,
)
from . import async_wemo_dispatcher_connect
from .coordinator import DeviceCoordinator
from .entity import WemoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WeMo select entities."""

    async def _discovered_wemo(coordinator: DeviceCoordinator) -> None:
        """Handle a discovered Wemo device."""

        if isinstance(coordinator.wemo, CrockPot):
            async_add_entities(
                [CrockPotModeSelect(coordinator)]
            )

    await async_wemo_dispatcher_connect(hass, _discovered_wemo)


class CrockPotModeSelect(WemoEntity, SelectEntity):
    """WeMo CrockPot Mode Select eneity."""

    _name_suffix = "Mode"

    @property
    def options(self):
        """Return a set of selectable options."""
        return list(CROCKPOT_MODE_MAP.values())

    @property
    def current_option(self):
        """Return the selected entity option to represent the entity state."""
        return self.wemo.mode_string

    def select_option(self, option: str):
        """Change the selected option."""
        mode = list(CROCKPOT_MODE_MAP.keys())[list(CROCKPOT_MODE_MAP.values()).index(option)]

        time = 0
        if mode != CrockPotMode.Off:
            time = self.wemo.remaining_time
            if time == 0:
                if mode == CrockPotMode.High or mode == CrockPotMode.Low:
                    time = 360        # 6 hours for High or Low by default
                else:
                    time = 120        # 2 hours for Warm by default

        with self._wemo_call_wrapper("select option"):
            self.wemo.update_settings(mode, time)
            self.wemo.get_state(True)
