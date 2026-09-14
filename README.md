# leagueapi

A baseline OP.GG-style tracker with in-memory support for:

- Jungle camp respawn timers
- Summoner spell cooldown timers (Flash, Ghost, etc.)
- Champion pick tracking and simple counterpick suggestions

## Baseline usage

```python
from leagueapi import BaselineOPGGTracker

tracker = BaselineOPGGTracker()
tracker.select_champion("Yasuo")
counterpicks = tracker.get_counterpicks()

blue_respawn = tracker.record_jungle_clear("blue_buff", 120)  # 420
enemy_flash_ready = tracker.record_spell_use("enemy_mid", "flash", 100)  # 400
```

## Run tests

```bash
python -m unittest discover -s tests
```
