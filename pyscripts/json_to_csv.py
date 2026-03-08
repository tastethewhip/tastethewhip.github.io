import json
import csv
import sys

def flatten_quotes(quotes):
    if not quotes:
        return ""
    return "||".join([
        f"{q.get('date','')} | {q.get('horse','')} | {q.get('horse_id','')} | {q.get('race','')} | {q.get('race_id','')} | {q.get('course','')} | {q.get('course_id','')} | {q.get('distance_f','')} | {q.get('distance_y','')} | {q.get('quote','')}"
        for q in quotes
    ])

def flatten_stable_tour(stable_tour):
    if not stable_tour:
        return ""
    return "||".join([
        f"{t.get('horse','')} | {t.get('horse_id','')} | {t.get('quote','')}"
        for t in stable_tour
    ])

def flatten_prev_owners(prev_owners):
    if not prev_owners:
        return ""
    return "||".join([
        f"{o.get('owner','')} ({o.get('change_date','')})"
        for o in prev_owners
    ])

def flatten_stats(stats: dict, prefix: str):
    out = {}
    for key, value in stats.items():
        if isinstance(value, dict):
            for k2, v2 in value.items():
                out[f"{prefix}_{key}_{k2}"] = v2
        else:
            out[f"{prefix}_{key}"] = value
    return out

def flatten_runner(runner: dict):
    flat = {}
    for k, v in runner.items():
        if k == "quotes":
            flat["quotes"] = flatten_quotes(v)
        elif k == "stable_tour":
            flat["stable_tour"] = flatten_stable_tour(v)
        elif k == "prev_owners":
            flat["prev_owners"] = flatten_prev_owners(v)
        elif k == "stats":
            flat.update(flatten_stats(v, "stats"))
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                flat[f"{k}_{k2}"] = v2
        else:
            flat[k] = v
    return flat

def flatten_race(race: dict):
    # All keys except runners
    flat = {k: v for k, v in race.items() if k != "runners"}
    return flat

def find_races(data: dict):
    # Assumes structure is country > course > time > race
    for country in data.values():
        for course in country.values():
            for time, race in course.items():
                yield race

def main(json_file, csv_file):
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for race in find_races(data):
        race_flat = flatten_race(race)
        for runner in race.get('runners', []):
            row = {}
            row.update(race_flat)
            row.update(flatten_runner(runner))
            rows.append(row)

    # Collect all fieldnames
    fieldnames = set()
    for r in rows:
        fieldnames.update(r.keys())

    # --- Specify your preferred order here! Example below: ---
    exexample_order = [
        "course", "course_id", "race_id", "date", "off_time", "race_name", "distance_round", "distance", "distance_f", "region",
        "pattern", "race_class", "type", "age_band", "rating_band", "prize", "field_size", "going_detailed", "rail_movements",
        "stalls", "weather", "going", "surface", "number", "draw", "headgear", "headgear_first", "lbs", "ofr", "rpr", "ts",
        "jockey", "jockey_id", "last_run", "form", "trainer_rtf", "stats_course_runs", "stats_course_wins", "stats_distance_runs",
        "stats_distance_wins", "stats_going_runs", "stats_going_wins", "stats_jockey_last_14_runs", "stats_jockey_last_14_wins",
        "stats_jockey_last_14_wins_pct", "stats_jockey_last_14_profit", "stats_jockey_ovr_runs", "stats_jockey_ovr_wins",
        "stats_jockey_ovr_wins_pct", "stats_jockey_ovr_profit", "stats_trainer_last_14_runs", "stats_trainer_last_14_wins",
        "stats_trainer_last_14_wins_pct", "stats_trainer_last_14_profit", "stats_trainer_ovr_runs", "stats_trainer_ovr_wins",
        "stats_trainer_ovr_wins_pct", "stats_trainer_ovr_profit", "name", "horse_id", "age", "dob", "sex", "sex_code", "colour",
        "region", "breeder", "dam", "dam_region", "sire", "sire_region", "grandsire", "damsire", "damsire_region", "trainer",
        "trainer_id", "trainer_location", "trainer_14_days_runs", "trainer_14_days_wins", "trainer_14_days_percent", "owner",
        "prev_trainers", "prev_owners", "comment", "spotlight", "quotes", "stable_tour"
    ]
    example_order = [
        "course", "going_detailed", "off_time",  "race_name","pattern", "distance_round","race_class", "age_band", "rating_band", "prize", "field_size",
         "name","age", "sex","number", "draw",  "trainer","jockey","headgear", "headgear_first", "lbs", "ofr", "rpr", "ts",
         "last_run", "form", "comment", "spotlight", "quotes", "stable_tour","trainer_rtf", "stats_course_runs", "stats_course_wins", "stats_distance_runs", 
    ]    
    # Add missing fields from the data to the end
    ordered_fields = [f for f in example_order if f in fieldnames] + [f for f in fieldnames if f not in example_order]

    with open(csv_file, "w", encoding="utf-8", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=ordered_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python json_to_csv.py input.json output.csv")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
