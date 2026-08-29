"""
db/client.py
────────────
Single responsibility: Create and expose the singleton Supabase client instance.

Inputs:  SUPABASE_URL and SUPABASE_ANON_KEY from config/settings.py.
Outputs: `supabase` — a ready-to-use supabase.Client instance imported by all
         repository modules.
"""

from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_ANON_KEY

# Singleton client — created once on first import, reused everywhere.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
