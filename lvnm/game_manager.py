import config
import json
from datetime import datetime
from prefix_manager import PrefixManager
from runner_manager import RunnerManagerInterface
from pathlib import Path
from dataclasses import asdict
from model.game_card import GameCard, GameScope

class GameManager:
    GAME_FILE = config.GAMES_DATA

    @staticmethod
    def add_game(exe, name, prefix, vndb):
        """ Adds a new game entry to the JSON data file. """

        # Validate Prefix Existence
        prefix_data = PrefixManager.get_prefix_info(prefix)
        if not prefix_data:
            print(f"[Error] Prefix '{prefix}' does not exist in registry.")
            return False

        # Validate Runner Existence
        runner_path = prefix_data.get("runner")
        if not RunnerManagerInterface.is_runner_valid(runner_path):
            print(f"[Error] Runner for prefix '{prefix}' is missing at: {runner_path}")
            return False

        games_dict = GameManager._load_data()

        new_card = GameCard(
            name=name,
            path=str(exe),
            prefix=prefix,
            vndb=vndb
        )
        
        games_dict[name] = new_card.to_dict()
        
        GameManager._save_data(games_dict)
        print(f"Successfully added game '{name}'")

    @staticmethod
    def list_games(name_query=None):
        """
        Returns the games dictionary. 
        """
        raw_data = GameManager._load_data()
        
        # Convert raw dictionaries into GameCard objects
        games_collection = {
            name: GameCard.from_dict(name, data) 
            for name, data in raw_data.items()
        }

        if name_query:
            query = name_query.lower()
            return {
                name: card for name, card in games_collection.items() 
                if query in name.lower()
            }
            
        return games_collection

    @staticmethod
    def delete_game(name):
        """
        Deletes a game entry based on the name key.
        """
        games_dict = GameManager._load_data()

        if name in games_dict:
            del games_dict[name]
            GameManager._save_data(games_dict)
            print(f"Game '{name}' has been removed from the library.")
        else:
            print(f"[Warning] Game '{name}' not found. Nothing to delete.")

    @staticmethod
    def update_game(name: str, updates: dict):
        """
        Updates an existing game entry.
        """
        raw_data = GameManager._load_data()
        
        if name not in raw_data:
            print(f"[Error] Game '{name}' not found. Cannot update.")
            return

        current_card = GameCard.from_dict(name, raw_data[name])
        current_card.update_date = datetime.today().strftime('%Y-%m-%d %H:%M:%S')

        for key, value in updates.items():
            if key == "gamescope" and isinstance(value, dict):
                for gs_key, gs_val in value.items():
                    setattr(current_card.gamescope, gs_key, gs_val)
            elif hasattr(current_card, key):
                setattr(current_card, key, value)

        raw_data[name] = current_card.to_dict()
        GameManager._save_data(raw_data)
        print(f"Successfully updated '{name}'.")

    @staticmethod
    def _load_data():
        """ Internal helper to load JSON data safely """
        if not GameManager.GAME_FILE.exists():
            return {}
        try:
            with open(GameManager.GAME_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    @staticmethod
    def _save_data(data):
        """ Internal helper to save JSON data safely """
        try:
            GameManager.GAME_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(GameManager.GAME_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Error] Failed to save to {GameManager.GAME_FILE}: {e}")

    @staticmethod
    def update_prefix_references(old_name: str, new_name: str):
        """Updates all games in the registry that use a specific prefix."""
        if not GameManager.GAME_FILE.exists():
            return

        print(f"Updating game references: '{old_name}' -> '{new_name}'")
        
        games_data = GameManager._load_data()

        updated_count = 0
        for game_name, details in games_data.items():
            if details.get("prefix") == old_name:
                details["prefix"] = new_name
                details["update_date"] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                updated_count += 1
        
        if updated_count > 0:
            GameManager._save_data(games_data)
            print(f"Updated {updated_count} game(s) to use new prefix name.")
        else:
            print("No games were using this prefix.")