"""ESI helper functions for public (unauthenticated) EVE Online API calls."""

import logging
import urllib.request
import urllib.parse
import json

from config import Config

logger = logging.getLogger(__name__)

ESI_BASE = 'https://esi.evetech.net/latest'
IMAGE_BASE = 'https://images.evetech.net/types'


def _esi_get(path, params=None):
    """Make a GET request to ESI and return parsed JSON, or None on error."""
    url = f'{ESI_BASE}{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        'User-Agent': Config.USER_AGENT,
        'Accept': 'application/json',
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f'ESI request failed: {url} - {e}')
        return None


def search_type_id(ship_name):
    """Search ESI for an inventory type by exact name. Returns type_id or None."""
    data = _esi_get('/search/', {
        'categories': 'inventory_type',
        'search': ship_name,
        'strict': 'true',
    })

    if not data or 'inventory_type' not in data:
        # Try non-strict search and pick first result
        data = _esi_get('/search/', {
            'categories': 'inventory_type',
            'search': ship_name,
        })

    if data and 'inventory_type' in data:
        type_ids = data['inventory_type']
        if len(type_ids) == 1:
            return type_ids[0]
        # Multiple results — try to find exact match
        for tid in type_ids:
            type_info = get_type_info(tid)
            if type_info and type_info.get('name', '').lower() == ship_name.lower():
                return tid
        # Fall back to first result
        return type_ids[0] if type_ids else None

    return None


def get_type_info(type_id):
    """Get type info (name, description, etc.) from ESI."""
    return _esi_get(f'/universe/types/{type_id}/')


def get_ship_image_url(type_id, size=256):
    """Return the EVE image server URL for a ship render."""
    if not type_id:
        return None
    return f'{IMAGE_BASE}/{type_id}/render?size={size}'
