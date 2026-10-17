# Equipment presets and substitution

`athlete/equipment.yml` is authoritative. At setup, start from a preset,
then edit it with the athlete ("anything missing? anything here you don't
have?").

## Presets

| Preset | Typical `available` |
|---|---|
| `commercial_gym` | barbells and racks, benches, dumbbells to ~40-50kg, cable stations, leg press, machines (chest/row/leg ext/curl), pull-up and dip stations, cardio machines |
| `home_gym` | rack or squat stands (ask about safety arms/spotter), barbell and plates (ask for the total), adjustable bench, often pull-up bar; ask about dumbbells, bands, rings |
| `minimal` | adjustable dumbbells or kettlebells, bands, pull-up bar or door anchor |
| `bodyweight_only` | floor, a sturdy table or rings, a bar/tree/playground |
| `mixed` | list per location, e.g. gym on weekdays and hotel bodyweight when travelling |

Always ask for the **safety setup** for heavy barbell work (safety arms/pins,
spotter availability). It decides whether max attempts are allowed.

Fill in `loads` so prescriptions round to buildable weights:
- barbell: bar weight and **total** plate counts
- dumbbells: the actual pairs (adjustable sets often go in 2-2.5kg steps)
- machine/cable stacks: min, max, step

## Substitution order

When the ideal exercise needs missing equipment, keep the **movement pattern
and loading profile**, in this order:

1. Same pattern, different implement (barbell row -> dumbbell row -> ring/inverted row)
2. Same pattern, unilateral or tempo to make up for lighter loads (goblet squat -> Bulgarian split squat with a 3s eccentric)
3. Same muscle, different pattern (cable fly -> deficit push-up -> ring fly)
4. Flag it: "this goal would benefit from X; options are ..." (for example, a
   bench goal with no safety setup means getting a spotter or safety arms
   before any max attempt)

Common swaps:

| Missing | Pattern | Substitute |
|---|---|---|
| cables | triceps pressdown | band pressdown, EZ/barbell skull crusher, close-grip push-up |
| cables | face pull / rear delt | band pull-apart, ring/inverted Y-raise, reverse fly with DBs |
| dumbbells | DB press | barbell variation, push-up variations (weighted vest/backpack) |
| leg machines | leg curl | Nordic curl (assisted), sliding leg curl, RDL |
| leg machines | leg extension | Spanish squat (band), sissy squat, heels-elevated goblet squat |
| rack | barbell squat | front-loaded goblet/DB squat, split squats, pistol progression |
| pull-up bar | vertical pull | band lat pulldown, ring/table inverted row (pull angle changes, so say so) |
| running surface | run intervals | bike/rower/elliptical intervals at equivalent HR |

Use `find_garmin_exercise` to get the Garmin category/key for the substitute
so it shows properly on the watch.
