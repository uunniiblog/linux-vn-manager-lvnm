# linux-vn-manager-lvnm


Attempt at making a visual novel manager for linux. It doesn't really do anything different than other linux game launchers do since at the end of the day it's just a wine/proton wrapper, but I've focused on making life easier for VNs. Main features:

 - Run VNs or any games with proton and wine
 - Download proton-ge and wine (normal and wow64 builds) runners directly from the application
 - Create and manage prefixes with video codecs and winetricks easily from interface
 - Game management to test games easily in all diferent prefixes with useful environment variables for VNs
 - Real time tracking support to have an accurate play count (Only KDE 6 and SteamOS gamescope session)
 - VNDB api integration to get covers and links
 - Pyside QT 6 interface

 ##  AppImage
Releases over here: https://github.com/uunniiblog/linux-vn-manager-lvnm/releases

It bundles umu and winetricks so it runs smoothly in the Steam Deck.

 ## How to use

 1. Runners tab: Download a runner
    - Sub tab for proton runners from steam folder ~/.local/share/Steam/compatibilitytools.d/. Can add proton-ge runners downloaded from GloriousEggroll github.
    - Sub tab for wine runners, they are stored in ~/.local/share/lvnm/runners/wine/. Can add normal amd64 and wow64 builds from Kron4ek github
    - Delete selected: Perma remove it from disk, there is a confirm window
    - To the right of every runner there will be a list of prefixes currently using it.
 2. Prefixex tab: Make a prefix with the runners availables
    - To the right of every prefix there will be a list of games currently using it.
    - Buttons:
        - Create a prefix: Create a new prefix
            <ul>
            <li>Name: Add a identificate name, example: protonge10.25_wmp11_quartz</li>
            <li>Path: locked field, will be stored in ~/.local/share/lvnm/prefixes/ with the name given</li>
            <li>Runner: Select a runner from all the installed runners</li>
            <li>Symlink fonts into prefix: Makes a symlink of the all the fonts folder configured in Settings into the new prefix</li>
            <li>Codecs: Install custom codecs into the prefix from https://www.vnwiki.xyz/linux/special-codecs.html </li>
            <li>Winetricks: Install preconfigured winetricks. They are configured at https://github.com/uunniiblog/linux-vn-manager-lvnm/blob/main/lvnm/config.py in WINETRICKS_LIST </li>
            <li> Umu store and Umu ID for proton runners (not really tested but should work) </li>
            </ul>
        - Edit prefix: Basically same options. I don't recommend to change name/path unless you want to break stuff.
        - Delete prefix: Perma delete a prefix, there is a confirm window.
        - Utility buttons:
            <ul>
            <li>Regedit: Opens windows registry for the prefix</li>
            <li>Winecfg: Opens Wine configuration window for the prefix</li>
            <li>wineboot cmd: Opens windows cmd terminal inside the prefix</li>
            <li>Bash: Opens linux terminal with wine/proton path and WINEPREFIX env variables preloaded at prefix folder</li> 
            </ul>
            All utility options are also available from the game tab

    - Can also right click any prefix for the same options.
    - Note: When a codec or winetricks is installed it cannot be removed, will need to make a new prefix.

3. Games tab: List and run games
    - Add game: Opens sidebar to fill info to add a game
        - Name: name or whatever indicative of the game. Mandatory
        - Path: path to the .exe of the game. click the three dots to open file system picker. Mandatory
        - Prefix: Combo with all prefixes in the application, choose one. Mandatory
        - VNDB: the VNDB id for the game (v11,v12, etc). Will fetch the cover and display vndb/egs link at the top. Optional.
        - Gamescope: Enable/disable gamescope and launch parameters, example: -W 3840 -H 2160 -f -r 60. Can be configured in settings to be filled automatically.
        - Environment Variables: Enable/Disable them as they fit for your game. Mouse over them to show the exact command. Can be configured in settings to be filled automatically. More can be added at https://github.com/uunniiblog/linux-vn-manager-lvnm/blob/main/lvnm/config.py in ENV_VARIABLES
        - Some variables are exclusive to proton/wine, won't show if they don't apply.
    - Edit game: Click one game from the list to show current data to edit. Same fields. Can also Start game from there.
    - Run in prefix: Run a game in a prefix without adding an entry, maybe useful to run some installers quickly. Environment variables will be gotten from global ones at settings.
    - Search: Filter games by name
    - Sort By: sort by name, prefix, last played, or total playtime.
    - Game list
        - Can double click an entry to instantly run the game
        - Can right click an entry to show some extra options as run game, browse files, show logs, duplicate, etc.
        - Three colums:
            <ul>
                <li>Cover: if vndb id is filled it will show real cover, otherwise empty.</li>
                <li>Name: Will show the name, with the prefix and path below. </li>
                <li>Last played date and playtime count</li>
            </ul>
        - Steam/desktop shortcut: Right click an entry to add. The application will be run without gui.
4. Statistics tab: If timetracking has been enabled when you run a game it will count your playtime. This tab shows some simple graphs by app or global based in your playtime.
5. Settings tab
    - Functional Settings:
        - Font folder: Path to a folder with your fonts. This fonts can be symlinked to prefixes to reduce disk space.
        - Gamescope: Enable gamescope and global parameters. When you add a game this setting will be automatically loaded, can be edited later per game as it fit.
        - Global Env Variables: Enable global environt variables checkboxes. When you add a game this setting will be automatically loaded, can be edited later per game as it fit. Will also be used when running a game in "Run in prefix".
    - Appearance Settings:
        - Dark/Light mode
        - Ui scaling
    - Timetracker: Enable/disable it
        - AFK Idle timer: timer to stop counting in case you go afk with the game focused. Requires [swayidle](https://github.com/swaywm/swayidle) to be installed.
        - Periodic save interval: Save the session every X minutes in case of power shutdown or app crash.
    - System info: List useful system info and gstreamer libraries I have found pretty useful to run videos in VNs with wow64 wine builds.

Config and data stored at: ~/.local/share/lvnm/

## Timetracking
Can be enabled in settings.

Timetracking will only track "real" playing time, it will only count the time when the game is focused so it should be somewhat accurate to your real playing time if you don't spend a lot of time in menus. 

It only works in KDE 6. Requires KWin and journalctl to be installed in the system (Tested in SteamOS desktop mode and EndeavourOS with wayland).

Additionally it will also run in Gamescope Gaming mode in SteamOS. In this case it will just count the time the game is open. If you minimize the game to go config controllers or other sections of Steam while game is running it will keep counting,

The tracking data is stored at ~/.local/share/lvnm/tracking/ as csv files with one line per session. If manual intervention is needed you can add/edit/delete lines there manually without issue. The info will be stored as the process name in case the game has a dynamic title window.

I brought the timetracking from another application I made last year, If you want it as a standalone application it is here: https://github.com/uunniiblog/playtimetracker Although it is a bit outdated compared to the version here.

With wayland the way of checking focused windows changes based on Desktop implementations, feel free to request PRs here or in the playtimetracker repo for other desktops. An implementation of DesktopUtilsInterface is all it should be needed. Can also use external libraries if it makes it easier.

## Tools and Credits
Tools used and inspiration:

- umu-launcher: https://github.com/Open-Wine-Components/umu-launcher
- proton-ge: https://github.com/GloriousEggroll/proton-ge-custom/
- wine: https://www.winehq.org/
- Kron4ek wine builds: https://github.com/Kron4ek/Wine-Builds
- Gamescope: https://github.com/ValveSoftware/gamescope
- Winetricks: https://github.com/Winetricks/winetricks/
- Codecs: https://github.com/b-fission/vn_winestuff/
- swayidle: for idle/afk detection: https://github.com/swaywm/swayidle
- kdotool: Inspiration to build the timetracking for KDE: https://github.com/jinliu/kdotool



## Run local
- python -m venv venv
- source venv/bin/activate
- pip install -r requirements.txt
- python lvnm/launcher.py
