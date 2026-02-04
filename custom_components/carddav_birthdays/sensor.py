"""Sensor platform for CardDAV Birthdays."""
from __future__ import annotations

import logging
from datetime import date, datetime

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CardDavCoordinator, Contact, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CardDAV Birthday sensors."""
    coordinator: CardDavCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Create entities for all contacts initially found
    entities = []
    created_uids = set()

    for contact in coordinator.data:
        entities.append(CardDavBirthdaySensor(coordinator, contact))
        created_uids.add(contact.uid)

    # Add the global "Next Birthday" sensor
    entities.append(CardDavNextBirthdaySensor(coordinator))

    async_add_entities(entities)

    # Listener to add new entities when data updates
    @callback
    def _on_coordinator_update() -> None:
        """Handle updated data from the coordinator."""
        new_entities = []
        current_data = coordinator.data
        if not current_data:
            return
            
        for contact in current_data:
            if contact.uid not in created_uids:
                new_entities.append(CardDavBirthdaySensor(coordinator, contact))
                created_uids.add(contact.uid)
        
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))


class CardDavBirthdaySensor(CoordinatorEntity, SensorEntity):
    """Representation of a CardDAV Birthday Sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:cake"

    def __init__(self, coordinator: CardDavCoordinator, contact: Contact) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.contact = contact
        self._attr_unique_id = f"{contact.uid}_birthday"
        self._attr_name = f"{contact.name} Birthday"
        # We store the UID to map updates back to this entity logic if needed,
        # but since we just read from self.coordinator.data in a loop or find by ID
        # actually CoordinatorEntity just triggers update, we need to find OUR data
        # in the new list.
        
    @property
    def native_value(self) -> date | None:
        """Return the date of the next birthday."""
        return self._get_next_birthday()[0]

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return the state attributes."""
        next_bday, age = self._get_next_birthday()
        return {
            "friendly_name": self.contact.name,
            "original_birthday": self.contact.birthday,
            "age_turning": age,
            "days_until": (next_bday - date.today()).days if next_bday else None
        }
        
    def _get_next_birthday(self) -> tuple[date | None, int | None]:
        """Calculate next birthday and the age they are turning."""
        # Find current contact data in coordinator (in case name/date changed)
        # Optimization: We could cache this or map it better in coordinator
        # but iterating a list of <1000 contacts is usually fast enough.
        
        current_contact = next(
            (c for c in self.coordinator.data if c.uid == self.contact.uid), 
            self.contact
        )
        # Update self.contact in case it changed
        self.contact = current_contact
        
        try:
            # birthday string format depends on vobject.
            # Usually YYYY-MM-DD. Sometimes --MM-DD (no year).
            bday_str = str(self.contact.birthday)
            today = date.today()
            
            # Handle YYYY-MM-DD
            if len(bday_str) >= 10:
                # Naive parsing
                # Some vCards use T timestamp, split at T
                bday_date_part = bday_str.split('T')[0]
                try:
                    bday = datetime.strptime(bday_date_part, "%Y-%m-%d").date()
                    has_year = True
                except ValueError:
                    # Try other formats?
                    return None, None
            elif bday_str.startswith('--'):
                # --MM-DD
                try:
                    # Mock year
                    bday = datetime.strptime(f"2000{bday_str[2:]}", "%Y-%m-%d").date()
                    has_year = False
                except ValueError:
                    return None, None
            else:
                return None, None

            # Calculate next birthday
            try:
                next_bday = bday.replace(year=today.year)
            except ValueError:
                # Feb 29 on non-leap year -> Mar 1 or Feb 28
                # Standard convention varies. Let's say Mar 1.
                next_bday = date(today.year, 3, 1)

            if next_bday < today:
                try:
                    next_bday = bday.replace(year=today.year + 1)
                except ValueError:
                     next_bday = date(today.year + 1, 3, 1)
                     
            age = None
            if has_year:
                age = next_bday.year - bday.year
                
            return next_bday, age

        except Exception:
            return None, None


class CardDavNextBirthdaySensor(CoordinatorEntity, SensorEntity):
    """Sensor that shows the global next birthday."""
    
    _attr_has_entity_name = True
    _attr_name = "Next Birthday"
    _attr_icon = "mdi:calendar-star"
    _attr_device_class = SensorDeviceClass.DATE
    
    def __init__(self, coordinator: CardDavCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = "carddav_next_birthday"

    @property
    def native_value(self) -> date | None:
        """Return the date of the next birthday."""
        next_bday, _, _ = self._get_next_birthday_data()
        return next_bday

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return attributes."""
        next_bday, names, age = self._get_next_birthday_data()
        return {
            "friendly_name": "Next Birthday",
            "names": names,
            "age_turning": age,
            "days_until": (next_bday - date.today()).days if next_bday else None
        }

    def _get_next_birthday_data(self) -> tuple[date | None, list[str], int | None]:
        """Calculate the next global birthday."""
        contacts: list[Contact] = self.coordinator.data
        if not contacts:
            return None, [], None

        today = date.today()
        upcoming = []
        
        for contact in contacts:
            try:
                bday_str = str(contact.birthday)
                
                if len(bday_str) >= 10:
                    bday_date_part = bday_str.split('T')[0]
                    bday = datetime.strptime(bday_date_part, "%Y-%m-%d").date()
                    has_year = True
                elif bday_str.startswith('--'):
                    bday = datetime.strptime(f"2000{bday_str[2:]}", "%Y-%m-%d").date()
                    has_year = False
                else:
                    continue

                try:
                    next_bday = bday.replace(year=today.year)
                except ValueError:
                    next_bday = date(today.year, 3, 1)

                if next_bday < today:
                    try:
                        next_bday = bday.replace(year=today.year + 1)
                    except ValueError:
                         next_bday = date(today.year + 1, 3, 1)
                
                days_diff = (next_bday - today).days
                
                age = None
                if has_year:
                    age = next_bday.year - bday.year
                    
                upcoming.append((days_diff, next_bday, contact.name, age))

            except Exception:
                continue

        if not upcoming:
            return None, [], None
            
        # Sort by days until
        upcoming.sort(key=lambda x: x[0])
        
        # Get the first one (min days)
        min_days = upcoming[0][0]
        
        # Collect all with same min_days
        matches = [x for x in upcoming if x[0] == min_days]
        
        final_date = matches[0][1]
        final_names = [x[2] for x in matches]
        final_ages = [x[3] for x in matches]
        
        # If all ages are same, return one. If different, return list.
        if all(x == final_ages[0] for x in final_ages):
            final_age = final_ages[0]
        else:
            final_age = final_ages

        return final_date, final_names, final_age
