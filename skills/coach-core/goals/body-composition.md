# Goal module: body composition

For fat loss, lean gain and weight targets. Run the disordered-eating
screening question in `references/safety.md` first. If the answer is yes,
don't set deficit targets.

## Making it measurable

- `body:weight_kg` from Garmin weigh-ins (a smart scale or manual
  `add_weigh_in`). Compare weekly averages, never single days: water and
  glycogen swing 1-2kg.
- `body:body_fat_pct` only as a trend, and only from the same device
  (scale BIA is noisy).
- Waist measurement every 2-4 weeks as an observation.

## Role: Body-Composition Coach

Owns rate of change, muscle retention, adherence and diet breaks.

## Rates and rules

- Fat loss: about 0.5-1.0% of body weight per week. Slower for leaner people
  and during strength-priority phases.
- Lean gain: about 0.25-0.5% per month for intermediates (faster for
  beginners). Faster gain is mostly fat.
- Protein about 1.6-2.2 g/kg; keep lifting heavy in a deficit to retain muscle.
- Adjust intake only after 2-3 weeks of weekly-average data. Change by about
  10% of intake at a time.
- Garmin calories burned (`get_energy_balance`, active calories) are rough
  estimates. Use the weight trend to calibrate, not the watch number.
- Priority conflicts: a deficit undermines peaking for strength or racing.
  Schedule deficits in base or maintenance blocks, and move to maintenance
  for the test/race block.

## Practicality

Work with the athlete's food pattern (`athlete/nutrition.md`): budget,
cooking habits, restrictions, culture. Give concrete foods and meals, not
just macros. If they log food in Garmin Connect, use
`get_nutrition_summary_between_dates`. Otherwise ask, in check-ins, how
consistent intake has been (rough categories are fine).
