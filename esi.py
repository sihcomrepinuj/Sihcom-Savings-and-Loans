"""EVE Online helpers for type ID lookup and ship images."""

import logging
import urllib.request
import urllib.parse
import json

from config import Config

logger = logging.getLogger(__name__)

FUZZWORK_API = 'https://www.fuzzwork.co.uk/api/typeid.php'
IMAGE_BASE = 'https://images.evetech.net/types'


def search_type_id(ship_name):
    """Look up an EVE type ID by name using Fuzzwork API. Returns type_id or None."""
    url = f'{FUZZWORK_API}?{urllib.parse.urlencode({"typename": ship_name})}'

    req = urllib.request.Request(url, headers={
        'User-Agent': Config.USER_AGENT,
        'Accept': 'application/json',
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.error(f'Fuzzwork lookup failed for "{ship_name}": {e}')
        return None

    if not data:
        logger.warning(f'Fuzzwork returned empty response for "{ship_name}"')
        return None

    # Response is {"typeID": 23773, "typeName": "Ragnarok"}
    type_id = data.get('typeID')
    if type_id and int(type_id) > 0:
        logger.info(f'Fuzzwork: "{ship_name}" -> type_id {type_id}')
        return int(type_id)

    logger.warning(f'Fuzzwork: no type_id found for "{ship_name}"')
    return None


def get_ship_image_url(type_id, size=256):
    """Return the EVE image server URL for a ship render."""
    if not type_id:
        return None
    return f'{IMAGE_BASE}/{type_id}/render?size={size}'
