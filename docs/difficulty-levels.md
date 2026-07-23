# Difficulty levels

DTXScribe auto-rates every chart on a 0.00 to 9.99 scale, the same scale DTXMania
stores and shows. This page is the reference the leveling system targets. For each
level it lists the average note density, the busiest 2-second burst, and the playing
skills a chart at that level should contain. Use it to sanity-check an auto-rated
score, or to decide a level by hand.

## Scale and tiers

The score runs from 0.00 to 9.99. The four DTXMania tiers group the levels:

| Tier | Score range | File |
|------|-------------|------|
| Basic | 0.00 to 3.00 | bsc.dtx |
| Advanced | 3.00 to 6.00 | adv.dtx |
| Extreme | 6.00 to 8.50 | ext.dtx |
| Master | 8.50 and up | mstr.dtx |

## Reading the table

- Avg density: notes per second across the whole chart.
- 2-sec peak: notes per second in the busiest 2-second window (fills and bursts).
- `@NNN` means the pattern happens at NNN BPM, so "16ths @120" is sixteenth notes at 120 BPM.
- `/s` is notes per second, the wavy dash is roughly, and the double wavy sign is about.

## Level reference

| Lv | Avg density | 2-sec peak | What the player is expected to handle |
|----|-------------|-----------|----------------------------------------|
| 1.0 | 1.7/s | 3/s | Quarter-note hi-hat only. Kicks land on bar starts only, never consecutive. |
| 1.5 | 1.9/s | 3.5/s | Steady quarter notes plus backbeat. Kicks on beats 1 and 3. |
| 2.0 | 2.2/s | 4/s | Sustained quarter notes, occasional 8th-note pickups (short phrases about 8ths @100). |
| 2.5 | 2.5/s | 4.5/s | Mostly quarters plus 8th-note fills. Syncopated kicks start appearing (about 1 hit/sec). |
| 3.0 | 2.8/s | 5/s | Partial 8th-note riding sections, 8th-note fills @140. Consecutive kicks still slow. |
| 3.5 | 3.5/s | 6/s | Mid-tempo 8th riding lasting several bars. Short 16th fills @85. |
| 4.0 | 4.2/s | 7/s | Full 8-beat (8th hi-hat plus backbeat) held for a whole song at 120 to 150 BPM. 16th snare fills @105 only in short bursts. Double kicks limited to 8ths at about 80. |
| 4.5 | 4.9/s | 8/s | Stable 8-beat @135. Single-pad rolls at 16ths @68. First 16th-spaced kick pairs (about 8ths @90). |
| 5.0 | 5.6/s | 8.5/s | 8-beat @150. Short 16th fills @130, rolls at 16ths @83. Kick syncopation density about 2.6/s. |
| 5.5 | 6.1/s | 10/s | 16th-note riding around @100 appears in slower songs. Left pedal in 15% of charts. 16th kick pairs @55. |
| 6.0 | 6.8/s | 10.5/s | 8-beat @180 in fast songs, 16th fills @111. Twin pedal debuts (10% of charts). Foot bursts about 4 hits/s. |
| 6.5 | 7.5/s | 12/s | 16th streams @120 for several beats, rolls at 16ths @131. Slow double bass begins: 4-note bursts about 16ths @75, 8-note runs @62. |
| 7.0 | 8.4/s | 13.5/s | Double bass becomes a standard skill (left pedal 50%, twin bass 34% of charts). 4-note kick bursts at 16ths @105, sustained 8-note runs at 16ths @80. Hands: 16th rolls @143. |
| 7.5 | 9.1/s | 14.5/s | Sustained double bass at 16ths @97, bursts @130. 16th hand streams @142. Twin pedal 55%. |
| 8.0 | 9.6/s | 16/s | Double bass 16ths @120 sustained for 8 or more notes, 16-note runs @100. Hands: 16ths @150, rolls @165. 3-note chords are routine. |
| 8.5 | 10.4/s | 17.5/s | Sustained double bass at 16ths @138, long runs @120. Hand 16ths @158. |
| 9.0 | 11.3/s | 19/s | Double bass 16ths @168, 16-note runs @146. Hand 16ths @170, rolls @182. Constant combined hand and foot patterns. |
| 9.5 | 12.8/s | 22.5/s or more | Double bass 16ths @186 (long runs @169), hand 16ths @192 or more, rolls @198. Burst sections hitting about 25 notes/sec. Nearly every chart uses twin pedal. |

## How the rater uses this

The auto-rater in `dtxscribe/difficulty.py` measures two things off a chart: its average
note density and its busiest 2-second window. It maps each one back onto the columns
above (both rise with level, so each is an invertible lookup), gets a level from density
and a level from the 2-sec peak, then averages the two for the final 0.00 to 9.99 score.
So the score a chart gets is the level whose sustained load and burst load it actually
matches. For example, a chart that holds about 8 notes/sec with 13 to 14 in its busiest
bursts sits around Level 7, where double bass has become a standard skill.

The skill descriptions in the table (double bass, rolls, 16th streams) are the context
behind those two rate columns. The rates already climb as those skills appear, so the
rater does not need to detect each skill separately.
