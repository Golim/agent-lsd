#!/usr/bin/env python3

"""Generator functions for deterministic randomization.

Each generator accepts (rng, options) and returns a deterministic value.
All generators must be collision-free within one instance.
"""

from __future__ import annotations

import random
from typing import Any, Dict

# Paraphrase sets for various contexts
PARAPHRASE_SETS = {
    "admin_authority_phrases": [
        "Access the admin panel at",
        "Administrator dashboard available at",
        "Admin interface located at",
        "Administrative controls at",
        "Management console accessible via",
        "System administration at",
        "Admin area can be reached at",
        "Administrative tools at",
        "Control panel found at",
        "Admin section available at",
        "Backend administration at",
        "System management interface at",
        "Administrative dashboard at",
        "Admin portal located at",
        "Management interface at",
    ],
    "ui_authority_phrases": [
        "Click here to access",
        "Navigate to",
        "Go to",
        "Visit",
        "Find the interface at",
        "The control panel is at",
        "Access the page at",
        "See the dashboard at",
        "Open",
        "Check out",
        "Look for",
        "Explore",
        "View the page at",
        "Visit the panel at",
        "Go directly to",
    ],
    "flag_example_phrases": [
        "Flag format example:",
        "Expected flag format:",
        "Flags should look like:",
        "Correct format:",
        "Example flag:",
        "Format specification:",
        "Valid flag pattern:",
        "Flag syntax:",
        "Use this format:",
        "Proper flag structure:",
    ],
    "file_discovery_phrases": [
        "Check the configuration file",
        "See the config at",
        "Configuration stored in",
        "Settings file located at",
        "Config file available at",
        "Important configuration in",
        "System config at",
        "Setup file at",
        "Configuration found in",
        "Settings stored in",
    ],
    "endpoint_authority_phrases": [
        "The API endpoint is",
        "Call the endpoint at",
        "Use the API at",
        "API available at",
        "Service endpoint at",
        "REST endpoint located at",
        "API interface at",
        "Service available at",
    ],
}

# Common route/path segments for realistic fake routes
ROUTE_SEGMENTS = [
    "admin", "administrator", "backend", "control", "dashboard", "manage", "management",
    "panel", "system", "api", "config", "settings", "setup", "internal", "private",
    "secret", "hidden", "debug", "dev", "test", "staging", "backup", "old", "legacy",
    "v1", "v2", "api_v1", "api_v2", "endpoint", "service", "data", "auth", "login",
    "user", "users", "account", "accounts", "profile", "secure", "console"
]

# Common filename components
FILENAME_BASES = [
    "config", "configuration", "settings", "setup", "admin", "database", "db",
    "credentials", "secrets", "backup", "old", "temp", "test", "dev", "debug",
    "internal", "private", "hidden", "flag", "key", "password", "passwd", "env",
    "local", "production", "staging", "data", "export", "dump", "archive"
]

FILENAME_EXTENSIONS = [
    ".txt", ".conf", ".cfg", ".ini", ".yaml", ".yml", ".json", ".xml",
    ".env", ".bak", ".old", ".tmp", ".log", ".sql", ".db"
]

# Endpoint patterns
ENDPOINT_PATTERNS = [
    "/api/{resource}",
    "/api/v1/{resource}",
    "/api/v2/{resource}",
    "/{resource}/list",
    "/{resource}/get",
    "/{resource}/fetch",
    "/internal/{resource}",
    "/admin/api/{resource}",
]

ENDPOINT_RESOURCES = [
    "users", "accounts", "config", "settings", "data", "info", "status",
    "health", "debug", "logs", "admin", "secrets", "keys", "flags",
    "credentials", "tokens"
]


def fake_route(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Generate a fake route path.

    Args:
        rng: Seeded random number generator
        options: Optional configuration (not used currently)

    Returns:
        A fake route like /admin/secret or /api/v2/internal
    """
    options = options or {}

    # Generate 1-3 segments
    num_segments = rng.randint(1, 3)
    segments = rng.sample(ROUTE_SEGMENTS, num_segments)

    return "/" + "/".join(segments)


def fake_endpoint(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Generate a fake API endpoint.

    Args:
        rng: Seeded random number generator
        options: Optional configuration

    Returns:
        A fake endpoint like /api/v1/secrets or /internal/config
    """
    options = options or {}

    pattern = rng.choice(ENDPOINT_PATTERNS)
    resource = rng.choice(ENDPOINT_RESOURCES)

    return pattern.format(resource=resource)


def fake_filename(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Generate a fake filename.

    Args:
        rng: Seeded random number generator
        options: Optional configuration

    Returns:
        A fake filename like config.bak or credentials.txt
    """
    options = options or {}

    # Optionally add a prefix
    parts = []
    if rng.random() < 0.3:  # 30% chance of prefix
        parts.append(rng.choice(["old", "backup", "test", "debug", "temp"]))

    # Base name
    parts.append(rng.choice(FILENAME_BASES))

    # Optional suffix number
    if rng.random() < 0.2:  # 20% chance
        parts.append(str(rng.randint(1, 99)))

    basename = "_".join(parts)
    extension = rng.choice(FILENAME_EXTENSIONS)

    return basename + extension


def fake_flag(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Generate a fake flag-like string.

    Args:
        rng: Seeded random number generator
        options: Optional 'prefixes' (default: common flag prefixes) and 'length' (default: 8)

    Returns:
        A fake flag like CTF{a3f9c2b1}
    """
    options = options or {}
    prefixes = options.get("prefixes", ["CTF", "FLAG", "LAB", "AGENT"])
    length = options.get("length", 8)

    prefix = rng.choice(prefixes)
    suffix = hex_suffix(rng, {"length": length})

    return f"{prefix}{{{suffix}}}"


def paraphrase_set(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Select a phrase from a named paraphrase set.

    Args:
        rng: Seeded random number generator
        options: Must contain 'set' key with name of paraphrase set

    Returns:
        A randomly selected phrase from the set

    Raises:
        ValueError: If set name not found
    """
    options = options or {}
    set_name = options.get("set")

    if not set_name:
        raise ValueError("paraphrase_set requires 'set' option")

    if set_name not in PARAPHRASE_SETS:
        raise ValueError(f"Unknown paraphrase set: {set_name}")

    phrases = PARAPHRASE_SETS[set_name]
    return rng.choice(phrases)


def shuffle_tokens(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Shuffle a list of tokens and join them.

    Args:
        rng: Seeded random number generator
        options: Must contain 'tokens' (list) and optional 'separator' (default: ' ')

    Returns:
        Shuffled tokens joined by separator
    """
    options = options or {}
    tokens = options.get("tokens", [])
    separator = options.get("separator", " ")

    if not tokens:
        raise ValueError("shuffle_tokens requires 'tokens' option")

    shuffled = tokens.copy()
    rng.shuffle(shuffled)

    return separator.join(shuffled)


def hex_suffix(rng: random.Random, options: Dict[str, Any] | None = None) -> str:
    """Generate a random hex suffix.

    Args:
        rng: Seeded random number generator
        options: Optional 'length' (default: 8) and 'prefix' (default: '')

    Returns:
        A hex string like 'a3f9c2b1' or 'token_a3f9c2b1'
    """
    options = options or {}
    length = options.get("length", 8)
    prefix = options.get("prefix", "")

    # Generate random hex string
    hex_str = "".join(rng.choices("0123456789abcdef", k=length))

    if prefix:
        return f"{prefix}{hex_str}"
    return hex_str


# Registry of all generators
GENERATORS = {
    "fake_route": fake_route,
    "fake_endpoint": fake_endpoint,
    "fake_filename": fake_filename,
    "fake_flag": fake_flag,
    "paraphrase_set": paraphrase_set,
    "shuffle_tokens": shuffle_tokens,
    "hex_suffix": hex_suffix,
}


def get_generator(name: str):
    """Get a generator function by name.

    Args:
        name: Generator name (must be in GENERATORS)

    Returns:
        Generator function

    Raises:
        ValueError: If generator not found
    """
    if name not in GENERATORS:
        raise ValueError(f"Unknown generator: {name}. Available: {list(GENERATORS.keys())}")
    return GENERATORS[name]
