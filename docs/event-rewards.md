# Timed attack rewards

The event overlay ("Pick a Reward!") at 33%, 66%, and 100% pauses battle input.
The bot releases any troop drag, waits 0.6–1.2 s for the cards to settle, then
clicks a random point inside the **right-hand card** (the bigger one, gold or
grey — its content does not matter). If the overlay is still open 2.5 s later it
clicks once more; after that it just waits for the event countdown to pick a
reward on its own. It verifies the overlay is gone (two clear frames) before
resuming. No OCR is needed. Stop interrupts the wait.

The overlay only exists during the timed event: when it never shows up nothing
changes in the attack.

The main strategy's End Battle and Surrender rules remain unchanged. The bot does
not wait for later milestones. Final damage can advance during exit confirmation.
Hero abilities retain their stored deployment slots; only a reward interruption
requires relocating the live hero portrait if the troop bar moves.

Validation: `python -m unittest discover -s tests -v`.
Live validation on Google Play Games at 1299×731 confirmed four hero ability clicks,
automatic reward selection after roughly 12 seconds, and battle exit after passing
50% (55% on the results screen). Later milestones are covered by repeat-overlay
tests; this live test did not prolong the attack to reach them.
