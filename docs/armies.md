# Deploy mechanics

What AresPilot actually does during a raid, for anyone tuning strategies or reading the code.

For the recommended army and the setup that makes it work, see
[Prepare your army](../README.md#3-prepare-your-army) in the README Quick start.

## Valkyries, Sneaky Goblins, Super Minions

These three share one routine. Per raid, in order:

1. **Select the troop** in the deploy bar. Abort if its icon isn't there.
2. **Drag-deploy around the perimeter.** One continuous press-and-drag from a randomly chosen
   corner, through four corner segments, then release — this empties the selected slot in a line
   along the base edges. Start corner and direction are randomized every raid (at 16:9 it starts
   left or right; at 16:10 it may also start from the top), and each segment's duration is
   jittered ±10%.
3. **Super Dragon**, if it's in the bar.
4. **Siege machine** — Log Launcher first, else Siege Barracks.
5. **Heroes**, in random order each raid: Queen, Warden, Royal Champion, King, Prince, Dragon
   Duke. Whichever are present get dropped, then clicked a second time to fire their abilities.
6. **Earthquake spells.**

Because step 2 is a drag rather than individual taps, exact troop count matters less than
filling the slot — the drag spreads whatever you're carrying along the edges.

## Earthquake placement

AresPilot clicks **11 earthquake points** per raid, in one of two patterns
(*Settings → Earthquake*):

- **Curve placement** (default) — samples an arc through the left/top/right anchor points with
  ±100px of jitter per point.
- **Random placement** — random points inside the region between that arc and a horizontal line
  40% up the frame. Falls back to curve placement if that region comes out degenerate.

It clicks all 11 points regardless of how many Earthquakes you're carrying; once you're out, the
remaining clicks land harmlessly.

## Edrags

A different routine: **12 Electro Dragons** placed individually around the diamond perimeter,
0.2s apart, rather than dragged. Heroes and spells follow as above.

## Builder Base

Baby Dragon is the only supported strategy (Night Witches is listed in the UI but still under
development). Per battle:

1. **Full zoom-out**, fast: the game shows the red "no deploy" border only for a few seconds.
2. **Read the border.** Red-dominant pixels → straight segments along the two isometric grid
   directions → convex hull. The Overall Damage panel is masked out (its stars are red too), and
   a hull smaller than a real border (fire, wooden walls) is rejected.
3. **One spot per dragon**, each a random **2–8 tiles** outside the border, spread evenly
   around the village from a random side. Only spots on the playable floor count (not on the
   HUD, the troop bar or the buttons): when a big village fills the floor on one side, the
   dragons are spread evenly over the open sides instead.
4. **Never stacked.** Every dragon lands at least **5 tiles** from the others. On a crowded
   floor that gap shrinks step by step; past that, each dragon takes the free spot farthest
   from the others, so two dragons never share a spot.
5. **Drop** each dragon on its spot, its card selected on the dragon's head — never on the
   troop-switch button — all within ~3 s. The Battle Machine / Flying Machine goes with one
   of the dragons.
6. **Retry missed drops.** A card that still shows its troop-switch button was not deployed:
   it is dropped again 2–3 tiles out, away from every spot already used, up to 5 rounds.
7. **Abilities**: every card clicked together after a random **10–20 s** (not in *Elixir*
   mode, which surrenders right away).

If no border shows, the bot falls back to the older diamond deploy.

**Trophy mode, second village.** After the first village reaches 100% (read twice from the
Overall Damage percent), the bot zooms out, selects a ready card and taps the village centre (on
the buildings) so the game shows the border, then repeats steps 2–6 with the surviving dragons
and the fresh cards only (grey cards are dead and skipped). With no border it uses a ring around
the village centre.
