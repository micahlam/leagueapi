"""Baseline OP.GG-like tracker features.

This module provides a small in-memory baseline for:
- jungle camp respawn tracking
- summoner spell cooldown tracking
- champion pick + counterpick lookup
"""

from __future__ import annotations

from dataclasses import dataclass, field


JUNGLE_CAMPS_RESPAWN_SECONDS = {
    "blue_buff": 300,
    "red_buff": 300,
    "gromp": 150,
    "wolves": 150,
    "raptors": 150,
    "krugs": 150,
    "scuttle": 210,
    "dragon": 300,
    "rift_herald": 360,
    "baron": 360,
}

SUMMONER_SPELL_COOLDOWNS_SECONDS = {
    "flash": 300,
    "ghost": 240,
    "heal": 240,
    "ignite": 180,
    "teleport": 360,
    "barrier": 180,
    "cleanse": 210,
    "exhaust": 210,
    "smite": 90,
}

CHAMPION_COUNTERPICKS = {
    "yasuo": ["renekton", "pantheon", "malphite"],
    "zed": ["lissandra", "malzahar", "galio"],
    "lee sin": ["warwick", "rammus", "trundle"],
    "vayne": ["caitlyn", "draven", "ashe"],
}


@dataclass
class BaselineOPGGTracker:
    """A small baseline tracker for match insights and timers."""

    selected_champion: str | None = None
    jungle_respawn_timers: dict[str, int] = field(default_factory=dict)
    spell_ready_timers: dict[str, dict[str, int]] = field(default_factory=dict)

    def select_champion(self, champion_name: str) -> None:
        """Store the picked champion."""
        self.selected_champion = champion_name.strip().lower()

    def get_counterpicks(self) -> list[str]:
        """Return baseline counterpick suggestions for selected champion."""
        if not self.selected_champion:
            return []
        return CHAMPION_COUNTERPICKS.get(self.selected_champion, [])

    def record_jungle_clear(self, camp: str, cleared_at: int) -> int:
        """Record jungle camp clear time and return next respawn timestamp."""
        camp_key = camp.strip().lower()
        if camp_key not in JUNGLE_CAMPS_RESPAWN_SECONDS:
            raise ValueError(f"Unsupported jungle camp: {camp}")

        respawn_at = cleared_at + JUNGLE_CAMPS_RESPAWN_SECONDS[camp_key]
        self.jungle_respawn_timers[camp_key] = respawn_at
        return respawn_at

    def get_jungle_respawn(self, camp: str) -> int | None:
        """Get known respawn timestamp for a jungle camp."""
        return self.jungle_respawn_timers.get(camp.strip().lower())

    def record_spell_use(self, player: str, spell: str, used_at: int) -> int:
        """Track spell usage and return next ready timestamp."""
        spell_key = spell.strip().lower()
        if spell_key not in SUMMONER_SPELL_COOLDOWNS_SECONDS:
            raise ValueError(f"Unsupported summoner spell: {spell}")

        player_key = player.strip().lower()
        ready_at = used_at + SUMMONER_SPELL_COOLDOWNS_SECONDS[spell_key]
        self.spell_ready_timers.setdefault(player_key, {})[spell_key] = ready_at
        return ready_at

    def get_spell_ready_at(self, player: str, spell: str) -> int | None:
        """Get known ready timestamp for a tracked player spell."""
        player_spells = self.spell_ready_timers.get(player.strip().lower(), {})
        return player_spells.get(spell.strip().lower())

    def is_spell_ready(self, player: str, spell: str, current_time: int) -> bool:
        """Return True if current_time is at/after ready timestamp."""
        ready_at = self.get_spell_ready_at(player, spell)
        return ready_at is not None and current_time >= ready_at
