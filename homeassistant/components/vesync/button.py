"""Support for VeSync buttons."""

import logging

from pyvesync.base_devices.vesyncbasedevice import VeSyncBaseDevice
from pyvesync.device_container import DeviceContainer

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .common import is_purifier
from .const import VS_DEVICES, VS_DISCOVERY
from .coordinator import VesyncConfigEntry, VeSyncDataCoordinator
from .entity import VeSyncBaseEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VesyncConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button platform."""

    coordinator = config_entry.runtime_data

    @callback
    def discover(devices):
        """Add new devices to platform."""
        _setup_entities(devices, async_add_entities, coordinator)

    config_entry.async_on_unload(
        async_dispatcher_connect(hass, VS_DISCOVERY.format(VS_DEVICES), discover)
    )

    _setup_entities(config_entry.runtime_data.manager.devices, async_add_entities, coordinator)


@callback
def _setup_entities(
    devices: DeviceContainer | list[VeSyncBaseDevice],
    async_add_entities,
    coordinator: VeSyncDataCoordinator,
):
    """Check if device is an air purifier and add additional entities."""
    entities: list[VeSyncBaseEntity] = []
    for dev in devices:
        if is_purifier(dev):
            entities.append(VeSyncAirPurifierResetFilter(dev, coordinator))

    async_add_entities(entities, update_before_add=True)

class VeSyncAirPurifierResetFilter(VeSyncBaseEntity, ButtonEntity):
    """Representation of a button for configuring reseting VeSync Air Purifier filter life to 100%."""

    def __init__(
        self, humidifier: VeSyncBaseDevice, coordinator: VeSyncDataCoordinator
    ) -> None:
        """Initialize the VeSync humidifier device."""
        super().__init__(humidifier, coordinator)

    @property
    def entity_category(self):
        """Return the configuration entity category."""
        return EntityCategory.CONFIG
    
    @property
    def unique_id(self):
        """Return the ID of this button."""
        return f"{super().unique_id}-reset-filter"
    
    @property
    def name(self):
        """Return the name of this button."""
        return f"Reset Filter Life"
    
    async def async_press(self) -> None:
        await self.device.reset_filter()
        await self.device.update()
        self.schedule_update_ha_state(force_refresh=True)
