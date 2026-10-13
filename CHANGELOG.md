# Changelog

Notable changes for each release are listed below, newest first.

## [v0.6.1]
- Added new option in settings to automatically increase the DPI temporaly when running wine utilities like regedit or winecfg in >1080p monitors for better visibility.
- Fix monitor's detection in flatpak, should work good for KDE, needs testing in other DE.
- PC-98 fixes: Enable retroarch SDL for controller support in flatpak PC-98 config, enables virtual keyboard, save all configuration to the `/home/uni/.local/share/lvnm/emulation/pc98/profiles/`folder to keep it tracked, improve multi disk naming detection.

## [v0.6.0]
- Flatpak release:
    - New Flatpak release, it bundles everything the application uses except gamescope (You need to install gamescope flatpak to use it). Every feature so far in the application should still work as normal.
    - Aditionally it also bundles both 32 and 64 bit gstreamer libraries, meaning a lot of VNs videos will play using the wine builds in the application without you needing to install the 32 bit gstreamer libraries in your system or use wow64 wine builds.
    - It has Japanese locale already bundled, it will still need the **LANG=ja_JP.UTF-8** for games, but shouldn't be needed to modify the locale.gen file or enable JP language for flatpak.
    - **linux-rt-upscaler** is also bundled (still uses normal system configuration), so you can use it without installing system wide, added a button in settings to open the UI for configuration. Should be useful in systems like the Steam Deck.
    - This is probably the most clean way to use the program now, moreso if you only use it for VNs. The install size is obviously a lot bigger than the appimage, it's about ~500Mb, plus the shared platform components. Flatpak releases do lag behind in performance with native system libraries, but for VNs this is a non issue. 
    - Needs manual install, download the .flatpak release and install with `flatpak install --user LVNM-x86_64.flatpak`

- Windows version:
    - Added a new compiled version of the launcher for Windows.
    - It should hide all specific linux features.
    - Supports: Timetracking, Gdrive save syncing and emulation.
    - It's very barebones and lacks any specific Windows features, but should be handy if you play VNs between Windows and a Steam Deck (or any linux system) and want to sync your savedata seamlessly between systems.
    * Note: Tested in Windows 10, I don't really use Windows anymore so there may be issues I have missed, feel free to report them.

- PC-98 Support added in emulation.
    - Preinstalled in flatpak release.
    - Outside of flatpak needs retroarch and the NP2kai core, can be downloaded from [Linux](https://buildbot.libretro.com/nightly/linux/x86_64/latest/np2kai_libretro.so.zip) or [Windows](https://buildbot.libretro.com/nightly/windows/x86_64/latest/np2kai_libretro.dll.zip) or compiled from https://github.com/AZO234/NP2kai. Configure the fields for windows/linux
        - Custom RetroArch: C:\...\retroarch.exe
        - Custom NP2kai core: C:\...\np2kai_libretro.dll
        - BIOS/font folder: C:\...\system\np2kai

    - Existing `.cmd` files are passed directly to NP2kai, allowing manual media configuration for unusual games.
    - Selecting the first floppy of a multidisk game automatically detects the other disks with the same name and creates a NP2kai `.cmd` file that mounts the complete set.
    - `.m3u` playlists are read by LVNM and converted into a NP2kai `.cmd` file, since some games need several floppy images mounted at the same time instead of normal playlist disk swapping.
    - Selecting a hard disk image automatically attaches an unambiguous CD image from the same folder. Selecting a CD image similarly looks for a companion hard disk or boot floppy set.
    - Generated `.cmd` files are saved in `~/.local/share/lvnm/emulation/pc98/media/`. They contain absolute paths to the original game images and are recreated when needed; the original files are not modified.
    - If several possible hard disks, CDs, or floppy sets are found, LVNM asks for a manually created `.cmd`. CD installation itself may still need to be completed interactively inside the emulated PC-98.

- Timetracking:
    - Updated kde_utils: Now it will load a kwin script that reports to the launcher windows and focus changes. Before this the launcher constantly executed scripts to poll the current focus. Not really noticeable in modern PCs but it's way more clean and performant implementation. The script is unloaded when you close the launcher or exit session.
    - Added gnome_utils: Allows to track native waylands windows for the timetracker. Requires to install an [extension](https://github.com/uunniiblog/linux-vn-manager-lvnm/blob/main/lvnm/assets/gnome_extension/lvnm-window-tracker%40linux-vn-manager-lvnm/extension.js), in settings tab the option to install it should appear if you are using a gnome desktop. The extension can be managed with gnome-extensions commands. Without installing the extension it will still use the Xwayland fallback.
    - Added hyprland_utils: Allows the timetracker to work in hyprland desktops.
    - Added existence check every minute: If the window ID being tracked dissappears but the game is still running it looks for it again. Useful in some rare cases where minimizing or changing to fullscreen gives results in the compositor giving the game window a new ID.  
    * Note: Both gnome and hyprland implementations are done fully by GPT-5.6-Sol, tested in an old laptop and it was working fine, but I don't use this two desktops so there may be issues I haven't found in my light testing. If you have issues feel free to open an issue with debug logs enabled.

- Savedata:
    - New modal to select the save folder.
    - Now you can select multiple folders or individual files as savedata, useful for some games where the savedata is a single file in the game folder.
    - When you select a folder, now you can also select individual files to exclude, avoiding syncing configuration files that you don't want to sync between different PCs.

- Registry options:
    - Added a registry path in advanced settings.
    - It has an auto detection setting, but if it doesn't work you will need to manually input the registry path like the placeholder.
    - Allows to move the inputted registry path between prefixes. Useful if you want to test the game in several prefixes without needing to rerun the installer for games that requiry registry entries to launch.

- Added an option to decide if you want the name sidebar to autocomplete with VNDB, SteamgridDB or none. Previously it was locked to VNDB. Defaults to VNDB still.
- Added an option in advanced settings to disable network access for the game, should always work with flatpak builds, for appimage you need firejail in your system for it to work.
- Added a new link to a third party modern version of Erogamescape: https://erogamescape.tailb5951c.ts.net/v2/ Unlike EGs this site also doesn't block foreign IPs so should be easier to use.
- Added the ability to run native linux games selecting prefix **Native**.
- Allow the ability to order labels by right clicking them.
- Fixed opening links directly from appimage not working.
- Fixed QT table colors outside of KDE environments.
- Fixed env vars checkboxes resetting when editing the game right after creating it.
- Improved launch times.


## [v0.5.4](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.5.4)

- Fix gamescope session timetracking (Bug from v0.5.3).
- Fix gamescope checkbox (Bug from v0.5.3).
- Improve Steam shortcut logic, hopefully it stops deleting other non steam games.

## [v0.5.3](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.5.3)

Adds emulation support:
 - In settings -> emulation -> Add the appimage or cli command for each emulator, it will create a fake prefix for the platform that you can select in the game sidebar.
 - in the game entry add the iso, rom, etc in the game path, and in prefix choose the platform of the emulator.
 - RPCS3 requires the eboot bin file, example: `/home/deck/games/BLJM61043/PS3_GAME/USRDIR/EBOOT.BIN` or game ID `%RPCS3_GAMEID%:BLJM61043` or directly `BLJM61043` should also work.
 - All other features should still work, for more info: https://github.com/uunniiblog/linux-vn-manager-lvnm/wiki/Emulation
 
The core GameRunner has been refactored into game launchers: launcher_base and sub launchers: wine launcher, emulation launcher, etc. This should make easier to implement new stuff or even port the launcher to other OS in the future.
Fix proton-ge 11.4+ new name runner downloads.
Fix linux-rt-upscale and scripts reap procceses

## [v0.5.2](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.5.2)

Added support for [linux-rt-upscaler](https://github.com/baronsmv/linux-rt-upscaler):
 - Main option is in settings tab. Requires it to be installed to be enabled.
 - Once enabled the option will appear in the sidebar to be enabled with custom parameters. For now I have put it inside the gamescope section.
 - The launcher will always add --target-title to the window title and --target-delay 1 parameters so it automatically upscales the game launched.
 - I recommend configuring profiles and passing --profile parameter to it so you don't end with million parameters options in the textbox. linux-rt-upscaler also supports auto profile detection so can also use that.

Improved/fixed proton runner detection so now it doesn't mistake them with certain proton forks.
Removed global environment variables from settings tab and moved it inside the env var dialog. Also improved the header styles/resizing of the table.
Added software version to some programs in debug prints/reports.

The goal forward is that new releases automatically read the description from this file's version

## [v0.5.1](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.5.1)

- Adds German support and the foundation for supporting more languages. #11 Thanks to Drackrath

## [v0.5.0](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.5.0)

- Savedata management: Can be enabled in Settings, Allows options like savedata detection, copying between prefixes, Gdrive sync, etc.
- Google Drive cloud Sync: Can seamlessly sync Savedata and playtime tracking files between devices using LVNM, setup: https://github.com/uunniiblog/linux-vn-manager-lvnm/wiki/Google-Drive-Cloud-Project-Setup
- Improve logging: Add extra options in Settings to log to file and optionally add wine logs from the game instead of always forcing it.
- UI fixes: Lots of UI fixes through the entire application.
- Destkop shortcut: ask where to save if Desktop folder can't be found. #10

## [v0.4.3](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.4.3)

- Fix AppImage x11 KDE errors in SteamOS. Bug report
- Fix opening external links in AppImage (vndb, egs, etc).
- Fix pre launch arguments splitting.

## [v0.4.2](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.4.2)

- Improved error handling across all the tabs to show error messages in the UI.
- Added a new cli option to launch the timetracker with games launched externally, useful in case you want to timetrack games launched through Steam easily. Check the readme for usage details.
- Show original Steam images when searching SteamgridDB images in game advanced settings.
- Added a button remove current images in game advanced settings.
- Fixed SteamgridDB images combo not getting preselected with vertical/horizontal when loading them after saving them previously.

## [v0.4.1](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.4.1)

- Fixes to import and export.
- Add list of json files to import for popular engines.

## [v0.4.0](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.4.0)

- Improved Wine process detection and added debug logging for process checks.
- Added SteamGridDB autocomplete support.
- Couple of minors fixes.

## [v0.3.7](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.7)

- Fixes for vndb image naming.
- Added a button to delete all current images in settings.
- Added update check to show latest version available at the bottom of settings if there is a new version in git.

## [v0.3.6](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.6)

- Added image handling in advanced settings. Now you can search for vndb releases and steamgriddb (https://www.steamgriddb.com/) pictures. Select one vertical cover that will be used in the application, and one horizontal layout that will be used when creating steam shortcuts.
- Added a field in settings for steamgriddb apikey.
- Remade a bunch of the logic to handle images, now the path to both images will be stored in the game json configuration data. It shouldn't break already existing covers, but if it does you may have to reselect the vndb id in the sidebar or in advanced settings.

## [v0.3.5](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.5)

- Added a vndb search autocomplete when writing the name of the game in the sidebar or import. Not the fastest since it needs to fetch pictures one by one but can be improved.
- Allow arguments in pre launch and post exit script: /path/to/script.sh argument1 argument2 etc. Useful in case the script needs a dynamic variable to avoid the need of making multiple scripts per each game.
- Added checkbox to wait for the game to be launched before executing the pre launch script. Useful in case your script needs the game to be running to do something with it. The logic uses DesktopUtils so only KDE properly supports native wayland games, as a fallback also added a logic in case the game is detected to be running native wayland in other desktops but it will not fully wait until the window has finished loading, only until is loaded in memory.

## [v0.3.4](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.4)

- Fix run in prefix not working after latest release.
- Trigger autosave in sidebar after saving in advanced settings to avoid having to double save.
- Refresh data automatically when opening statistics tab.

## [v0.3.3](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.3)

- Run post exit script in headless mode from steam/desktop shortcut.
- Disable font symlink checkbox if font folder is not configured.

## [v0.3.2](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.2)

Fixes:
 - Sidebar not reloading prefixes or hiding timetracking section when adding new game.
 - Fix Browse files not working in appimage.
 - Don't save invalid winetricks verbs into the prefix info.
 - Add winetricks and umu to path when opening bash terminal when using the appimage.
 - Use system file explorer instead of QT fallback in appimage.
 - Load global environment variables to utility options like regedit, bash terminal, etc.
 - Fixed some winetricks errors from appimage/steam deck environment.
 - Ui fixes.

New:
 - Now it is possible to change the configuration folders path to a new one, this includes prefixes, runners, covers and timetracking log folders. Can also move all the current files to the new directory (otherwise you won't be able to use them unless you go back). This should be useful in systems with low disk space in the main OS drive.
 - Ability to create 32 bit prefixes. Only available to wine amd64 (not wow64) runners.
 - Add winefile utility option.
 - Add the ability to open the Environment variable management dialog from the game sidebar directly, alongisde settings tab.
 - Add Advanced options dialog in game sidebar. Moved umu options there.
 - Added pre launch and post exit script attachment to advanced options.
 - Added arguments to advanced options.
 - Added pre launch command to advanced options.

## [v0.3.1](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.1)

- Added custom winetricks when creating or editing prefixes.
- Some fixes to exporting games config.
- Update timetracking in settings tab.

## [v0.3.0](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.3.0)

Changes:

- Allow user added environment variables in settings -> Manage Variables button.
- Add dialog window to track progress when downloading runners.
- Add Labels to categorize games in the game list. Right click a game -> Label -> Add new label. To delete a label right click the header in the game list. Sorting the game list will now be done within the label categories.
- Enable Wayland Driver checkbox at prefix level. Can be added or removed when creating or editing a prefix. Wine prefixes do not have the PROTON_ENABLE_WAYLAND variable so it is useful for those cases, but it does still work with both wine and proton prefixes. Do not recommended to enable it for playing VNs, but it may be useful for some installers to display correctly in Wayland Desktops.
- DPI scaling based on monitor resolution checkbox at prefix level. It automatically increases the DPI setting when primary monitor is bigger than 1080p. Useful for 1440 and 4k monitors where some installers or windows with fixed resolution are very small. Some old games also get scaled by this in window mode so be careful. DPI can also be manually set at winecfg.
- Export and import games. Exporting a game will create a json file with the game and prefix settings. Importing the json will download the runner, create the prefix and make an entry for the game with same settings. Note that only changes made through the launcher UI are saved, so changes made to prefixes manually can't be tracked and won't be exported.
- Create new class GameProcessManager to track running games and timetracking, instead of doing it in sidebar ui class.
- Some ui fixes

## [v0.2.3](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.2.3)

- Timetracker: Added X11 utils to use as a fallback in other desktops besides KDE. Should work in any x11 desktop or through xwayland.

## [v0.2.2](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.2.2)

Timetracking improvements:

- Add option to autostart timetracking at game start in settings
- New dialog to manually track window or stop tracking when game is running
- Show live tracking progress in sidebar
- Attach byte file size to log file name to avoid duplicates from same game engines like SiglusEngine. This will break current progress in any game you are playing right now since it will be created with a new file name from scratch. You can manually move your old data csv to the new one in ~/.local/share/lvnm/tracking/

## [v0.2.1](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.2.1)

Added texthooking options:
- Enable it in settings and link to the .exe of your texthooker of choice (make sure the architecture x86 or x64 coincides with the game's).
- Open a game, then right click it and select "Open texthooker" to open it.

Textractor should automatically hook into the game since it offers the -p game.exe argument.
Others texthooker should let you hook into the game through its interface options.

For Agent you can also select Frida server as a texthooker (https://github.com/frida/frida/releases/tag/16.2.5) and use the Linux version of Agent hooking it like this: 127.0.0.1|gamename.exe. Although using window's version directly is probably easier.

Note: As a workaround umu's vessel container restrictions I am running the texthooker without umu from Proton's bin directly, this could lead into issues and instability, although in my testing it seems fine with current version of textractor and agent.

Note2: If you are running the game with gamescope the texthooker will also open with gamescope, it is the only way to open two applications in the same prefix with gamescope. This is scuffed, not intended, and will spit a lot of errors through the terminal, but for now is the only way to make it work.

## [v0.2.0](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.2.0)

- Added playtime statistics, total playtime in the game list, and sorting options.
- Added initial timetracking support, including command-line tracking and Steam Deck testing.
- Improved logging, reduced memory use, and fixed assorted sidebar and application exit issues.

## [v0.1.0](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.1.0)

- Improved Proton runner discovery and codec setup.
- Began Steam artwork integration.

## [v0.0.3](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.0.3)

- Added global environment variables and tooltips in Settings.
- Improved the interface, sidebar resizing, game list refreshing, and Wine prefix browsing.
- Added a VNDB ID placeholder to game setup.

## [v0.0.2](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.0.2)

- Improved AppImage packaging, certificates, and compatibility with codec installation when no system Wine is present.
- Updated bundled AppImage dependencies and build workflows.

## [v0.0.1](https://github.com/uunniiblog/linux-vn-manager-lvnm/releases/tag/v0.0.1)

- Initial tagged release.
