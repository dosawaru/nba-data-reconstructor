import json
import logging
import random
import time
from pathlib import Path
from typing import Dict

from nba_api.stats.endpoints import leaguedashplayerstats
from requests.exceptions import ChunkedEncodingError, ConnectionError, ReadTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/player_baselines")
RETRYABLE = (ReadTimeout, ConnectionError, ChunkedEncodingError, ValueError, OSError)


def _cache_path(season: str, cache_dir: Path = CACHE_DIR) -> Path:
    safe = season.replace("/", "-")
    return cache_dir / f"{safe}.json"


def _load_cache(season: str, cache_dir: Path = CACHE_DIR) -> Dict[int, Dict[str, float]] | None:
    path = _cache_path(season, cache_dir)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        baselines: Dict[int, Dict[str, float]] = {}
        for pid, v in raw.items():
            if "ortg" not in v or "net" not in v:
                # Old cache schema without ortg/net — force refresh.
                return None
            baselines[int(pid)] = {
                "drtg": float(v["drtg"]),
                "usage": float(v["usage"]),
                "ortg": float(v["ortg"]),
                "net": float(v["net"]),
            }
        logger.info("Cache hit for player baselines season %s (%d players)", season, len(baselines))
        return baselines
    except Exception as e:
        logger.warning("Bad player-baselines cache for %s: %s", season, e)
        return None


def _save_cache(season: str, baselines: Dict[int, Dict[str, float]], cache_dir: Path = CACHE_DIR) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(season, cache_dir)
    serializable = {str(pid): vals for pid, vals in baselines.items()}
    with path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f)


def _fetch_advanced_stats(season: str, timeout: int = 60) -> Dict[int, Dict[str, float]]:
    stats = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star="Regular Season",
        measure_type_detailed_defense="Advanced",
        per_mode_detailed="PerGame",
        timeout=timeout,
    )
    df = stats.get_data_frames()[0]
    baselines: Dict[int, Dict[str, float]] = {}
    for _, row in df.iterrows():
        player_id = int(row["PLAYER_ID"])
        drtg = row.get("DEF_RATING")
        ortg = row.get("OFF_RATING")
        usg = row.get("USG_PCT")
        net = row.get("NET_RATING")
        if drtg is None or usg is None or ortg is None:
            continue
        try:
            drtg_f = float(drtg)
            ortg_f = float(ortg)
            usg_f = float(usg)
            if net is None:
                net_f = ortg_f - drtg_f
            else:
                net_f = float(net)
        except (TypeError, ValueError):
            continue
        # USG_PCT from Advanced is typically 0–1; feature code expects ~0–100 scale.
        if usg_f <= 1.0:
            usg_f *= 100.0
        baselines[player_id] = {
            "drtg": drtg_f,
            "ortg": ortg_f,
            "usage": usg_f,
            "net": net_f,
        }
    return baselines


def load_player_baselines(
    season: str,
    cache_dir: Path = CACHE_DIR,
    max_retries: int = 3,
) -> Dict[int, Dict[str, float]]:
    """
    Load season player OFF/DEF/NET rating and USG_PCT for feature extraction.
    Uses disk cache under data/cache/player_baselines/. On total API failure
    with no cache, returns {} so callers fall back to league averages.
    """
    cached = _load_cache(season, cache_dir)
    if cached is not None:
        return cached

    last_error: Exception | None = None
    for attempt in range(max_retries):
        logger.info("Fetching advanced player baselines for season %s (attempt %d/%d)", season, attempt + 1, max_retries)
        try:
            baselines = _fetch_advanced_stats(season)
            if not baselines:
                logger.warning("Advanced player stats returned empty for season %s", season)
                return {}
            _save_cache(season, baselines, cache_dir)
            logger.info("Cached %d player baselines for season %s", len(baselines), season)
            return baselines
        except RETRYABLE as e:
            last_error = e
            wait_time = (3 ** attempt) + random.uniform(2.0, 5.0)
            logger.error("Error fetching player baselines for %s: %s", season, e)
            logger.info("Backing off %.1fs before retry", wait_time)
            time.sleep(wait_time)
        except Exception as e:
            last_error = e
            logger.error("Unexpected error fetching player baselines for %s: %s", season, e)
            break

    logger.warning(
        "Failed to load player baselines for %s (%s); using empty map / league-avg fallbacks",
        season,
        last_error,
    )
    return {}


if __name__ == "__main__":
    result = load_player_baselines("2025-26")
    print(f"Loaded {len(result)} players")
    sample = list(result.items())[:3]
    print(sample)
