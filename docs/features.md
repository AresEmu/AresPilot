# AresPilot features

Everything AresPilot does, and how far each part is. The short version is in the
[README](../README.md#features); what changed in each version is in the
[CHANGELOG](../CHANGELOG.md).

## Status legend

| Status | Meaning |
|---|---|
| ✅ Working | Implemented and verified against the new UI |
| 🧪 Not fully tested | Implemented, but only briefly or not yet tested live |
| 🚧 Work in progress | Being rewritten for the new UI, not usable yet |
| 📋 Planned | Not started yet, to be released |

### ✅ Working (new UI, 16:9)

- **New UI support (16:9 profile).** All Home Village templates re-cropped at 2560×1440
  for the October 2026 UI.
- **New interface.** Black, Apple-style desktop app: sidebar with icons, Start / Stop in
  the page header, iOS-style switches, centred number fields.
- **Builder Base on the new UI.** Village detection, boat, Find Now, attack, battle end,
  Return Home and the Star Bonus popup use templates re-cropped for the
  new UI. Baby Dragon army with the Battle Machine / Flying Machine.
- **Builder Base wall upgrades.** Same flow as the Home Village (Build panel + Upgrade
  More), with its own threshold in millions (one decimal, e.g. 1.3M). The first look reads
  the wall prices; if it cannot finish (panel not opened, list not read to the end) it is
  tried again at the next checks, up to 3 times.
- **Builder Base loot modes.** *Gold* (end the battle at 2 stars), *Both* (at 1 star),
  *Elixir* (surrender right after deploying).
- **Auto upgrade via the new Build panel ("Buildings & Heroes").** Opens the panel with
  the Build button, scans the whole list, reads names and costs, and confirms upgrades.
  Modes: **Maxer**, **Rusher**, **Dry run** (logs only, clicks nothing).
- **Wall upgrades via the Build panel.** Triggered by the full-storage icon. Finds the
  Wall row (scrolling down to the end of the list if needed: the game re-sorts the list
  by what the loot can pay, so the row moves), picks a payable wall level (see Settings →
  Upgrade order), uses **Upgrade More** to batch walls
  in the multi-select bar, pays with gold or elixir and confirms the "Upgrade Walls"
  popup. Up to two rounds per check; the second round only runs if a wall level is still
  payable after re-reading the HUD. Wall prices are re-read every time (never cached to
  disk). The number of walls recorded is taken from the actual HUD drop (cost ÷ price per
  wall), so the summary stays correct even if the batch counter is off.
- **New price and HUD reader.** Prices and gold/elixir/dark elixir amounts are read with a
  dedicated digit-glyph matcher instead of Tesseract, with thousands-grouping checks and
  red-text detection (unaffordable prices).
- **Both confirm dialog layouts.** Works with and without the Gold Pass (discounted price
  layout vs yellow banner layout).
- **Safe popup handling.** Gem-spend dialogs, panels and unknown popups are closed via their
  X / Cancel buttons — never a blind Okay/Confirm.
- **End-of-run summary.** When a run ends, a summary window and log entry show run time,
  number of attacks, farmed gold/elixir/dark elixir, and walls upgraded grouped by level
  with their cost.
- **Robust loot tracker.** HUD amounts are only accepted when two frames agree. A sudden
  "collapse" (e.g. 9,000,000 read as 6) triggers a re-read, and if it persists the previous
  value is held for one cycle instead of counting a fake loss or a fake gain. Real spends
  (walls, upgrades) are not counted as farmed loot.
- **Varied attack patterns.** Heroes are dropped at random points of the perimeter and
  hero abilities fire 0–10 s after each hero is deployed. Troop placement
  (Valkyrie, Super Minion, Sneaky Goblin) was reworked:
  - troops follow random waypoints inside a **3.5-tile band** along each side, joined by a
    half-smoothed curve (a gentle, irregular wave rather than a perfect spline);
  - drops land **between tiles** too, not only on tile centres (irregular spacing of
    0.2–0.45 tiles);
  - drag speed changes **±30% per hop**, and each side takes ±10% of its share of time;
  - **corners are crossed faster** (≈1.4× with its own ±30% variation each time) to avoid
    big troop clumps where two sides meet;
  - **Valkyrie** deploy lasts **7 s**; **Super Minion** deploy lasts a new random
    **2.8–4.2 s** every attack.
- **Full zoom-out before attacking**, so the first attack after the menus is not zoomed in.
- **Faster template matching.** Coarse-to-fine matching with a template cache
  (~4× faster per call).
- **Reliable list scrolling.** The Build panel list is checked to have actually moved and
  stopped before it is read.
- **Settings auto-save** on every change; Duration field fixed.
- **AresPilot data folder.** Settings, logs and debug frames live in
  `%LOCALAPPDATA%\AresPilot`; on the first start, settings from an older `BasePilot`
  install are copied over automatically (the old folder is left untouched).
- **Separate test logs.** Unit tests write to `%LOCALAPPDATA%\AresPilot\test_logs`
  (see `ARESPILOT_LOG_DIR`) so they never pollute the real run log.

### 🧪 Implemented but not fully tested

- **Reward chests (November 2026 update).** The end-of-battle chest (Claim Reward) and the
  Star Bonus chests (after 2 stars, and the 5-star "Star Bonus Received!" Claim) are
  claimed, tapped open and continued, whatever the chest or the reward is.
- **Builder Base Trophy mode.** Never ends the battle early: plays the first village to
  100%, then attacks the second village with the surviving dragons and the fresh cards,
  and waits for the battle to finish before Return Home.
- **Baby Dragon edge deploy (Builder Base, both stages).** Full zoom-out, then the bot reads
  the red "no deploy" border around the village and drops each dragon on its own spot, a
  random **2–8 tiles** outside the border, spread evenly around the village and at least
  **5 tiles** from the others (never two on the same spot), all within ~3 s. Spots never
  land off the playable floor, on the HUD, on the troop bar or on the buttons: when a big
  village fills one side, the dragons share the open sides. The machine is dropped with one
  of the dragons; all abilities fire together after a random 10–20 s. In the second village the
  bot first taps a building with a dragon selected to make the game show the border.
- **Missed-drop retries.** Dragons the game did not take (their card still shows the troop
  switch button) are dropped again closer to the border, up to 5 rounds.
- **Last run remembered.** Village, army, Builder Base mode, duration and all switches of
  the Run page come back as they were at the last Start.
- **Rusher mode** on the new Build panel.
- **Timed event "Pick a Reward!" overlay** (33/66/100% damage): the bot now clicks the
  right-hand card (gold or grey, whatever it contains) instead of waiting ~12 s for the
  countdown. When the event is over and the overlay never shows up, attacks run as before.
  See [docs/event-rewards.md](event-rewards.md).
- **Sneaky Goblin** with the new troop placement (shares the Valkyrie/Super Minion code,
  not run live yet).
- **Earthquake "Random Placement"** after the fix.
- **Gem dialog recovery** in rare cases (seen once during a large elixir batch, cause not
  confirmed).
- **Run until maxed / idling** logic with the new panel (inherited from upstream, not
  re-verified over long sessions).

### 🚧 Work in progress

- **Faster wall rounds.** Remember where the Wall row is during a run (not on disk) and
  start the scan from there, cutting most of the list scrolling (~+10% attacks/h
  expected with walls on).
- **Faster Stop.** Pressing Stop can take 6–9 s to take effect mid-attack (spell and hero
  deploy, OCR passes are not interruptible yet). Goal: ~1–1.5 s.
- **Wall batch counter.** The fallback wall count is one short per batch (the first
  selected wall isn't counted). Harmless today because the HUD-drop count is used, but it
  will be corrected as a safety net.
- **Stuck-screen timeout loop.** A known case where the bot can keep retrying the same
  recovery step after a timeout.
- **Player list / multi-run.** The Players page shows "Work in progress" while the
  player list and multi-run are reworked.
- **Night Witches** (Builder Base): listed in the UI, not implemented yet.

### 📋 Planned / to be released

- **Laboratory chip on the new UI** (lab status in Live status, max 2 labs).
- **Multi-account** support.
- **Timer** function.
- **Skipping low-loot bases.**
- **16:10 profile** update for the new UI (only the 16:9 profile is updated for now).

Not automated (as upstream): starting laboratory research and Pet House upgrades.

## Safety rails

Automation that spends resources has to be careful, so AresPilot:

- Never confirms a purchase whose price shows red (unaffordable → gem-spend risk).
- Checks that the confirm dialog matches the picked row (name, price and resource) before
  clicking Confirm.
- Verifies every upgrade actually started by checking the builder counter afterwards.
- Closes unknown dialogs via their close button or empty ground — never a blind "Okay".
- Keeps a gold buffer so matchmaking entry fees are never spent on walls.
- Saves screenshots of anything it couldn't verify to `%LOCALAPPDATA%\AresPilot\debug\`
  instead of retrying blindly.
