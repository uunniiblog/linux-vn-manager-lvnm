import config
import json
import logging
logger = logging.getLogger(__name__)
from datetime import datetime
from prefix_manager import PrefixManager
from runner_manager import RunnerManagerInterface
from pathlib import Path
from dataclasses import asdict
from model.game_card import GameCard, GameScope
from vndb_manager import VndbManager

class GameManager:
    GAME_FILE = config.GAMES_DATA

    @staticmethod
    def add_game(exe, name, prefix, vndb):
        """ Adds a new game entry to the JSON data file. """
        logging.debug(f"add_game exe: {exe} name: {name} prefix: {prefix} vndb: {vndb}")

        # Validate Prefix Existence
        prefix_data = PrefixManager.get_prefix_info(prefix)
        if not prefix_data:
            logging.error(f"Prefix '{prefix}' does not exist in registry.")
            return False

        # Validate Runner Existence
        runner_path = prefix_data.get("runner")
        if not RunnerManagerInterface.is_runner_valid(runner_path):
            logging.error(f"Runner for prefix '{prefix}' is missing at: {runner_path}")
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
        logging.info(f"Successfully added game '{name}'")

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
            logging.info(f"Game '{name}' has been removed from the library.")
            return True
        else:
            logging.debug(f"Game '{name}' not found. Nothing to delete.")
            return False

    @staticmethod
    def update_game(original_name: str, updates: dict):
        """
        Updates an existing game entry
        """
        raw_data = GameManager._load_data()
        
        if original_name not in raw_data:
            logging.error(f"Game '{original_name}' not found. Cannot update.")
            return

        current_card = GameCard.from_dict(original_name, raw_data[original_name])
        current_card.update_date = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        old_vndb = current_card.vndb

        for key, value in updates.items():
            if key == "gamescope"and isinstance(value, dict):
                for gs_key, gs_val in value.items():
                    setattr(current_card.gamescope, gs_key, gs_val)
            elif hasattr(current_card, key):
                setattr(current_card, key, value)

        
        # Fetch if ID changed OR if ID exists but ogtitle is empty
        new_vndb = current_card.vndb
        if new_vndb and (new_vndb != old_vndb or not current_card.ogtitle):
            logging.debug(f"Updating metadata for VNDB ID: {new_vndb}")
            results = VndbManager.fetch_and_store_vn(vndb_id=new_vndb)
            if results and len(results) > 0:
                current_card.ogtitle = VndbManager.get_original_title(results[0])

        new_name = current_card.name
        # Handle renaming: remove the old key if the name changed
        if new_name != original_name:
            del raw_data[original_name]

        # Save under the (potentially new) key
        raw_data[new_name] = current_card.to_dict()
        GameManager._save_data(raw_data)
        logging.info(f"Successfully updated '{new_name}'.")

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
            logging.error(f"Failed to save to {GameManager.GAME_FILE}: {e}")

    @staticmethod
    def get_game(name: str) -> Optional[GameCard]:
        """ Fetches a single game by name and returns it as a GameCard. """
        raw_data = GameManager._load_data()
        data = raw_data.get(name)
        
        if data:
            return GameCard.from_dict(name, data)
        return None

    @staticmethod
    def update_prefix_references(old_name: str, new_name: str):
        """Updates all games in the registry that use a specific prefix."""
        if not GameManager.GAME_FILE.exists():
            return

        logging.info(f"Updating game references: '{old_name}' -> '{new_name}'")
        
        games_data = GameManager._load_data()

        updated_count = 0
        for game_name, details in games_data.items():
            if details.get("prefix") == old_name:
                details["prefix"] = new_name
                details["update_date"] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                updated_count += 1
        
        if updated_count > 0:
            GameManager._save_data(games_data)
            logging.info(f"Updated {updated_count} game(s) to use new prefix name.")
        else:
            logging.info("No games were using this prefix.")

    @staticmethod
    def duplicate_game(name: str):
        """
        Creates a copy of an existing game with a unique name.
        """
        source_card = GameManager.get_game(name)
        if not source_card:
            logging.error(f"Cannot duplicate. Game '{name}' not found.")
            return False

        games_dict = GameManager._load_data()
        
        # Generate a unique name
        base_name = f"{name} (Copy)"
        new_name = base_name
        counter = 1
        
        while new_name in games_dict:
            counter += 1
            new_name = f"{base_name} {counter}"

        # Create the copy
        new_data = source_card.to_dict()
        
        # Update the metadata for the copy
        new_data['name'] = new_name
        new_data['update_date'] = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        new_data['last_played'] = "" # Reset play time for the copy

        games_dict[new_name] = new_data
        GameManager._save_data(games_dict)
        
        logging.info(f"Successfully duplicated '{name}' as '{new_name}'")
        return True