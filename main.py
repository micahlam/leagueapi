import datetime as dt
import json
import os
import ssl
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from urllib import error, parse, request


RIOT_API_KEY = "RGAPI-52db1463-9cc9-41f1-863c-f36b44038a4e"


PLATFORM_REGIONS = [
    "na1",
]

REGIONAL_ROUTING = {
    "na1": "americas",
}

QUEUE_NAMES = {
    420: "Ranked Solo",
    440: "Ranked Flex",
    430: "Normal Blind",
    400: "Normal Draft",
    450: "ARAM",
    700: "Clash",
    900: "URF",
}


class RiotAPIError(Exception):
    pass


class RiotClient:
    def __init__(self, api_key=""):
        self.api_key = api_key.strip()
        self.ssl_context = ssl._create_unverified_context()
        self._champion_map = None
        self._latest_version = None

    def _build_request(self, url, extra_headers=None):
        headers = {
            "X-Riot-Token": self.api_key,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        if extra_headers:
            headers.update(extra_headers)
        return request.Request(url, headers=headers)

    def set_api_key(self, api_key):
        self.api_key = api_key.strip()

    def _base_url(self, platform_region):
        return f"https://{platform_region}.api.riotgames.com"

    def _regional_base_url(self, platform_region):
        routing = REGIONAL_ROUTING.get(platform_region.lower(), "americas")
        return f"https://{routing}.api.riotgames.com"

    def _request_json(self, url, extra_headers=None, timeout=15):
        req = self._build_request(url, extra_headers=extra_headers)
        try:
            with request.urlopen(req, context=self.ssl_context, timeout=timeout) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload)
        except error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                detail = exc.reason

            if exc.code == 403 and "1010" in str(detail):
                raise RiotAPIError(
                    "Riot returned 403/1010. The API key is likely expired, invalid, or blocked. "
                    "Development keys expire every 24 hours. Regenerate the key, make sure it is pasted correctly, "
                    "and confirm you are using the right region for the account."
                ) from exc

            if exc.code == 401:
                raise RiotAPIError(
                    "Riot returned 401 Unauthorized. The API key is missing or invalid. "
                    "Paste a valid Riot API key and try again."
                ) from exc

            if exc.code == 403:
                raise RiotAPIError(
                    "Riot returned 403 Forbidden. The API key is invalid, expired, blacklisted, or not allowed for this request. "
                    "Check the key, region, and endpoint."
                ) from exc

            if exc.code == 429:
                raise RiotAPIError(
                    "Riot returned 429 Rate Limited. Wait for the retry window and try again."
                ) from exc

            raise RiotAPIError(f"Riot API error {exc.code}: {detail}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            raise RiotAPIError(f"Request failed: {exc}") from exc

    def _request_optional_json(self, url, extra_headers=None, timeout=15):
            try:
                return self._request_json(url, extra_headers=extra_headers, timeout=timeout)
            except RiotAPIError:
                return None
    def get_summoner_by_name(self, platform_region, summoner_name):
        encoded_name = parse.quote(summoner_name.strip(), safe="")
        url = f"{self._base_url(platform_region)}/lol/summoner/v4/summoners/by-name/{encoded_name}"
        return self._request_json(url)

    def get_ranked_entries(self, platform_region, encrypted_summoner_id):
        url = f"{self._base_url(platform_region)}/lol/league/v4/entries/by-summoner/{encrypted_summoner_id}"
        return self._request_json(url)

    def get_champion_masteries(self, platform_region, encrypted_summoner_id, count=5):
        url = (
            f"{self._base_url(platform_region)}/lol/champion-mastery/v4/champion-masteries/"
            f"by-summoner/{encrypted_summoner_id}?count={count}"
        )
        return self._request_json(url)

    def get_match_ids(self, platform_region, puuid, count=10):
        url = (
            f"{self._regional_base_url(platform_region)}/lol/match/v5/matches/by-puuid/"
            f"{puuid}/ids?start=0&count={count}"
        )
        return self._request_json(url)

    def get_match_details(self, platform_region, match_id):
        url = f"{self._regional_base_url(platform_region)}/lol/match/v5/matches/{match_id}"
        return self._request_json(url)

    def get_live_client_data(self):
        url = "https://127.0.0.1:2999/liveclientdata/allgamedata"
        req = request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            with request.urlopen(req, context=self.ssl_context, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    