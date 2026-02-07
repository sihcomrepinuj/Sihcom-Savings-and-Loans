import os


class Config:
    # Flask secret key - change this to a random string
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'change-this-to-a-random-string')

    # Database — DATA_DIR lets you point to a persistent volume in production
    DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(__file__))
    DATABASE_PATH = os.path.join(DATA_DIR, 'sihcom.db')

    # EVE Online SSO - register at https://developers.eveonline.com
    EVE_CLIENT_ID = os.environ.get('EVE_CLIENT_ID', 'your-client-id-here')
    EVE_CLIENT_SECRET = os.environ.get('EVE_CLIENT_SECRET', 'your-client-secret-here')
    EVE_CALLBACK_URL = os.environ.get('EVE_CALLBACK_URL', 'http://localhost:5000/callback')

    # Your EVE character ID - this account will be the admin
    ADMIN_CHARACTER_ID = int(os.environ.get('ADMIN_CHARACTER_ID', '0'))

    # User agent for ESI requests
    USER_AGENT = 'Sihcom Savings and Loans (contact: your-eve-name)'
