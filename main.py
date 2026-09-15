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

    def get_champion_map(self):
            if self._champion_map is not None:
                return self._champion_map
    
            versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
            versions = self._request_optional_json(versions_url, timeout=10)
            if not versions:
                self._champion_map = {}
                return self._champion_map
    
            latest_version = versions[0]
            self._latest_version = latest_version
            champ_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json"
            data = self._request_optional_json(champ_url, timeout=15)
    
            champ_map = {}
            if data:
                for champion in data.get("data", {}).values():
                    try:
                        champ_map[int(champion.get("key", "0"))] = champion.get("name", champion.get("id", "Unknown"))
                    except ValueError:
                        continue
    
            self._champion_map = champ_map
            return champ_map
    
    
class LeagueDashboardApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("League Dashboard")
        self.root.geometry("1180x760")
        self.root.minsize(1020, 680)

        self.client = RiotClient(RIOT_API_KEY or os.getenv("RIOT_API_KEY", ""))
        self.current_profile = None
        self.current_matches = []
        self.current_live = None
        self.current_live_match_id = None
        self.champion_map = {}
        self.live_event_id = -1
        self.live_timers = {"Baron": 0, "Dragon": 0, "Herald": 0}

        self.api_key_var = tk.StringVar(value=RIOT_API_KEY or os.getenv("RIOT_API_KEY", ""))
        self.region_var = tk.StringVar(value="na1")
        self.name_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Enter a summoner name and search.")

        self.profile_vars = {
            "name": tk.StringVar(value="--"),
            "level": tk.StringVar(value="--"),
            "region": tk.StringVar(value="--"),
            "puuid": tk.StringVar(value="--"),
            "summoner_id": tk.StringVar(value="--"),
        }

        self.ranked_labels = {}
        self.mastery_tree = None
        self.matches_tree = None
        self.match_details = None
        self.live_labels = {}
        self.live_roster = None

        self._setup_style()
        self._build_ui()
        self._poll_live_client()
        self._schedule_live_refresh()

    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#0f1115")
        style.configure("TLabel", background="#0f1115", foreground="#e8e8e8")
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), foreground="#ffffff")
        style.configure("Subheader.TLabel", font=("Segoe UI", 10), foreground="#9ea7b3")
        style.configure("Card.TLabelframe", background="#151922", foreground="#ffffff")
        style.configure("Card.TLabelframe.Label", background="#151922", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 8))
        style.map("Primary.TButton", background=[("active", "#3b82f6")])
        style.configure("Treeview", background="#12151c", fieldbackground="#12151c", foreground="#eaeaea", rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#1d2230", foreground="#ffffff")
        style.map("Treeview", background=[("selected", "#2f5ea8")])

        self.root.configure(background="#0f1115")

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")

        ttk.Label(header, text="League Dashboard", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Search a summoner and get ranked stats, mastery, match history, and live client data.",
            style="Subheader.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        search_bar = ttk.Frame(outer)
        search_bar.pack(fill="x", pady=(0, 14))

        self._labeled_entry(search_bar, "API Key", self.api_key_var, width=44, column=0)
        self._labeled_combo(search_bar, "Region", self.region_var, PLATFORM_REGIONS, width=10, column=1)
        self._labeled_entry(search_bar, "Summoner", self.name_var, width=28, column=2)

        buttons = ttk.Frame(search_bar)
        buttons.grid(row=0, column=3, rowspan=2, padx=(12, 0), sticky="s")
        ttk.Button(buttons, text="Search", style="Primary.TButton", command=self.search_profile).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Clear", command=self.clear_results).pack(side="left")

        search_bar.columnconfigure(0, weight=2)
        search_bar.columnconfigure(1, weight=0)
        search_bar.columnconfigure(2, weight=1)

        self.status_label = ttk.Label(outer, textvariable=self.status_var, style="Subheader.TLabel")
        self.status_label.pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        self.overview_tab = ttk.Frame(notebook, padding=14)
        self.matches_tab = ttk.Frame(notebook, padding=14)
        self.live_tab = ttk.Frame(notebook, padding=14)

        notebook.add(self.overview_tab, text="Overview")
        notebook.add(self.matches_tab, text="Matches")
        notebook.add(self.live_tab, text="Live")

        self._build_overview_tab()
        self._build_matches_tab()
        self._build_live_tab()

    def _labeled_entry(self, parent, label_text, variable, width=24, column=0):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, padx=(0, 10), sticky="nsew")
        ttk.Label(frame, text=label_text, style="Subheader.TLabel").pack(anchor="w")
        entry = ttk.Entry(frame, textvariable=variable, width=width)
        entry.pack(fill="x")
        if label_text == "Summoner":
            entry.bind("<Return>", lambda _event: self.search_profile())
        return entry

    def _labeled_combo(self, parent, label_text, variable, values, width=12, column=0):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=column, padx=(0, 10), sticky="nsew")
        ttk.Label(frame, text=label_text, style="Subheader.TLabel").pack(anchor="w")
        combo = ttk.Combobox(frame, textvariable=variable, values=values, width=width, state="readonly")
        combo.pack(fill="x")
        return combo

    def _build_overview_tab(self):
        top = ttk.Frame(self.overview_tab)
        top.pack(fill="x")

        profile_card = ttk.Labelframe(top, text="Summoner Profile", style="Card.TLabelframe", padding=12)
        profile_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        grid = ttk.Frame(profile_card)
        grid.pack(fill="x")

        fields = [
            ("Summoner", "name"),
            ("Level", "level"),
            ("Region", "region"),
            ("PUUID", "puuid"),
            ("Summoner ID", "summoner_id"),
        ]
        for row, (label_text, key) in enumerate(fields):
            ttk.Label(grid, text=label_text, style="Subheader.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Label(grid, textvariable=self.profile_vars[key]).grid(row=row, column=1, sticky="w", padx=(12, 0), pady=4)

        ranked_card = ttk.Labelframe(top, text="Ranked", style="Card.TLabelframe", padding=12)
        ranked_card.pack(side="left", fill="both", expand=True)

        self.ranked_labels["solo"] = ttk.Label(ranked_card, text="Solo/Duo: --")
        self.ranked_labels["flex"] = ttk.Label(ranked_card, text="Flex: --")
        self.ranked_labels["solo"].pack(anchor="w", pady=(0, 6))
        self.ranked_labels["flex"].pack(anchor="w")

        mastery_card = ttk.Labelframe(self.overview_tab, text="Top Champion Mastery", style="Card.TLabelframe", padding=12)
        mastery_card.pack(fill="both", expand=True, pady=(12, 0))

        self.mastery_tree = ttk.Treeview(mastery_card, columns=("champion", "points", "level"), show="headings", height=10)
        self.mastery_tree.heading("champion", text="Champion")
        self.mastery_tree.heading("points", text="Points")
        self.mastery_tree.heading("level", text="Mastery Level")
        self.mastery_tree.column("champion", width=240, anchor="w")
        self.mastery_tree.column("points", width=120, anchor="center")
        self.mastery_tree.column("level", width=120, anchor="center")
        self.mastery_tree.pack(fill="both", expand=True)

    def _build_matches_tab(self):
        table_card = ttk.Labelframe(self.matches_tab, text="Recent Matches", style="Card.TLabelframe", padding=12)
        table_card.pack(fill="both", expand=True)

        columns = ("queue", "champion", "result", "kda", "cs", "duration", "date")
        self.matches_tree = ttk.Treeview(table_card, columns=columns, show="headings", height=11)
        headings = {
            "queue": "Queue",
            "champion": "Champion",
            "result": "Result",
            "kda": "KDA",
            "cs": "CS",
            "duration": "Duration",
            "date": "Date",
        }
        widths = {
            "queue": 180,
            "champion": 180,
            "result": 90,
            "kda": 100,
            "cs": 80,
            "duration": 100,
            "date": 180,
        }
        for key in columns:
            self.matches_tree.heading(key, text=headings[key])
            self.matches_tree.column(key, width=widths[key], anchor="center")
        self.matches_tree.pack(fill="both", expand=True)
        self.matches_tree.bind("<<TreeviewSelect>>", self.show_selected_match_details)

        detail_card = ttk.Labelframe(self.matches_tab, text="Match Details", style="Card.TLabelframe", padding=12)
        detail_card.pack(fill="both", expand=True, pady=(12, 0))
        self.match_details = scrolledtext.ScrolledText(
            detail_card,
            height=10,
            bg="#12151c",
            fg="#eaeaea",
            insertbackground="#ffffff",
            relief="flat",
            padx=10,
            pady=10,
            wrap="word",
        )
        self.match_details.pack(fill="both", expand=True)
        self.match_details.insert("end", "Search a summoner to see match details here.")
        self.match_details.configure(state="disabled")

    def _build_live_tab(self):
        top = ttk.Frame(self.live_tab)
        top.pack(fill="x")

        live_card = ttk.Labelframe(top, text="Live Client Data", style="Card.TLabelframe", padding=12)
        live_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.live_labels["status"] = ttk.Label(live_card, text="Not connected to an active match.")
        self.live_labels["game_time"] = ttk.Label(live_card, text="Game Time: --:--")
        self.live_labels["player"] = ttk.Label(live_card, text="Player: --")
        self.live_labels["champion"] = ttk.Label(live_card, text="Champion: --")
        self.live_labels["kda"] = ttk.Label(live_card, text="KDA: --")
        self.live_labels["score"] = ttk.Label(live_card, text="Team Score: --")

        for key in ["status", "game_time", "player", "champion", "kda", "score"]:
            self.live_labels[key].pack(anchor="w", pady=2)

        timer_card = ttk.Labelframe(top, text="Objective Timers", style="Card.TLabelframe", padding=12)
        timer_card.pack(side="left", fill="both", expand=True)

        self.live_timers_labels = {}
        for name in self.live_timers:
            lbl = ttk.Label(timer_card, text=f"{name}: 0s")
            lbl.pack(anchor="w", pady=2)
            self.live_timers_labels[name] = lbl

        roster_card = ttk.Labelframe(self.live_tab, text="Team Roster", style="Card.TLabelframe", padding=12)
        roster_card.pack(fill="both", expand=True, pady=(12, 0))
        self.live_roster = scrolledtext.ScrolledText(
            roster_card,
            height=18,
            bg="#12151c",
            fg="#eaeaea",
            insertbackground="#ffffff",
            relief="flat",
            padx=10,
            pady=10,
            wrap="word",
        )
        self.live_roster.pack(fill="both", expand=True)
        self.live_roster.insert("end", "Search a summoner or wait for an active match.")
        self.live_roster.configure(state="disabled")

    def _set_busy(self, busy):
        cursor = "watch" if busy else ""
        self.root.configure(cursor=cursor)
        for child in self.root.winfo_children():
            try:
                child.configure(cursor=cursor)
            except tk.TclError:
                pass
        self.root.update_idletasks()

    def clear_results(self):
        self.current_profile = None
        self.current_matches = []
        self.champion_map = {}
        self.profile_vars["name"].set("--")
        self.profile_vars["level"].set("--")
        self.profile_vars["region"].set("--")
        self.profile_vars["puuid"].set("--")
        self.profile_vars["summoner_id"].set("--")
        self.ranked_labels["solo"].configure(text="Solo/Duo: --")
        self.ranked_labels["flex"].configure(text="Flex: --")
        self._clear_tree(self.mastery_tree)
        self._clear_tree(self.matches_tree)
        self._set_text(self.match_details, "Search a summoner to see match details here.")
        self._set_text(self.live_roster, "Search a summoner or wait for an active match.")
        self.status_var.set("Cleared results.")

    def _clear_tree(self, tree):
        for item in tree.get_children():
            tree.delete(item)

    def _set_text(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", value)
        widget.configure(state="disabled")

    def search_profile(self):
        api_key = self.api_key_var.get().strip()
        summoner_name = self.name_var.get().strip()
        region = self.region_var.get().strip().lower()

        if not api_key:
            messagebox.showerror("Missing API Key", "Paste a Riot API key first.")
            return
        if not summoner_name:
            messagebox.showerror("Missing Summoner", "Enter a summoner name.")
            return

        self.client.set_api_key(api_key)
        self.status_var.set(f"Searching {summoner_name} on {region}...")
        self._set_busy(True)

        worker = threading.Thread(target=self._search_worker, args=(region, summoner_name), daemon=True)
        worker.start()

    def _search_worker(self, region, summoner_name):
        try:
            self._search_impl(region, summoner_name)
        except RiotAPIError as exc:
            message = str(exc)
            self.root.after(0, lambda msg=message: self._on_search_error(msg))
        except Exception as exc:
            message = f"Unexpected error: {exc}"
            self.root.after(0, lambda msg=message: self._on_search_error(msg))

    def _search_impl(self, region, summoner_name):
        profile = self.client.get_summoner_by_name(region, summoner_name)
        ranked = self.client.get_ranked_entries(region, profile["id"])
        masteries = self.client.get_champion_masteries(region, profile["id"], count=5)
        match_ids = self.client.get_match_ids(region, profile["puuid"], count=10)
        match_details = [self.client.get_match_details(region, match_id) for match_id in match_ids]
        champ_map = self.client.get_champion_map()
        live_data = self.client.get_live_client_data()

        parsed_matches = [self._summarize_match(match, profile, champ_map) for match in match_details]
        ranked_summary = self._summarize_ranked(ranked)
        masteries_summary = self._summarize_masteries(masteries, champ_map)
        live_summary = self._summarize_live(live_data, profile)

        result = {
            "region": region,
            "profile": profile,
            "ranked": ranked_summary,
            "masteries": masteries_summary,
            "matches": parsed_matches,
            "live": live_summary,
        }
        self.root.after(0, lambda: self._apply_search_result(result))

    def _summarize_ranked(self, ranked_entries):
        summary = {"solo": "Solo/Duo: Unranked", "flex": "Flex: Unranked"}
        for entry in ranked_entries:
            queue = entry.get("queueType", "")
            text = (
                f"{entry.get('tier', 'UNRANKED')} {entry.get('rank', '')} | "
                f"{entry.get('leaguePoints', 0)} LP | "
                f"{entry.get('wins', 0)}W / {entry.get('losses', 0)}L"
            )
            if queue == "RANKED_SOLO_5x5":
                summary["solo"] = f"Solo/Duo: {text}"
            elif queue == "RANKED_FLEX_SR":
                summary["flex"] = f"Flex: {text}"
        return summary

    def _summarize_masteries(self, masteries, champ_map):
        rows = []
        for mastery in masteries:
            champ_id = mastery.get("championId")
            champ_name = champ_map.get(champ_id, f"Champion {champ_id}")
            rows.append({
                "champion": champ_name,
                "points": mastery.get("championPoints", 0),
                "level": mastery.get("championLevel", 0),
            })
        return rows

    def _summarize_match(self, match, profile, champ_map):
        info = match.get("info", {})
        participants = info.get("participants", [])
        participant = next((p for p in participants if p.get("puuid") == profile.get("puuid")), None)
        if not participant:
            participant = participants[0] if participants else {}

        wins = participant.get("win", False)
        kills = participant.get("kills", 0)
        deaths = participant.get("deaths", 0)
        assists = participant.get("assists", 0)
        cs = participant.get("totalMinionsKilled", 0) + participant.get("neutralMinionsKilled", 0)
        champion = participant.get("championName") or champ_map.get(participant.get("championId"), "Unknown")
        duration = self._format_duration(info.get("gameDuration", 0))
        date = self._format_match_date(info.get("gameCreation", 0))
        queue_name = QUEUE_NAMES.get(info.get("queueId"), f"Queue {info.get('queueId', 'Unknown')}")

        return {
            "match_id": match.get("metadata", {}).get("matchId", "Unknown"),
            "queue": queue_name,
            "champion": champion,
            "result": "Win" if wins else "Loss",
            "kda": f"{kills}/{deaths}/{assists}",
            "cs": cs,
            "duration": duration,
            "date": date,
            "details": self._build_match_details(info, participant, match),
        }

    def _build_match_details(self, info, participant, match):
        perks = participant.get("perks", {}).get("styles", [])
        primary_style = perks[0].get("style") if perks else "Unknown"
        sub_style = perks[1].get("style") if len(perks) > 1 else "Unknown"
        team_id = participant.get("teamId", 0)
        objective = info.get("teams", [])
        teams_text = []
        for team in objective:
            teams_text.append(
                f"Team {team.get('teamId')}: objectives={team.get('objectives', {})}, win={team.get('win', False)}"
            )

        return (
            f"Match ID: {match.get('metadata', {}).get('matchId', 'Unknown')}\n"
            f"Champion: {participant.get('championName', 'Unknown')}\n"
            f"Role: {participant.get('teamPosition', 'Unknown')}\n"
            f"Lane: {participant.get('lane', 'Unknown')}\n"
            f"Team: {team_id}\n"
            f"Kills/Deaths/Assists: {participant.get('kills', 0)}/{participant.get('deaths', 0)}/{participant.get('assists', 0)}\n"
            f"CS: {participant.get('totalMinionsKilled', 0) + participant.get('neutralMinionsKilled', 0)}\n"
            f"Damage to Champions: {participant.get('totalDamageDealtToChampions', 0)}\n"
            f"Vision Score: {participant.get('visionScore', 0)}\n"
            f"Primary Style: {primary_style}\n"
            f"Secondary Style: {sub_style}\n\n"
            f"Team Objectives:\n- " + "\n- ".join(teams_text)
        )

    def _format_duration(self, seconds):
        total = int(seconds or 0)
        minutes = total // 60
        secs = total % 60
        return f"{minutes:02d}:{secs:02d}"

    def _format_match_date(self, epoch_ms):
        if not epoch_ms:
            return "Unknown"
        try:
            return dt.datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Unknown"

    def _summarize_live(self, live_data, profile):
        if not live_data:
            return None

        game_data = live_data.get("gameData", {})
        active_player = live_data.get("activePlayer", {})
        all_players = live_data.get("allPlayers", [])

        player_name = active_player.get("summonerName", profile.get("name", "Unknown"))
        player_team = active_player.get("team")
        if not player_team:
            player = next((p for p in all_players if p.get("summonerName") == player_name), {})
            player_team = player.get("team")

        team_kills = 0
        enemy_kills = 0
        roster_lines = []
        for player in all_players:
            scores = player.get("scores", {})
            line = (
                f"[{player.get('team', 'Unknown')}] {player.get('summonerName', 'Unknown')} - "
                f"{player.get('championName', 'Unknown')} | "
                f"{scores.get('kills', 0)}/{scores.get('deaths', 0)}/{scores.get('assists', 0)}"
            )
            roster_lines.append(line)
            if player.get("team") == player_team:
                team_kills += scores.get("kills", 0)
            else:
                enemy_kills += scores.get("kills", 0)

        events = live_data.get("events", {}).get("Events", [])
        return {
            "game_time": self._format_duration(game_data.get("gameTime", 0)),
            "player": player_name,
            "champion": active_player.get("championName", "Unknown"),
            "kda": f"{active_player.get('scores', {}).get('kills', 0)}/{active_player.get('scores', {}).get('deaths', 0)}/{active_player.get('scores', {}).get('assists', 0)}",
            "score": f"{team_kills} - {enemy_kills}",
            "roster": roster_lines,
            "events": events,
        }

    def _apply_search_result(self, result):
        self.current_profile = result["profile"]
        self.current_matches = result["matches"]
        self.champion_map = self.client.get_champion_map()

        self.profile_vars["name"].set(result["profile"].get("name", "Unknown"))
        self.profile_vars["level"].set(str(result["profile"].get("summonerLevel", "Unknown")))
        self.profile_vars["region"].set(result["region"].upper())
        self.profile_vars["puuid"].set(result["profile"].get("puuid", "Unknown"))
        self.profile_vars["summoner_id"].set(result["profile"].get("id", "Unknown"))

        self.ranked_labels["solo"].configure(text=result["ranked"]["solo"])
        self.ranked_labels["flex"].configure(text=result["ranked"]["flex"])

        self._clear_tree(self.mastery_tree)
        for row in result["masteries"]:
            self.mastery_tree.insert("", "end", values=(row["champion"], row["points"], row["level"]))

        self._clear_tree(self.matches_tree)
        for idx, match in enumerate(result["matches"]):
            self.matches_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(match["queue"], match["champion"], match["result"], match["kda"], match["cs"], match["duration"], match["date"]),
            )

        self.current_live = result["live"]
        self._update_live_tab()
        self.status_var.set(f"Loaded profile for {result['profile'].get('name', 'Unknown')}.")
        self._set_busy(False)

    def _on_search_error(self, message):
        self.status_var.set(message)
        self._set_busy(False)
        messagebox.showerror("Riot API Error", message)

    def show_selected_match_details(self, _event=None):
        selection = self.matches_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        if index < 0 or index >= len(self.current_matches):
            return
        self._set_text(self.match_details, self.current_matches[index]["details"])

    def _update_live_tab(self):
        live = self.current_live
        if not live:
            self.live_labels["status"].configure(text="Not connected to an active match.")
            self.live_labels["game_time"].configure(text="Game Time: --:--")
            self.live_labels["player"].configure(text="Player: --")
            self.live_labels["champion"].configure(text="Champion: --")
            self.live_labels["kda"].configure(text="KDA: --")
            self.live_labels["score"].configure(text="Team Score: --")
            self._set_text(self.live_roster, "No live match detected.")
            for name in self.live_timers_labels:
                self.live_timers_labels[name].configure(text=f"{name}: 0s")
            return

        self.live_labels["status"].configure(text="Live match detected.")
        self.live_labels["game_time"].configure(text=f"Game Time: {live['game_time']}")
        self.live_labels["player"].configure(text=f"Player: {live['player']}")
        self.live_labels["champion"].configure(text=f"Champion: {live['champion']}")
        self.live_labels["kda"].configure(text=f"KDA: {live['kda']}")
        self.live_labels["score"].configure(text=f"Team Score: {live['score']}")
        self._set_text(self.live_roster, "\n".join(live["roster"]))

        self._process_live_events(live.get("events", []))
        for name, seconds in self.live_timers.items():
            self.live_timers_labels[name].configure(text=f"{name}: {seconds}s")

    def _process_live_events(self, events):
        for event in events:
            event_id = event.get("EventID", -1)
            if event_id <= self.live_event_id:
                continue
            self.live_event_id = event_id
            event_name = event.get("EventName", "")
            if event_name == "DragonKill":
                self.live_timers["Dragon"] = 300
            elif event_name == "BaronKill":
                self.live_timers["Baron"] = 420
            elif event_name == "HeraldKill":
                self.live_timers["Herald"] = 360

    def _schedule_live_refresh(self):
        for name in list(self.live_timers):
            if self.live_timers[name] > 0:
                self.live_timers[name] -= 1

        if self.current_live:
            self._update_live_tab()

        self.root.after(1000, self._schedule_live_refresh)

    def _poll_live_client(self):
        live_data = self.client.get_live_client_data()

        if live_data:
            self.current_live = self._summarize_live(live_data, self.current_profile or {})
            if self.current_live is not None:
                self._update_live_tab()
        else:
            if self.current_live is not None:
                self.current_live = None
                self.current_live_match_id = None
                self.live_event_id = -1
                self.live_timers = {"Baron": 0, "Dragon": 0, "Herald": 0}
                self._update_live_tab()

        self.root.after(5000, self._poll_live_client)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    LeagueDashboardApp().run() 