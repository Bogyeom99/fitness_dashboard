from datetime import datetime

import altair as alt
import gspread
import numpy as np
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials


ACSM_WEEKLY_SET_TARGET = 10

PRIMARY_PURPLE = "#A78BFA"
SESSION_PUSH = "#A78BFA"
SESSION_PULL = "#2DD4BF"
SESSION_LEGS = "#F59E0B"


st.set_page_config(
    page_title="RUA Fitness Dashboard",
    page_icon="📊",
    layout="wide",
)


st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #0F141B;
        color: #E5E7EB;
    }

    [data-testid="stHeader"] {
        background: rgba(15, 20, 27, 0.92);
    }

    [data-testid="stSidebar"] {
        background-color: #111821;
        border-right: 1px solid #2B3545;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1450px;
    }

    h1, h2, h3 {
        color: #E5E7EB !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }

    p, div, span, label {
        color: #CBD5E1;
    }

    .section-card {
        background: linear-gradient(135deg, #171D26 0%, #1E2633 100%);
        padding: 1.4rem 1.6rem;
        border-radius: 20px;
        border: 1px solid #2B3545;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28);
        margin-bottom: 1rem;
    }

    .small-note {
        color: #A7B0C0;
        font-size: 0.95rem;
        line-height: 1.6;
        margin-top: 0.35rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #2B3545;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #171D26;
        color: #A7B0C0;
        border-radius: 12px 12px 0 0;
        padding: 10px 18px;
        border: 1px solid #2B3545;
        border-bottom: none;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        background-color: #241B36;
        color: #EDE9FE;
        border-color: #A78BFA;
        font-weight: 700;
    }

    [data-testid="stMetric"] {
        background-color: #171D26;
        border: 1px solid #2B3545;
        padding: 18px;
        border-radius: 18px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.24);
    }

    [data-testid="stMetricLabel"] {
        color: #A7B0C0;
        font-size: 0.92rem;
        font-weight: 600;
    }

    [data-testid="stMetricValue"] {
        color: #E5E7EB;
        font-size: 1.7rem;
        font-weight: 800;
    }

    div[data-testid="stExpander"] {
        background-color: #171D26;
        border-radius: 16px;
        border: 1px solid #2B3545;
    }

    [data-testid="stDataFrame"] {
        background-color: #171D26;
        border-radius: 14px;
        border: 1px solid #2B3545;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# Google Sheets connection
# =========================================================

REQUIRED_INPUT_SHEETS = [
    "INBODY_LOG",
    "WORKOUT_LOG",
    "EXERCISE_MASTER",
    "MUSCLE_WEIGHT",
    "RPE_SCALE",
]


def get_service_account_info():
    if "gcp_service_account" not in st.secrets:
        st.error("Streamlit Secrets에 [gcp_service_account]가 없습니다.")
        st.stop()

    info = dict(st.secrets["gcp_service_account"])

    private_key = info.get("private_key", "")
    if "\\n" in private_key:
        info["private_key"] = private_key.replace("\\n", "\n")

    return info


def get_spreadsheet_url():
    if "spreadsheet_url" not in st.secrets:
        st.error("Streamlit Secrets에 spreadsheet_url이 없습니다.")
        st.stop()

    return str(st.secrets["spreadsheet_url"]).strip()


def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    credentials = Credentials.from_service_account_info(
        get_service_account_info(),
        scopes=scopes,
    )

    return gspread.authorize(credentials)


def worksheet_to_dataframe(worksheet):
    values = worksheet.get_all_values()

    if not values:
        return pd.DataFrame()

    header = [str(col).strip() for col in values[0]]

    rows = []
    for row in values[1:]:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[: len(header)]

        rows.append(row)

    df = pd.DataFrame(rows, columns=header)

    empty_header_cols = [col for col in df.columns if col == ""]
    if empty_header_cols:
        df = df.drop(columns=empty_header_cols)

    df = df.replace(r"^\s*$", np.nan, regex=True)

    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_google_sheet_data(spreadsheet_url):
    client = get_gspread_client()

    try:
        spreadsheet = client.open_by_url(spreadsheet_url)
    except Exception as error:
        st.error(f"Google Sheets를 여는 중 오류가 발생했습니다: {error}")
        st.stop()

    worksheets = spreadsheet.worksheets()
    sheet_names = [worksheet.title for worksheet in worksheets]
    sheet_map = {str(name).strip(): name for name in sheet_names}

    missing_sheets = [sheet for sheet in REQUIRED_INPUT_SHEETS if sheet not in sheet_map]

    if missing_sheets:
        st.error(
            "필수 입력 시트를 찾을 수 없습니다. "
            f"누락 시트: {missing_sheets}. "
            f"현재 시트 목록: {list(sheet_map.keys())}"
        )
        st.stop()

    data = {}

    for required_sheet in REQUIRED_INPUT_SHEETS:
        real_sheet_name = sheet_map[required_sheet]
        worksheet = spreadsheet.worksheet(real_sheet_name)
        data[required_sheet] = worksheet_to_dataframe(worksheet)

    return data, sheet_names


# =========================================================
# Basic utilities
# =========================================================

def normalize_columns(df):
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df


def safe_numeric(series):
    clean_series = series.astype(str).str.replace(",", "", regex=False)
    return pd.to_numeric(clean_series, errors="coerce")


def format_number(value, digits=1):
    if pd.isna(value):
        return "-"
    return f"{value:.{digits}f}"


def get_latest_text(df, col):
    if col not in df.columns or df.empty:
        return "정보 없음"

    value = df.iloc[-1][col]

    if pd.isna(value):
        return "정보 없음"

    return str(value)


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


# =========================================================
# Data cleaning and calculation
# =========================================================

def clean_inbody(inbody):
    inbody = normalize_columns(inbody)

    required_cols = ["date", "weight_kg", "skeletal_muscle_kg", "body_fat_pct"]

    for col in required_cols:
        if col not in inbody.columns:
            st.error(f"INBODY_LOG에 '{col}' 컬럼이 없습니다.")
            st.stop()

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


def clean_muscle_weight(muscle_weight):
    muscle_weight = normalize_columns(muscle_weight)

    required_cols = ["exercise", "muscle_group", "ratio"]

    for col in required_cols:
        if col not in muscle_weight.columns:
            st.error(f"MUSCLE_WEIGHT에 '{col}' 컬럼이 없습니다.")
            st.stop()

    muscle_weight["exercise"] = muscle_weight["exercise"].astype(str).str.strip()
    muscle_weight["muscle_group"] = muscle_weight["muscle_group"].astype(str).str.strip()
    muscle_weight["ratio"] = safe_numeric(muscle_weight["ratio"])

    return muscle_weight


def clean_workout(workout, exercise_master, rpe_scale):
    workout = normalize_columns(workout)
    exercise_master = normalize_columns(exercise_master)
    rpe_scale = normalize_columns(rpe_scale)

    required_workout_cols = [
        "date",
        "session",
        "exercise",
        "sets",
        "reps",
        "weight_kg",
        "rpe",
    ]

    for col in required_workout_cols:
        if col not in workout.columns:
            st.error(f"WORKOUT_LOG에 '{col}' 컬럼이 없습니다.")
            st.stop()

    required_master_cols = ["exercise", "session", "exercise_fatigue_factor"]

    for col in required_master_cols:
        if col not in exercise_master.columns:
            st.error(f"EXERCISE_MASTER에 '{col}' 컬럼이 없습니다.")
            st.stop()

    required_rpe_cols = ["rpe", "stimulus_factor", "fatigue_factor"]

    for col in required_rpe_cols:
        if col not in rpe_scale.columns:
            st.error(f"RPE_SCALE에 '{col}' 컬럼이 없습니다.")
            st.stop()

    workout["date"] = pd.to_datetime(workout["date"], errors="coerce")
    workout["exercise"] = workout["exercise"].astype(str).str.strip()

    workout["session"] = workout["session"].astype("string").str.strip()
    workout["session"] = workout["session"].replace(
        ["", "nan", "NaN", "None", "#N/A", "미등록"],
        pd.NA,
    )

    workout["sets"] = safe_numeric(workout["sets"])
    workout["reps"] = safe_numeric(workout["reps"])
    workout["weight_kg"] = safe_numeric(workout["weight_kg"])
    workout["rpe"] = safe_numeric(workout["rpe"])

    workout = workout.dropna(subset=["date", "exercise", "sets", "reps", "weight_kg"])
    workout = workout[workout["exercise"] != ""].copy()
    workout["raw_volume"] = workout["sets"] * workout["reps"] * workout["weight_kg"]

    exercise_master["exercise"] = exercise_master["exercise"].astype(str).str.strip()
    exercise_master["session"] = exercise_master["session"].astype(str).str.strip()
    exercise_master["exercise_fatigue_factor"] = safe_numeric(
        exercise_master["exercise_fatigue_factor"]
    )

    master_lookup = exercise_master[
        ["exercise", "session", "exercise_fatigue_factor"]
    ].rename(columns={"session": "session_master"})

    workout = workout.merge(master_lookup, on="exercise", how="left")
    workout["session"] = workout["session"].fillna(workout["session_master"])
    workout["session"] = workout["session"].fillna("미등록")
    workout = workout.drop(columns=["session_master"])

    rpe_scale["rpe"] = safe_numeric(rpe_scale["rpe"])
    rpe_scale["stimulus_factor"] = safe_numeric(rpe_scale["stimulus_factor"])
    rpe_scale["fatigue_factor"] = safe_numeric(rpe_scale["fatigue_factor"])

    workout = workout.merge(
        rpe_scale[["rpe", "stimulus_factor", "fatigue_factor"]],
        on="rpe",
        how="left",
    )

    workout["fatigue_load"] = np.where(
        workout["rpe"].notna(),
        workout["raw_volume"]
        * workout["fatigue_factor"]
        * workout["exercise_fatigue_factor"],
        np.nan,
    )

    workout["rpe_status"] = np.where(workout["rpe"].notna(), "RPE 있음", "RPE 없음")
    workout["week_start"] = workout["date"] - pd.to_timedelta(
        workout["date"].dt.weekday,
        unit="D",
    )

    return workout, exercise_master, rpe_scale


def validate_data(workout, exercise_master, muscle_weight):
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
        np.isclose(ratio_check["ratio_sum"], 1.0, atol=0.001),
        "OK",
        "CHECK",
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

    return validation


def build_calc_workout(workout, muscle_weight):
    calc = workout.merge(
        muscle_weight[["exercise", "muscle_group", "ratio"]],
        on="exercise",
        how="left",
    )

    calc["muscle_volume"] = calc["raw_volume"] * calc["ratio"]
    calc["weighted_sets"] = calc["sets"] * calc["ratio"]

    calc["stimulus_score"] = np.where(
        calc["rpe"].notna(),
        calc["muscle_volume"] * calc["stimulus_factor"],
        np.nan,
    )

    return calc


def build_muscle_weekly(calc):
    muscle_weekly = (
        calc.groupby(["week_start", "muscle_group"], as_index=False)
        .agg(
            muscle_volume=("muscle_volume", "sum"),
            stimulus_score=("stimulus_score", "sum"),
            weighted_sets=("weighted_sets", "sum"),
        )
        .sort_values(["week_start", "muscle_group"])
    )

    return muscle_weekly


@st.cache_data(ttl=300, show_spinner=False)
def prepare_dashboard_data(spreadsheet_url):
    raw_data, sheet_names = load_google_sheet_data(spreadsheet_url)

    inbody = raw_data["INBODY_LOG"]
    workout = raw_data["WORKOUT_LOG"]
    exercise_master = raw_data["EXERCISE_MASTER"]
    muscle_weight = raw_data["MUSCLE_WEIGHT"]
    rpe_scale = raw_data["RPE_SCALE"]

    inbody = clean_inbody(inbody)
    muscle_weight = clean_muscle_weight(muscle_weight)
    workout, exercise_master, rpe_scale = clean_workout(workout, exercise_master, rpe_scale)

    validation = validate_data(workout, exercise_master, muscle_weight)
    calc = build_calc_workout(workout, muscle_weight)
    muscle_weekly = build_muscle_weekly(calc)

    return (
        inbody,
        workout,
        exercise_master,
        muscle_weight,
        rpe_scale,
        validation,
        calc,
        muscle_weekly,
        sheet_names,
    )


# =========================================================
# Chart settings
# =========================================================

def session_color_scale():
    return alt.Scale(
        domain=["밀기", "당기기", "하체"],
        range=[SESSION_PUSH, SESSION_PULL, SESSION_LEGS],
    )


def muscle_color_scale():
    return alt.Scale(
        domain=[
            "Chest",
            "Upper Back",
            "Lower Back",
            "Shoulders",
            "Quadriceps",
            "Hamstrings",
            "Hips",
            "Biceps",
            "Triceps",
        ],
        range=[
            "#F87171",
            "#60A5FA",
            "#94A3B8",
            "#FBBF24",
            "#34D399",
            "#A3E635",
            "#C084FC",
            "#2DD4BF",
            "#F472B6",
        ],
    )


def make_inbody_line_chart(inbody_filtered):
    chart_df = inbody_filtered[
        ["date", "weight_kg", "skeletal_muscle_kg", "body_fat_pct"]
    ].copy()

    chart_df = chart_df.rename(
        columns={
            "weight_kg": "체중",
            "skeletal_muscle_kg": "골격근량",
            "body_fat_pct": "체지방률",
        }
    )

    long_df = chart_df.melt(id_vars="date", var_name="항목", value_name="값")

    return (
        alt.Chart(long_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="날짜", axis=alt.Axis(format="%Y-%m-%d")),
            y=alt.Y("값:Q", title="값", scale=alt.Scale(domain=[10, 55])),
            color=alt.Color(
                "항목:N",
                title="항목",
                scale=alt.Scale(
                    domain=["체중", "골격근량", "체지방률"],
                    range=["#60A5FA", "#34D399", "#FBBF24"],
                ),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                alt.Tooltip("항목:N", title="항목"),
                alt.Tooltip("값:Q", title="값", format=".1f"),
            ],
        )
        .properties(height=430)
    )


def make_inbody_change_chart(inbody_filtered):
    required_cols = ["date", "weight_diff", "skeletal_muscle_diff", "body_fat_pct_diff"]

    for col in required_cols:
        if col not in inbody_filtered.columns:
            return None

    change_chart = inbody_filtered[required_cols].copy()

    change_chart = change_chart.rename(
        columns={
            "weight_diff": "체중 변화",
            "skeletal_muscle_diff": "골격근량 변화",
            "body_fat_pct_diff": "체지방률 변화",
        }
    )

    change_long = change_chart.melt(id_vars="date", var_name="항목", value_name="변화량")
    change_long = change_long.dropna(subset=["변화량"])

    if change_long.empty:
        return None

    return (
        alt.Chart(change_long)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="날짜", axis=alt.Axis(format="%Y-%m-%d")),
            y=alt.Y("변화량:Q", title="이전 측정 대비 변화량"),
            color=alt.Color(
                "항목:N",
                title="항목",
                scale=alt.Scale(
                    domain=["체중 변화", "골격근량 변화", "체지방률 변화"],
                    range=["#60A5FA", "#34D399", "#FBBF24"],
                ),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                alt.Tooltip("항목:N", title="항목"),
                alt.Tooltip("변화량:Q", title="변화량", format=".1f"),
            ],
        )
        .properties(height=360)
    )


def make_fatigue_chart(workout_filtered):
    fatigue_daily = workout_filtered.dropna(subset=["fatigue_load"]).copy()

    if fatigue_daily.empty:
        return None

    fatigue_daily["date_only"] = fatigue_daily["date"].dt.date

    fatigue_daily = (
        fatigue_daily.groupby("date_only", as_index=False)["fatigue_load"]
        .sum()
        .sort_values("date_only")
    )

    return (
        alt.Chart(fatigue_daily)
        .mark_line(point=True, color=PRIMARY_PURPLE)
        .encode(
            x=alt.X("date_only:T", title="날짜", axis=alt.Axis(format="%Y-%m-%d")),
            y=alt.Y("fatigue_load:Q", title="RPE 기반 피로도"),
            tooltip=[
                alt.Tooltip("date_only:T", title="날짜", format="%Y-%m-%d"),
                alt.Tooltip("fatigue_load:Q", title="피로도", format=",.0f"),
            ],
        )
        .properties(height=350)
    )


def make_muscle_volume_line_chart(muscle_weekly_filtered):
    return (
        alt.Chart(muscle_weekly_filtered.copy())
        .mark_line(point=True)
        .encode(
            x=alt.X("week_start:T", title="주 시작일", axis=alt.Axis(format="%Y-%m-%d")),
            y=alt.Y("muscle_volume:Q", title="근육군 볼륨"),
            color=alt.Color("muscle_group:N", title="근육군", scale=muscle_color_scale()),
            tooltip=[
                alt.Tooltip("week_start:T", title="주 시작일", format="%Y-%m-%d"),
                alt.Tooltip("muscle_group:N", title="근육군"),
                alt.Tooltip("muscle_volume:Q", title="볼륨", format=",.0f"),
            ],
        )
        .properties(height=440)
    )


def make_muscle_stimulus_line_chart(muscle_weekly_filtered):
    chart_df = muscle_weekly_filtered.dropna(subset=["stimulus_score"]).copy()

    if chart_df.empty or chart_df["stimulus_score"].sum() == 0:
        return None

    return (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("week_start:T", title="주 시작일", axis=alt.Axis(format="%Y-%m-%d")),
            y=alt.Y("stimulus_score:Q", title="RPE 기반 자극도"),
            color=alt.Color("muscle_group:N", title="근육군", scale=muscle_color_scale()),
            tooltip=[
                alt.Tooltip("week_start:T", title="주 시작일", format="%Y-%m-%d"),
                alt.Tooltip("muscle_group:N", title="근육군"),
                alt.Tooltip("stimulus_score:Q", title="자극도", format=",.0f"),
            ],
        )
        .properties(height=440)
    )


def build_frequent_exercise_summary(workout_filtered):
    return (
        workout_filtered.groupby(["session", "exercise"], as_index=False)
        .agg(
            training_days=("date", lambda x: x.dt.date.nunique()),
            entries=("exercise", "count"),
            total_sets=("sets", "sum"),
            total_reps=("reps", "sum"),
            max_weight=("weight_kg", "max"),
            avg_weight=("weight_kg", "mean"),
            total_volume=("raw_volume", "sum"),
        )
        .sort_values(
            ["session", "training_days", "total_volume"],
            ascending=[True, False, False],
        )
    )


def build_progression_recommendations(workout_filtered, recent_n=3):
    daily_exercise = workout_filtered.copy()
    daily_exercise["date_only"] = daily_exercise["date"].dt.normalize()

    daily_exercise = (
        daily_exercise.groupby(["date_only", "session", "exercise"], as_index=False)
        .agg(
            total_sets=("sets", "sum"),
            total_reps=("reps", "sum"),
            max_weight=("weight_kg", "max"),
            avg_rpe=("rpe", "mean"),
            total_volume=("raw_volume", "sum"),
        )
        .rename(columns={"date_only": "date"})
        .sort_values(["exercise", "date"])
    )

    recommendations = []

    for exercise, group in daily_exercise.groupby("exercise"):
        group = group.sort_values("date").tail(recent_n)

        if len(group) < recent_n:
            continue

        session = group["session"].iloc[-1]
        weight_range = group["max_weight"].max() - group["max_weight"].min()
        reps_range = group["total_reps"].max() - group["total_reps"].min()
        latest_weight = group["max_weight"].iloc[-1]
        latest_reps = group["total_reps"].iloc[-1]
        latest_rpe = group["avg_rpe"].iloc[-1]
        first_date = group["date"].min()
        last_date = group["date"].max()

        weight_static = weight_range == 0
        reps_static = reps_range == 0

        if not weight_static:
            status = "중량 변화 있음"
            recommendation = "현재 진행 중"
        elif weight_static and not reps_static:
            status = "중량 고정, 반복수 변화 있음"
            recommendation = "반복수 증가가 멈추면 증량 검토"
        else:
            status = "중량과 반복수 정체"

            if pd.isna(latest_rpe):
                recommendation = "RPE 없음: 다음 운동에서 체감강도 확인 후 증량 검토"
            elif latest_rpe <= 8:
                recommendation = "증량 권장: 다음 수행 시 2.5에서 5% 또는 최소 단위 증량"
            elif latest_rpe <= 9:
                recommendation = "소폭 증량 검토: 자세 유지 가능하면 최소 단위 증량"
            else:
                recommendation = "유지 권장: 현재 강도가 높아 반복수 안정화 우선"

        recommendations.append(
            {
                "session": session,
                "exercise": exercise,
                "recent_sessions": len(group),
                "period": f"{first_date.strftime('%Y-%m-%d')} ~ {last_date.strftime('%Y-%m-%d')}",
                "latest_weight": latest_weight,
                "latest_total_reps": latest_reps,
                "latest_rpe": latest_rpe,
                "status": status,
                "recommendation": recommendation,
            }
        )

    result = pd.DataFrame(recommendations)

    if result.empty:
        return result

    priority_order = {
        "증량 권장": 1,
        "소폭 증량 검토": 2,
        "RPE 없음": 3,
        "반복수 증가": 4,
        "현재 진행 중": 5,
        "유지 권장": 6,
    }

    def get_priority(text):
        for key, value in priority_order.items():
            if key in text:
                return value
        return 99

    result["priority"] = result["recommendation"].apply(get_priority)
    return result.sort_values(["priority", "session", "exercise"])


def build_acsm_hypertrophy_check(calc_workout, weekly_set_target=10):
    if calc_workout.empty:
        return pd.DataFrame()

    weekly_sets = (
        calc_workout.groupby(["week_start", "muscle_group"], as_index=False)
        .agg(
            weighted_sets=("weighted_sets", "sum"),
            exercise_count=("exercise", "nunique"),
        )
        .sort_values(["week_start", "muscle_group"])
    )

    weekly_sets["target_sets"] = weekly_set_target
    weekly_sets["set_gap"] = weekly_sets["weighted_sets"] - weekly_sets["target_sets"]
    weekly_sets["status"] = np.where(
        weekly_sets["weighted_sets"] >= weekly_set_target,
        "충분",
        "부족",
    )
    weekly_sets["recommendation"] = np.where(
        weekly_sets["weighted_sets"] >= weekly_set_target,
        "근비대 목적 주간 세트 기준 충족",
        "해당 근육군의 주간 세트 추가 필요",
    )

    return weekly_sets

DEFAULT_MUSCLE_GROUPS = [
    "Chest",
    "Upper Back",
    "Lower Back",
    "Shoulders",
    "Quadriceps",
    "Hamstrings",
    "Hips",
    "Biceps",
    "Triceps",
]


def build_this_week_summary(workout, calc_workout, weekly_set_target=10):
    if workout.empty:
        return {"has_data": False}

    latest_date = pd.to_datetime(workout["date"].max())
    week_start = latest_date - pd.to_timedelta(latest_date.weekday(), unit="D")
    week_end_exclusive = week_start + pd.Timedelta(days=7)

    week_workout = workout[
        (workout["date"] >= week_start)
        & (workout["date"] < week_end_exclusive)
    ].copy()

    if week_workout.empty:
        return {"has_data": False}

    total_volume = week_workout["raw_volume"].sum()
    training_days = week_workout["date"].dt.date.nunique()
    fatigue_sum = week_workout["fatigue_load"].sum(skipna=True)

    session_volume = (
        week_workout.groupby("session", as_index=False)["raw_volume"]
        .sum()
        .sort_values("raw_volume", ascending=False)
    )

    if session_volume.empty:
        top_session = "-"
        top_session_volume = 0
    else:
        top_session = session_volume.iloc[0]["session"]
        top_session_volume = session_volume.iloc[0]["raw_volume"]

    exercise_summary = (
        week_workout.groupby("exercise", as_index=False)
        .agg(
            training_days=("date", lambda x: x.dt.date.nunique()),
            total_sets=("sets", "sum"),
            total_volume=("raw_volume", "sum"),
        )
        .sort_values(["training_days", "total_volume"], ascending=[False, False])
    )

    if exercise_summary.empty:
        top_exercise = "-"
    else:
        top_exercise = exercise_summary.iloc[0]["exercise"]

    if calc_workout.empty:
        insufficient_muscles = []
        acsm_week = pd.DataFrame()
    else:
        calc = calc_workout.copy()
        calc["week_start"] = pd.to_datetime(calc["week_start"], errors="coerce")

        calc_week = calc[
            calc["week_start"] == week_start
        ].copy()

        acsm_week = (
            calc_week.groupby("muscle_group", as_index=False)["weighted_sets"]
            .sum()
            if not calc_week.empty
            else pd.DataFrame(columns=["muscle_group", "weighted_sets"])
        )

        acsm_week = pd.DataFrame({"muscle_group": DEFAULT_MUSCLE_GROUPS}).merge(
            acsm_week,
            on="muscle_group",
            how="left",
        )

        acsm_week["weighted_sets"] = acsm_week["weighted_sets"].fillna(0)
        acsm_week["target_sets"] = weekly_set_target
        acsm_week["set_gap"] = acsm_week["weighted_sets"] - acsm_week["target_sets"]
        acsm_week["status"] = np.where(
            acsm_week["weighted_sets"] >= weekly_set_target,
            "충분",
            "부족",
        )

        insufficient_muscles = acsm_week[
            acsm_week["status"] == "부족"
        ]["muscle_group"].tolist()

    progression_df = build_progression_recommendations(workout, recent_n=3)

    if progression_df.empty:
        progression_candidates = pd.DataFrame()
    else:
        progression_candidates = progression_df[
            progression_df["recommendation"].str.contains(
                "증량 권장|소폭 증량 검토",
                na=False,
            )
        ].copy()

    return {
        "has_data": True,
        "week_start": week_start,
        "week_end": week_end_exclusive - pd.Timedelta(days=1),
        "week_label": f"{week_start.strftime('%Y-%m-%d')} ~ {(week_end_exclusive - pd.Timedelta(days=1)).strftime('%Y-%m-%d')}",
        "total_volume": total_volume,
        "training_days": training_days,
        "fatigue_sum": fatigue_sum,
        "top_session": top_session,
        "top_session_volume": top_session_volume,
        "top_exercise": top_exercise,
        "insufficient_muscles": insufficient_muscles,
        "insufficient_count": len(insufficient_muscles),
        "progression_candidates": progression_candidates,
        "progression_count": len(progression_candidates),
        "acsm_week": acsm_week,
    }


def render_this_week_summary(summary):
    st.markdown("### 이번 주 요약")

    if not summary.get("has_data", False):
        st.info("이번 주 요약을 표시할 운동 데이터가 없습니다.")
        return

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("기준 주차", summary["week_label"])

    with col2:
        st.metric("총 훈련 볼륨", f"{summary['total_volume']:,.0f} kg")

    with col3:
        st.metric("운동 수행일", f"{summary['training_days']} 일")

    with col4:
        st.metric("주요 세션", str(summary["top_session"]))

    with col5:
        st.metric("누적 피로도", f"{summary['fatigue_sum']:,.0f}")

    col6, col7 = st.columns(2)

    with col6:
        st.markdown("#### 근비대 기준 부족 부위")

        if summary["insufficient_count"] == 0:
            st.success("이번 주는 모든 근육군이 기준 세트를 충족했습니다.")
        else:
            insufficient_text = ", ".join(summary["insufficient_muscles"])
            st.warning(
                f"{summary['insufficient_count']}개 근육군 부족: {insufficient_text}"
            )

    with col7:
        st.markdown("#### 증량 검토 운동")

        if summary["progression_count"] == 0:
            st.info("현재 기준으로 뚜렷한 증량 후보 운동이 없습니다.")
        else:
            st.warning(
                f"{summary['progression_count']}개 운동에서 증량 검토 가능"
            )

            st.dataframe(
                summary["progression_candidates"][
                    [
                        "session",
                        "exercise",
                        "latest_weight",
                        "latest_total_reps",
                        "latest_rpe",
                        "recommendation",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

# =========================================================
# Prepare data
# =========================================================

SPREADSHEET_URL = get_spreadsheet_url()

try:
    (
        inbody,
        workout,
        exercise_master,
        muscle_weight,
        rpe_scale,
        validation,
        calc_workout,
        muscle_weekly,
        sheet_names,
    ) = prepare_dashboard_data(SPREADSHEET_URL)
except Exception as error:
    st.error(f"Google Sheets 데이터 처리 중 오류가 발생했습니다: {error}")
    st.stop()


if st.sidebar.button("데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()


# =========================================================
# Filters
# =========================================================

st.sidebar.title("필터")
st.sidebar.caption("데이터 소스: Google Sheets")

min_date = min(
    inbody["date"].min() if not inbody.empty else pd.Timestamp.today(),
    workout["date"].min() if not workout.empty else pd.Timestamp.today(),
)

max_date = max(
    inbody["date"].max() if not inbody.empty else pd.Timestamp.today(),
    workout["date"].max() if not workout.empty else pd.Timestamp.today(),
)

date_range = st.sidebar.date_input(
    "조회 기간",
    value=(min_date.date(), max_date.date()),
    min_value=min_date.date(),
    max_value=max_date.date(),
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date = pd.to_datetime(date_range[0])
    end_date = pd.to_datetime(date_range[1])
else:
    start_date = min_date
    end_date = max_date

session_options = sorted(workout["session"].dropna().unique())

selected_sessions = st.sidebar.multiselect(
    "세션",
    options=session_options,
    default=session_options,
)

muscle_options = sorted(muscle_weekly["muscle_group"].dropna().unique())

selected_muscles = st.sidebar.multiselect(
    "근육군",
    options=muscle_options,
    default=muscle_options,
)

inbody_filtered = inbody[
    (inbody["date"] >= start_date)
    & (inbody["date"] <= end_date)
].copy()

workout_filtered = workout[
    (workout["date"] >= start_date)
    & (workout["date"] <= end_date)
    & (workout["session"].isin(selected_sessions))
].copy()

muscle_weekly_filtered = muscle_weekly[
    (muscle_weekly["week_start"] >= start_date)
    & (muscle_weekly["week_start"] <= end_date)
    & (muscle_weekly["muscle_group"].isin(selected_muscles))
].copy()

if not calc_workout.empty:
    calc_workout_filtered = calc_workout[
        (calc_workout["date"] >= start_date)
        & (calc_workout["date"] <= end_date)
        & (calc_workout["muscle_group"].isin(selected_muscles))
    ].copy()
else:
    calc_workout_filtered = pd.DataFrame()


# =========================================================
# Layout
# =========================================================

st.markdown(
    """
    <div class="section-card">
        <h1>RUA Fitness Dashboard</h1>
        <p class="small-note">
        인바디 체성분 변화, 운동 볼륨, 근육군별 자극 분포, RPE 기반 피로도, 증량 후보를 한 화면에서 확인합니다.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


with st.expander("데이터 검증 결과 보기"):
    st.write("Google Sheets 시트 목록:", sheet_names)
    st.dataframe(validation, width="stretch")

this_week_summary = build_this_week_summary(
    workout=workout,
    calc_workout=calc_workout,
    weekly_set_target=ACSM_WEEKLY_SET_TARGET,
)

render_this_week_summary(this_week_summary)

tab_inbody, tab_workout, tab_muscle, tab_raw = st.tabs(
    ["인바디 변화", "운동 변화", "근육군 분석", "원자료 확인"]
)


with tab_inbody:
    st.subheader("인바디 체성분 변화")

    if inbody_filtered.empty:
        st.warning("선택한 기간에 인바디 데이터가 없습니다.")
    else:
        latest = inbody_filtered.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "현재 체중",
                f"{format_number(latest.get('weight_kg'))} kg",
                f"{format_number(latest.get('weight_diff'))} kg",
            )

        with col2:
            st.metric(
                "현재 골격근량",
                f"{format_number(latest.get('skeletal_muscle_kg'))} kg",
                f"{format_number(latest.get('skeletal_muscle_diff'))} kg",
            )

        with col3:
            st.metric(
                "현재 체지방률",
                f"{format_number(latest.get('body_fat_pct'))} %",
                f"{format_number(latest.get('body_fat_pct_diff'))} %p",
            )

        with col4:
            st.metric(
                "체성분 변화 유형",
                str(latest.get("body_composition_type", "정보 없음")),
            )

        st.markdown("### 이전 측정 대비 변화")
        st.write(get_latest_text(inbody_filtered, "weight_change_text"))
        st.write(get_latest_text(inbody_filtered, "muscle_change_text"))
        st.write(get_latest_text(inbody_filtered, "fat_change_text"))

        st.markdown("### 날짜별 체성분 변화")
        st.altair_chart(make_inbody_line_chart(inbody_filtered), width="stretch")

        st.markdown("### 이전 측정 대비 변화량")
        change_chart = make_inbody_change_chart(inbody_filtered)

        if change_chart is None:
            st.info("변화량 그래프를 표시할 데이터가 없습니다.")
        else:
            st.altair_chart(change_chart, width="stretch")

        st.markdown("### 인바디 기록")
        st.dataframe(inbody_filtered, width="stretch")


with tab_workout:
    st.subheader("운동 변화")

    if workout_filtered.empty:
        st.warning("선택한 기간에 운동 데이터가 없습니다.")
    else:
        total_volume = workout_filtered["raw_volume"].sum()
        total_sessions = workout_filtered["date"].dt.date.nunique()
        total_rows = len(workout_filtered)
        rpe_available_count = workout_filtered["rpe"].notna().sum()
        rpe_coverage = rpe_available_count / total_rows * 100 if total_rows > 0 else 0
        fatigue_sum = workout_filtered["fatigue_load"].sum(skipna=True)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("총 훈련 볼륨", f"{total_volume:,.0f} kg")

        with col2:
            st.metric("운동 수행일", f"{total_sessions} 일")

        with col3:
            st.metric("RPE 기록률", f"{rpe_coverage:.1f}%")

        with col4:
            st.metric("누적 피로도", f"{fatigue_sum:,.0f}")

        st.markdown("### 일별 운동 볼륨")

        daily_volume = workout_filtered.copy()
        daily_volume["date_only"] = daily_volume["date"].dt.date

        daily_volume = (
            daily_volume.groupby("date_only", as_index=False)["raw_volume"]
            .sum()
            .sort_values("date_only")
        )

        daily_volume_chart = (
            alt.Chart(daily_volume)
            .mark_line(point=True, color=PRIMARY_PURPLE)
            .encode(
                x=alt.X("date_only:T", title="날짜", axis=alt.Axis(format="%Y-%m-%d")),
                y=alt.Y("raw_volume:Q", title="운동 볼륨"),
                tooltip=[
                    alt.Tooltip("date_only:T", title="날짜", format="%Y-%m-%d"),
                    alt.Tooltip("raw_volume:Q", title="운동 볼륨", format=",.0f"),
                ],
            )
            .properties(height=350)
        )

        st.altair_chart(daily_volume_chart, width="stretch")

        st.markdown("### 세션별 운동 볼륨")

        session_volume = (
            workout_filtered.groupby("session", as_index=False)["raw_volume"]
            .sum()
            .sort_values("raw_volume", ascending=False)
        )

        session_chart = (
            alt.Chart(session_volume)
            .mark_bar(color=PRIMARY_PURPLE)
            .encode(
                x=alt.X("session:N", title="세션", sort="-y"),
                y=alt.Y("raw_volume:Q", title="운동 볼륨"),
                tooltip=[
                    alt.Tooltip("session:N", title="세션"),
                    alt.Tooltip("raw_volume:Q", title="운동 볼륨", format=",.0f"),
                ],
            )
            .properties(height=350)
        )

        st.altair_chart(session_chart, width="stretch")

        st.markdown("### 세션별 자주 하는 운동")

        frequent_summary = build_frequent_exercise_summary(workout_filtered)

        if frequent_summary.empty:
            st.info("자주 하는 운동을 계산할 데이터가 없습니다.")
        else:
            selected_session_for_exercise = st.selectbox(
                "세션 선택",
                options=sorted(frequent_summary["session"].dropna().unique()),
                key="frequent_exercise_session",
            )

            frequent_filtered = frequent_summary[
                frequent_summary["session"] == selected_session_for_exercise
            ].copy()

            top_exercise_chart = (
                alt.Chart(frequent_filtered.head(10))
                .mark_bar(color=PRIMARY_PURPLE)
                .encode(
                    x=alt.X("training_days:Q", title="수행일 수"),
                    y=alt.Y("exercise:N", title="운동명", sort="-x"),
                    tooltip=[
                        alt.Tooltip("exercise:N", title="운동명"),
                        alt.Tooltip("training_days:Q", title="수행일 수"),
                        alt.Tooltip("total_sets:Q", title="총 세트"),
                        alt.Tooltip("total_reps:Q", title="총 반복"),
                        alt.Tooltip("max_weight:Q", title="최대 중량", format=".1f"),
                        alt.Tooltip("total_volume:Q", title="총 볼륨", format=",.0f"),
                    ],
                )
                .properties(height=420)
            )

            st.altair_chart(top_exercise_chart, width="stretch")

            st.dataframe(
                frequent_filtered[
                    [
                        "session",
                        "exercise",
                        "training_days",
                        "total_sets",
                        "total_reps",
                        "max_weight",
                        "avg_weight",
                        "total_volume",
                    ]
                ],
                width="stretch",
            )

        st.markdown("### 주차별 세션 운동 볼륨")

        weekly_volume = workout_filtered.copy()
        weekly_volume["week_start"] = pd.to_datetime(weekly_volume["week_start"], errors="coerce")

        weekly_volume = (
            weekly_volume.groupby(["week_start", "session"], as_index=False)["raw_volume"]
            .sum()
            .sort_values(["week_start", "session"])
        )

        weekly_chart = (
            alt.Chart(weekly_volume)
            .mark_bar()
            .encode(
                x=alt.X("week_start:T", title="주 시작일", axis=alt.Axis(format="%Y-%m-%d")),
                y=alt.Y("raw_volume:Q", title="운동 볼륨"),
                color=alt.Color("session:N", title="세션", scale=session_color_scale()),
                tooltip=[
                    alt.Tooltip("week_start:T", title="주 시작일", format="%Y-%m-%d"),
                    alt.Tooltip("session:N", title="세션"),
                    alt.Tooltip("raw_volume:Q", title="운동 볼륨", format=",.0f"),
                ],
            )
            .properties(height=380)
        )

        st.altair_chart(weekly_chart, width="stretch")

        st.markdown("### RPE 기반 피로도")

        fatigue_chart = make_fatigue_chart(workout_filtered)

        if fatigue_chart is None:
            st.info("선택한 기간에 RPE가 있는 운동 기록이 없어 피로도 그래프를 표시할 수 없습니다.")
        else:
            st.altair_chart(fatigue_chart, width="stretch")

        st.markdown("### 정체 운동 및 증량 권장")

        progression_df = build_progression_recommendations(workout_filtered, recent_n=3)

        if progression_df.empty:
            st.info("최근 3회 이상 반복 수행된 운동이 부족해서 증량 권장 판단을 할 수 없습니다.")
        else:
            recommendation_filter = st.multiselect(
                "권장 상태 필터",
                options=sorted(progression_df["recommendation"].dropna().unique()),
                default=sorted(progression_df["recommendation"].dropna().unique()),
                key="progression_filter",
            )

            progression_view = progression_df[
                progression_df["recommendation"].isin(recommendation_filter)
            ].copy()

            st.dataframe(
                progression_view[
                    [
                        "session",
                        "exercise",
                        "period",
                        "latest_weight",
                        "latest_total_reps",
                        "latest_rpe",
                        "status",
                        "recommendation",
                    ]
                ],
                width="stretch",
            )


with tab_muscle:
    st.subheader("근육군별 분석")

    if muscle_weekly_filtered.empty:
        st.warning("선택한 기간에 근육군 분석 데이터가 없습니다.")
    else:
        st.markdown("### 주차별 근육군 볼륨 변화")
        st.altair_chart(make_muscle_volume_line_chart(muscle_weekly_filtered), width="stretch")

        st.markdown("### 선택 기간 근육군별 총 볼륨")

        muscle_total = (
            muscle_weekly_filtered.groupby("muscle_group", as_index=False)["muscle_volume"]
            .sum()
            .sort_values("muscle_volume", ascending=False)
        )

        muscle_total_chart = (
            alt.Chart(muscle_total)
            .mark_bar(color=PRIMARY_PURPLE)
            .encode(
                x=alt.X("muscle_group:N", title="근육군", sort="-y"),
                y=alt.Y("muscle_volume:Q", title="총 볼륨"),
                tooltip=[
                    alt.Tooltip("muscle_group:N", title="근육군"),
                    alt.Tooltip("muscle_volume:Q", title="총 볼륨", format=",.0f"),
                ],
            )
            .properties(height=380)
        )

        st.altair_chart(muscle_total_chart, width="stretch")

        st.markdown("### RPE 기반 근육군별 자극도 변화")

        stimulus_chart = make_muscle_stimulus_line_chart(muscle_weekly_filtered)

        if stimulus_chart is None:
            st.info("선택한 기간에 RPE 기반 자극도 데이터가 없습니다.")
        else:
            st.altair_chart(stimulus_chart, width="stretch")

        st.markdown("### 주간 근비대 부족 부위")

        acsm_check = build_acsm_hypertrophy_check(
            calc_workout,
            weekly_set_target=ACSM_WEEKLY_SET_TARGET,
        )

        if acsm_check.empty:
            st.info("주간 세트 기준 부족 부위를 계산할 수 없습니다.")
        else:
            acsm_filtered = acsm_check[
                (acsm_check["week_start"] >= start_date)
                & (acsm_check["week_start"] <= end_date)
                & (acsm_check["muscle_group"].isin(selected_muscles))
            ].copy()

            if acsm_filtered.empty:
                st.info("선택한 기간에 주간 세트 기준 평가 데이터가 없습니다.")
            else:
                latest_week = acsm_filtered["week_start"].max()
                latest_acsm = acsm_filtered[acsm_filtered["week_start"] == latest_week].copy()
                insufficient = latest_acsm[latest_acsm["status"] == "부족"].copy()

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("평가 주차", latest_week.strftime("%Y-%m-%d"))

                with col2:
                    st.metric("부족 근육군 수", f"{len(insufficient)} 개")

                with col3:
                    st.metric("기준", f"주당 {ACSM_WEEKLY_SET_TARGET} 가중 세트")

                acsm_chart = (
                    alt.Chart(latest_acsm)
                    .mark_bar()
                    .encode(
                        x=alt.X("muscle_group:N", title="근육군", sort="-y"),
                        y=alt.Y("weighted_sets:Q", title="가중 세트 수"),
                        color=alt.Color(
                            "status:N",
                            title="상태",
                            scale=alt.Scale(
                                domain=["충분", "부족"],
                                range=["#2DD4BF", "#F87171"],
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("muscle_group:N", title="근육군"),
                            alt.Tooltip("weighted_sets:Q", title="가중 세트", format=".1f"),
                            alt.Tooltip("target_sets:Q", title="기준 세트"),
                            alt.Tooltip("status:N", title="상태"),
                            alt.Tooltip("recommendation:N", title="권장"),
                        ],
                    )
                    .properties(height=380)
                )

                target_line = (
                    alt.Chart(pd.DataFrame({"target_sets": [ACSM_WEEKLY_SET_TARGET]}))
                    .mark_rule(strokeDash=[6, 4], color=PRIMARY_PURPLE)
                    .encode(y="target_sets:Q")
                )

                st.altair_chart(acsm_chart + target_line, width="stretch")

                st.dataframe(
                    latest_acsm[
                        [
                            "week_start",
                            "muscle_group",
                            "weighted_sets",
                            "target_sets",
                            "set_gap",
                            "status",
                            "recommendation",
                        ]
                    ].sort_values("weighted_sets"),
                    width="stretch",
                )

        st.markdown("### 근육군 주간 요약표")
        st.dataframe(muscle_weekly_filtered, width="stretch")


with tab_raw:
    st.subheader("원자료 확인")

    st.markdown("### WORKOUT_LOG 기반 계산")
    st.dataframe(workout_filtered, width="stretch")

    st.markdown("### SUMMARY_MUSCLE_WEEKLY")
    st.dataframe(muscle_weekly_filtered, width="stretch")

    st.markdown("### SUMMARY_INBODY")
    st.dataframe(inbody_filtered, width="stretch")

    st.markdown("### CALC_WORKOUT")
    if calc_workout_filtered.empty:
        st.info("CALC_WORKOUT 표시 데이터가 없습니다.")
    else:
        st.dataframe(calc_workout_filtered, width="stretch")


st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
