# Changelog

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
