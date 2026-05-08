import time
from datetime import datetime

import numpy as np
import pandas as pd


EXCEL_FILE_PATH = r"data\rua_fitness.xlsx"


def log_info(message):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[INFO] {message} at {now}")


def log_warn(message):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[WARN] {message} at {now}")


def normalize_columns(df):
    df.columns = [str(col).strip() for col in df.columns]
    return df


def read_sheet(file_path, sheet_name):
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    df = normalize_columns(df)
    return df


def safe_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def load_data(file_path):
    log_info("Loading Excel sheets")

    inbody = read_sheet(file_path, "INBODY_LOG")
    workout = read_sheet(file_path, "WORKOUT_LOG")
    exercise_master = read_sheet(file_path, "EXERCISE_MASTER")
    muscle_weight = read_sheet(file_path, "MUSCLE_WEIGHT")
    rpe_scale = read_sheet(file_path, "RPE_SCALE")

    return inbody, workout, exercise_master, muscle_weight, rpe_scale


def clean_inbody(inbody):
    log_info("Cleaning INBODY_LOG")

    required_cols = ["date", "weight_kg", "skeletal_muscle_kg", "body_fat_pct"]
    for col in required_cols:
        if col not in inbody.columns:
            raise ValueError(f"INBODY_LOG missing required column: {col}")

    inbody = inbody.copy()
    inbody["date"] = pd.to_datetime(inbody["date"], errors="coerce")
    inbody["weight_kg"] = safe_numeric(inbody["weight_kg"])
    inbody["skeletal_muscle_kg"] = safe_numeric(inbody["skeletal_muscle_kg"])
    inbody["body_fat_pct"] = safe_numeric(inbody["body_fat_pct"])

    inbody = inbody.dropna(subset=["date"])
    inbody = inbody.sort_values("date").reset_index(drop=True)

    inbody["weight_diff"] = inbody["weight_kg"].diff()
    inbody["skeletal_muscle_diff"] = inbody["skeletal_muscle_kg"].diff()
    inbody["body_fat_pct_diff"] = inbody["body_fat_pct"].diff()

    inbody["weight_change_text"] = inbody["weight_diff"].apply(
        lambda x: change_text(x, "체중", "kg")
    )
    inbody["muscle_change_text"] = inbody["skeletal_muscle_diff"].apply(
        lambda x: change_text(x, "골격근량", "kg")
    )
    inbody["fat_change_text"] = inbody["body_fat_pct_diff"].apply(
        lambda x: change_text(x, "체지방률", "%p")
    )

    inbody["body_composition_type"] = inbody.apply(classify_body_composition, axis=1)

    return inbody


def change_text(value, name, unit):
    if pd.isna(value):
        return "이전 측정값 없음"

    if value > 0:
        return f"{name}이 전보다 {value:.1f}{unit} 증가했어요"
    if value < 0:
        return f"{name}이 전보다 {abs(value):.1f}{unit} 감소했어요"

    return f"{name} 변화가 없어요"


def classify_body_composition(row):
    weight_th = 0.3
    muscle_th = 0.2
    fat_th = 0.5

    w = row.get("weight_diff", np.nan)
    m = row.get("skeletal_muscle_diff", np.nan)
    f = row.get("body_fat_pct_diff", np.nan)

    if pd.isna(w) or pd.isna(m) or pd.isna(f):
        return "Baseline"

    w_state = "same" if abs(w) < weight_th else ("up" if w > 0 else "down")
    m_state = "same" if abs(m) < muscle_th else ("up" if m > 0 else "down")
    f_state = "same" if abs(f) < fat_th else ("up" if f > 0 else "down")

    if f_state == "down" and m_state in ["same", "up"] and w_state in ["down", "same"]:
        return "Recomposition"

    if w_state == "down" and f_state == "down" and m_state == "down":
        return "Weight loss with muscle loss"

    if w_state in ["same", "up"] and m_state == "up" and f_state in ["same", "down"]:
        return "Lean mass up"

    if w_state == "down" and f_state == "down":
        return "Weight loss"

    if f_state == "up" and w_state in ["same", "up"]:
        return "Fat gain"

    if m_state == "down" and f_state in ["same", "up"]:
        return "Poor change"

    return "Maintenance"


def clean_workout(workout):
    log_info("Cleaning WORKOUT_LOG")

    required_cols = ["date", "session", "exercise", "sets", "reps", "weight_kg", "rpe"]
    for col in required_cols:
        if col not in workout.columns:
            raise ValueError(f"WORKOUT_LOG missing required column: {col}")

    workout = workout.copy()
    workout["date"] = pd.to_datetime(workout["date"], errors="coerce")
    workout["exercise"] = workout["exercise"].astype(str).str.strip()
    workout["session"] = workout["session"].astype(str).str.strip()
    workout["sets"] = safe_numeric(workout["sets"])
    workout["reps"] = safe_numeric(workout["reps"])
    workout["weight_kg"] = safe_numeric(workout["weight_kg"])
    workout["rpe"] = safe_numeric(workout["rpe"])

    workout = workout.dropna(subset=["date", "exercise", "sets", "reps", "weight_kg"])
    workout = workout[workout["exercise"] != ""].copy()

    workout["raw_volume"] = workout["sets"] * workout["reps"] * workout["weight_kg"]
    workout["rpe_available"] = np.where(workout["rpe"].notna(), "Y", "N")

    return workout


def clean_master(exercise_master, muscle_weight, rpe_scale):
    log_info("Cleaning master sheets")

    exercise_master = exercise_master.copy()
    muscle_weight = muscle_weight.copy()
    rpe_scale = rpe_scale.copy()

    exercise_master["exercise"] = exercise_master["exercise"].astype(str).str.strip()
    exercise_master["session"] = exercise_master["session"].astype(str).str.strip()
    exercise_master["exercise_fatigue_factor"] = safe_numeric(
        exercise_master["exercise_fatigue_factor"]
    )

    muscle_weight["exercise"] = muscle_weight["exercise"].astype(str).str.strip()
    muscle_weight["muscle_group"] = muscle_weight["muscle_group"].astype(str).str.strip()
    muscle_weight["ratio"] = safe_numeric(muscle_weight["ratio"])

    rpe_scale["rpe"] = safe_numeric(rpe_scale["rpe"])
    rpe_scale["stimulus_factor"] = safe_numeric(rpe_scale["stimulus_factor"])
    rpe_scale["fatigue_factor"] = safe_numeric(rpe_scale["fatigue_factor"])

    return exercise_master, muscle_weight, rpe_scale


def validate_data(workout, exercise_master, muscle_weight):
    log_info("Validating exercise names and muscle ratios")

    workout_exercises = set(workout["exercise"].dropna().unique())
    master_exercises = set(exercise_master["exercise"].dropna().unique())
    muscle_weight_exercises = set(muscle_weight["exercise"].dropna().unique())

    missing_in_master = sorted(workout_exercises - master_exercises)
    missing_in_muscle_weight = sorted(master_exercises - muscle_weight_exercises)

    ratio_check = (
        muscle_weight.groupby("exercise", as_index=False)["ratio"]
        .sum()
        .rename(columns={"ratio": "ratio_sum"})
    )
    ratio_check["ratio_status"] = np.where(
        np.isclose(ratio_check["ratio_sum"], 1.0, atol=0.001), "OK", "CHECK"
    )

    validation_rows = []

    for exercise in missing_in_master:
        validation_rows.append(
            {
                "check_type": "WORKOUT_LOG exercise not in EXERCISE_MASTER",
                "exercise": exercise,
                "status": "CHECK",
            }
        )

    for exercise in missing_in_muscle_weight:
        validation_rows.append(
            {
                "check_type": "EXERCISE_MASTER exercise not in MUSCLE_WEIGHT",
                "exercise": exercise,
                "status": "CHECK",
            }
        )

    for _, row in ratio_check.iterrows():
        if row["ratio_status"] != "OK":
            validation_rows.append(
                {
                    "check_type": "MUSCLE_WEIGHT ratio sum not 1.00",
                    "exercise": row["exercise"],
                    "status": f"CHECK: {row['ratio_sum']:.3f}",
                }
            )

    validation = pd.DataFrame(validation_rows)

    if validation.empty:
        validation = pd.DataFrame(
            [{"check_type": "All validation checks", "exercise": "-", "status": "OK"}]
        )
        log_info("Validation completed without critical issues")
    else:
        log_warn("Validation found issues. Check VALIDATION sheet")

    return validation


def build_calc_workout(workout, exercise_master, muscle_weight, rpe_scale):
    log_info("Building CALC_WORKOUT")

    master_cols = [
        "exercise",
        "equipment_type",
        "movement_pattern",
        "fatigue_type",
        "exercise_fatigue_factor",
    ]

    workout_master = workout.merge(
        exercise_master[master_cols],
        on="exercise",
        how="left",
    )

    calc = workout_master.merge(
        muscle_weight[["exercise", "muscle_group", "ratio"]],
        on="exercise",
        how="left",
    )

    calc = calc.merge(
        rpe_scale[["rpe", "stimulus_factor", "fatigue_factor"]],
        on="rpe",
        how="left",
    )

    calc["muscle_volume"] = calc["raw_volume"] * calc["ratio"]

    calc["stimulus_score"] = np.where(
        calc["rpe"].notna(),
        calc["muscle_volume"] * calc["stimulus_factor"],
        np.nan,
    )

    calc["fatigue_load"] = np.where(
        calc["rpe"].notna(),
        calc["raw_volume"]
        * calc["fatigue_factor"]
        * calc["exercise_fatigue_factor"],
        np.nan,
    )

    calc["week_start"] = calc["date"] - pd.to_timedelta(calc["date"].dt.weekday, unit="D")

    cols = [
        "date",
        "week_start",
        "session",
        "exercise",
        "equipment_type",
        "movement_pattern",
        "fatigue_type",
        "sets",
        "reps",
        "weight_kg",
        "rpe",
        "rpe_available",
        "raw_volume",
        "muscle_group",
        "ratio",
        "muscle_volume",
        "stimulus_factor",
        "stimulus_score",
        "fatigue_factor",
        "exercise_fatigue_factor",
        "fatigue_load",
    ]

    available_cols = [col for col in cols if col in calc.columns]
    calc = calc[available_cols].sort_values(["date", "session", "exercise", "muscle_group"])

    return calc


def build_workout_summaries(calc):
    log_info("Building workout summary sheets")

    daily = (
        calc.groupby(["date", "session"], as_index=False)
        .agg(
            total_raw_volume=("raw_volume", "sum"),
            total_muscle_volume=("muscle_volume", "sum"),
            total_stimulus_score=("stimulus_score", "sum"),
            total_fatigue_load=("fatigue_load", "sum"),
        )
        .sort_values(["date", "session"])
    )

    weekly = (
        calc.groupby(["week_start", "session"], as_index=False)
        .agg(
            total_raw_volume=("raw_volume", "sum"),
            total_muscle_volume=("muscle_volume", "sum"),
            total_stimulus_score=("stimulus_score", "sum"),
            total_fatigue_load=("fatigue_load", "sum"),
        )
        .sort_values(["week_start", "session"])
    )

    muscle_weekly = (
        calc.groupby(["week_start", "muscle_group"], as_index=False)
        .agg(
            muscle_volume=("muscle_volume", "sum"),
            stimulus_score=("stimulus_score", "sum"),
        )
        .sort_values(["week_start", "muscle_group"])
    )

    return daily, weekly, muscle_weekly


def write_output(file_path, sheets):
    log_info("Writing calculated sheets to Excel")

    with pd.ExcelWriter(
        file_path,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace",
    ) as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def main():
    start_time = time.time()

    try:
        inbody, workout, exercise_master, muscle_weight, rpe_scale = load_data(EXCEL_FILE_PATH)

        inbody = clean_inbody(inbody)
        workout = clean_workout(workout)
        exercise_master, muscle_weight, rpe_scale = clean_master(
            exercise_master, muscle_weight, rpe_scale
        )

        validation = validate_data(workout, exercise_master, muscle_weight)
        calc = build_calc_workout(workout, exercise_master, muscle_weight, rpe_scale)
        daily, weekly, muscle_weekly = build_workout_summaries(calc)

        output_sheets = {
            "SUMMARY_INBODY": inbody,
            "CALC_WORKOUT": calc,
            "SUMMARY_WORKOUT_DAILY": daily,
            "SUMMARY_WORKOUT_WEEKLY": weekly,
            "SUMMARY_MUSCLE_WEEKLY": muscle_weekly,
            "VALIDATION": validation,
        }

        write_output(EXCEL_FILE_PATH, output_sheets)

        elapsed = time.time() - start_time
        elapsed_text = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        print(f"[Done] exited with code=0 in {elapsed_text}")

    except Exception as error:
        elapsed = time.time() - start_time
        elapsed_text = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        print(f"[ERROR] {error}")
        print(f"[Done] exited with code=1 in {elapsed_text}")


if __name__ == "__main__":
    main()