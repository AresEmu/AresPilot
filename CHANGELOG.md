# Changelog

## Unreleased

### Fixed
- **Log file.** Every module had its own rotating handler on `arespilot.log`; at 5 MB the
  rotation failed on Windows (file in use) and from then on log lines were lost. All
  modules now share one handler.
- **Logs page.** Opening it again appended the whole file a second time and could freeze
  the window on a big log; it now loads only the end of the file, shows complete lines and
  follows the log after a rotation.
- **Builder Base without Baby Dragons.** A battle that opened with no dragon on the bar
  was left running, and the recovery looked for Surrender only (the button is End Battle
  before any troop is down): the bot waited minutes for the Battle button. The battle is
  now ended at once, and after 4 such battles in a row a timed run stops (run until maxed
  waits 5 minutes and tries again).
- **Deploy check.** The check after the last re-drop round ran before the game had time to
  take the dragons, so it could warn about dragons that were in fact placed.
- **Lost game window.** A window handle that died (game or Google Play Games restarted) is
  searched again instead of failing every capture; waits no longer spin when there is no
  capture.
- Closing the app during a run waits up to 3 s for the bot to stop, so the run summary is
  still written.

### Faster
- Screenshots: the capture is converted in one step (about 14 ms less per frame at
  2560×1440, same image).
- Builder Base troop-bar reads look at the card row only, not at the whole frame.

## 1.1.0 — AresPilot

First release under the **AresPilot** name (based on
[BasePilot](https://github.com/efebolukbasi/BasePilot) by Efe Bolukbasi, MIT).

### New
- **New name and logo.** The app, the exe (`AresPilot.exe`) and the data folder
  (`%LOCALAPPDATA%\AresPilot`) are renamed; settings from an older `BasePilot` install are
  copied over on the first start.
- **New interface.** Black, Apple-style design with a sidebar, header Start / Stop and
  iOS-style switches.
- **Builder Base Trophy mode.** Plays the first village to 100%, then attacks the second
  village with the surviving dragons and the fresh cards, and waits for the battle to end.
- **Baby Dragon edge deploy.** Reads the red border around the village and drops the dragons
  in six zones 2–8 tiles outside it, kept on the playable floor; machine with one dragon,
  abilities together after 10–25 s.
- **Missed-drop retries.** Dragons still on the bar after the deploy are dropped again, up to
  5 rounds.
- **Last run remembered.** The Run page restores village, army, Builder Base mode, duration
  and switches.

### Fixed
- Cards were tapped near the troop-switch button, which sometimes switched the troop
  instead of selecting it; the card select also needed more time to register.
- In the second village the Overall Damage stars were read as part of the red border,
  sending drops inside the village.
- Number fields in the interface were not centred.

### Changed
- The Players page shows "Work in progress" while the player list and multi-run are
  reworked.
- Clearer disclaimer: AresPilot is a personal educational project, not affiliated with
  Supercell, and the author does not condone cheating. The app shows it on the first start
  and runs only after it is accepted.
- The log no longer contains the account name from the game window title.
- README: removed the farming statistics section.

## 1.0.1 — BasePilot fork

October 2026 UI update of BasePilot: Home Village templates, Build panel auto upgrade, wall
upgrades, price/HUD reader and the other changes listed in the README.
