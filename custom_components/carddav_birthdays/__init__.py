"""The CardDAV Birthdays integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import NamedTuple

import aiohttp
import vobject
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class Contact(NamedTuple):
    """Simple contact structure."""
    uid: str
    name: str
    birthday: str  # YYYY-MM-DD or --MM-DD


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CardDAV Birthdays from a config entry."""
    
    url = entry.data[CONF_URL]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    
    coordinator = CardDavCoordinator(hass, session, url, username, password)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class CardDavCoordinator(DataUpdateCoordinator[list[Contact]]):
    """Class to manage fetching CardDAV data."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        session: aiohttp.ClientSession,
        url: str, 
        username: str, 
        password: str
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=12),
        )
        self.session = session
        self.url = url
        self.auth = aiohttp.BasicAuth(username, password)

    async def _async_update_data(self) -> list[Contact]:
        """Fetch data from CardDAV."""
        try:
            return await self._fetch_contacts()
        except Exception as err:
            _LOGGER.exception("Error fetching CardDAV data")
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _fetch_contacts(self) -> list[Contact]:
        """Query the CardDAV server for contacts with birthdays."""
        
        # PROPFIND or REPORT. We use REPORT addressbook-query to filter for BDAY.
        # This is efficient and standard.
        
        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "Depth": "1"
        }
        
        # XML Query to get address-data for cards that have a BDAY property
        body = """
        <C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
            <D:prop>
                <D:getetag/>
                <C:address-data/>
            </D:prop>
            <C:filter>
                <C:prop-filter name="BDAY"/>
            </C:filter>
        </C:addressbook-query>
        """
        
        async with self.session.request(
            "REPORT", 
            self.url, 
            auth=self.auth, 
            data=body, 
            headers=headers
        ) as response:
            if response.status != 207 and response.status != 200:
                 # If REPORT not supported, fallback? 
                 # Radicale supports REPORT. Let's assume it works for now.
                 # If 405, maybe we need to try PROPFIND?
                 # But Step 1 is REPORT.
                 raise UpdateFailed(f"CardDAV REPORT failed: {response.status}")
            
            text = await response.text()
            
        # Parse XML and vCards in executor to avoid blocking the loop
        return await self.hass.async_add_executor_job(self._parse_contacts, text)

    def _parse_contacts(self, xml_text: str) -> list[Contact]:
        """Parse the XML response and contained vCards."""
        contacts: list[Contact] = []
        import xml.etree.ElementTree as ET
        
        try:
            # Remove namespaces (hacky but effective) or just ignore them
            # For robustness we can just parse normally.
            root = ET.fromstring(xml_text)
            
            # Find all address-data elements. 
            # Namespace map is usually {urn:ietf:params:xml:ns:carddav}
            # We can use wildcard if we are lazy, or specific namespace.
            # Let's use wildcard to be safe against server variations.
            address_data_elements = root.findall(".//{urn:ietf:params:xml:ns:carddav}address-data")
            
            for elem in address_data_elements:
                if not elem.text:
                    continue
                    
                vcard_str = elem.text
                try:
                    vcard = vobject.readOne(vcard_str)
                    
                    # Extract UID
                    uid = None
                    if 'uid' in vcard.contents:
                         uid = vcard.contents['uid'][0].value
                    
                    if not uid:
                         continue
                         
                    # Extract Name (FN)
                    fn = "Unknown"
                    if 'fn' in vcard.contents:
                        fn = vcard.contents['fn'][0].value
                    
                    # Extract BDAY
                    if 'bday' in vcard.contents:
                        bday_value = vcard.bday.value
                        contacts.append(Contact(uid=uid, name=fn, birthday=str(bday_value)))
                        
                except Exception as e:
                    _LOGGER.warning(f"Failed to parse vCard: {e}")
                    continue
                    
        except ET.ParseError as e:
             _LOGGER.error(f"Failed to parse XML response: {e}")
             raise UpdateFailed("Invalid XML from server")

        return contacts
