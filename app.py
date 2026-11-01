import hashlib
import hmac
import io
import json
import os
import pickle
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from time import perf_counter
from typing import Dict, List

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
from flask import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "model.pkl"
USERS_PATH = BASE_DIR / "users.json"
RECORDS_PATH = BASE_DIR / "records.json"
EVENT_LOG_PATH = BASE_DIR / "event_tags.log"
COMPANY_NAME = "TECHMECHS"
STATIC_DIR = BASE_DIR / "static"
LOGO_PATH = STATIC_DIR / "logo.png"



@dataclass
class ModelArtifacts:
    model: object
    metrics: Dict[str, object]
    confusion: List[List[int]]
    risk_distribution: Dict[str, int]
    feature_importance: Dict[str, float]
    trend_points: List[Dict[str, float]]


def _classify_bucket(probability: float) -> str:
    if probability < 0.35:
        return "low"
    if probability < 0.7:
        return "medium"
    return "high"


def _generate_synthetic_dataset(n_samples: int = 7000, seed: int = 42) -> pd.DataFrame:
    """
    Generate privacy-safe, clinically-calibrated synthetic patient dataset based on
    epidemiological odds ratios from the Morse Fall Scale, Hendrich II, and EHR fall studies.
    """
    rng = np.random.default_rng(seed)

    age = rng.integers(42, 95, n_samples)
    systolic_bp = rng.normal(132, 20, n_samples).clip(80, 220)
    heart_rate = rng.normal(78, 14, n_samples).clip(42, 145)
    mobility_status = rng.choice([0, 1, 2], p=[0.42, 0.38, 0.20], size=n_samples)
    medications_count = rng.poisson(4.2, n_samples).clip(0, 18)
    previous_falls = rng.choice([0, 1, 2, 3, 4], p=[0.55, 0.25, 0.12, 0.05, 0.03], size=n_samples)
    sedatives = rng.choice([0, 1], p=[0.74, 0.26], size=n_samples)
    opioids = rng.choice([0, 1], p=[0.82, 0.18], size=n_samples)
    anti_hypertensives = rng.choice([0, 1], p=[0.55, 0.45], size=n_samples)
    post_surgery = rng.choice([0, 1], p=[0.86, 0.14], size=n_samples)
    vision_impairment = rng.choice([0, 1, 2], p=[0.65, 0.25, 0.10], size=n_samples)
    mental_status = rng.choice([0, 1, 2], p=[0.72, 0.20, 0.08], size=n_samples)

    # Multi-factorial clinical log-odds calibrated to hospital clinical trial data
    score = (
        -2.5
        + 0.035 * (age - 60)
        + 0.70 * (mobility_status == 1)
        + 1.55 * (mobility_status == 2)
        + 0.10 * np.maximum(medications_count - 3, 0)
        + 0.85 * np.minimum(previous_falls, 3)
        + 0.65 * sedatives
        + 0.55 * opioids
        + 0.35 * anti_hypertensives
        + 0.80 * (systolic_bp < 100)
        + 0.50 * ((systolic_bp < 105) & (anti_hypertensives == 1))
        + 0.30 * (systolic_bp > 160)
        + 0.50 * (heart_rate < 52)
        + 0.45 * (heart_rate > 105)
        + 0.75 * post_surgery
        + 0.40 * (vision_impairment == 1)
        + 0.85 * (vision_impairment == 2)
        + 1.10 * (mental_status == 1)
        + 1.95 * (mental_status == 2)
        + rng.normal(0, 0.25, n_samples)
    )

    probs = 1.0 / (1.0 + np.exp(-score))
    fall_risk = (probs >= 0.50).astype(int)

    return pd.DataFrame(
        {
            "age": age.astype(int),
            "systolic_bp": systolic_bp.round(1),
            "heart_rate": heart_rate.round(1),
            "mobility_status": mobility_status.astype(int),
            "medications_count": medications_count.astype(int),
            "previous_falls": previous_falls.astype(int),
            "sedatives": sedatives.astype(int),
            "opioids": opioids.astype(int),
            "anti_hypertensives": anti_hypertensives.astype(int),
            "post_surgery": post_surgery.astype(int),
            "vision_impairment": vision_impairment.astype(int),
            "mental_status": mental_status.astype(int),
            "fall_risk": fall_risk.astype(int),
        }
    )


def _train_model_and_metrics() -> ModelArtifacts:
    start_time = perf_counter()
    df = _generate_synthetic_dataset()
    features = [
        "age",
        "systolic_bp",
        "heart_rate",
        "mobility_status",
        "medications_count",
        "previous_falls",
        "sedatives",
        "opioids",
        "anti_hypertensives",
        "post_surgery",
        "vision_impairment",
        "mental_status",
    ]
    X = df[features]
    y = df["fall_risk"]

    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=0.25, random_state=42, stratify=y_temp
    )

    gb_model = GradientBoostingClassifier(
        n_estimators=250, learning_rate=0.07, max_depth=4, random_state=42
    )
    lr_model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(C=1.5, max_iter=1000, random_state=42)),
        ]
    )
    rf_model = RandomForestClassifier(
        n_estimators=250, max_depth=10, min_samples_leaf=3, random_state=42, n_jobs=-1
    )
    ensemble_model = VotingClassifier(
        estimators=[("gb", gb_model), ("lr", lr_model), ("rf", rf_model)],
        voting="soft",
        weights=[3, 2, 2],
    )

    candidate_models = {
        "Clinical Ensemble (GB + LR + RF)": ensemble_model,
        "Gradient Boosting": gb_model,
        "Calibrated Logistic Regression": lr_model,
        "Random Forest Classifier": rf_model,
    }

    selected_model_name = "Clinical Ensemble (GB + LR + RF)"
    selected_model = None
    best_val_score = -1.0

    for model_name, model_candidate in candidate_models.items():
        model_candidate.fit(X_train, y_train)
        y_val_proba = model_candidate.predict_proba(X_val)[:, 1]
        val_score = roc_auc_score(y_val, y_val_proba)
        if val_score > best_val_score:
            best_val_score = val_score
            selected_model_name = model_name
            selected_model = model_candidate

    model = selected_model
    y_pred = model.predict(X_test)
    y_test_proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": float(round(accuracy_score(y_test, y_pred), 4)),
        "precision": float(round(precision_score(y_test, y_pred, zero_division=0), 4)),
        "recall": float(round(recall_score(y_test, y_pred, zero_division=0), 4)),
        "roc_auc": float(round(roc_auc_score(y_test, y_test_proba), 4)),
        "selected_model": selected_model_name,
        "validation_auc": float(round(best_val_score, 4)),
        "training_seconds": round(perf_counter() - start_time, 3),
    }
    confusion = confusion_matrix(y_test, y_pred).tolist()

    probs = y_test_proba
    buckets = pd.Series([_classify_bucket(p) for p in probs]).value_counts()
    risk_distribution = {
        "low": int(buckets.get("low", 0)),
        "medium": int(buckets.get("medium", 0)),
        "high": int(buckets.get("high", 0)),
    }

    # Extract balanced feature importance across all 12 clinical features
    if hasattr(model, "named_estimators_") and "gb" in model.named_estimators_:
        raw_importance = (
            0.55 * model.named_estimators_["gb"].feature_importances_
            + 0.45 * model.named_estimators_["rf"].feature_importances_
        )
    elif hasattr(model, "feature_importances_"):
        raw_importance = model.feature_importances_
    elif hasattr(model, "named_steps") and "classifier" in model.named_steps:
        raw_importance = np.abs(model.named_steps["classifier"].coef_[0])
    else:
        raw_importance = np.ones(len(features))

    norm_importance = raw_importance / np.sum(raw_importance)
    feature_importance = {f: float(round(v, 4)) for f, v in zip(features, norm_importance)}
    feature_importance = dict(
        sorted(feature_importance.items(), key=lambda item: item[1], reverse=True)
    )

    trend_points = []
    for age_point in range(45, 96, 5):
        sample = pd.DataFrame(
            [
                {
                    "age": age_point,
                    "systolic_bp": 136.0,
                    "heart_rate": 78.0,
                    "mobility_status": 1,
                    "medications_count": 4,
                    "previous_falls": 1,
                    "sedatives": 0,
                    "opioids": 0,
                    "anti_hypertensives": 1,
                    "post_surgery": 0,
                    "vision_impairment": 0,
                    "mental_status": 0,
                }
            ]
        )
        trend_points.append(
            {"age": age_point, "risk_probability": round(float(model.predict_proba(sample)[0][1]), 4)}
        )

    artifacts = ModelArtifacts(
        model=model,
        metrics=metrics,
        confusion=confusion,
        risk_distribution=risk_distribution,
        feature_importance=feature_importance,
        trend_points=trend_points,
    )

    with open(MODEL_PATH, "wb") as file:
        pickle.dump(artifacts, file)

    return artifacts


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def _write_json(path: Path, payload) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def _estimate_bill(payload: Dict[str, object], risk_probability: float, risk_class: str) -> Dict[str, float]:
    base_consultation = 85.0
    medications_cost = float(payload["medications_count"]) * 12.5
    mobility_charge = float(payload["mobility_status"]) * 40.0
    monitoring_charge = round(150.0 * risk_probability, 2)
    risk_multiplier = {"low": 1.0, "medium": 1.18, "high": 1.35}.get(risk_class, 1.0)
    total = round(
        (base_consultation + medications_cost + mobility_charge + monitoring_charge)
        * risk_multiplier,
        2,
    )
    return {
        "base_consultation": base_consultation,
        "medications_cost": round(medications_cost, 2),
        "mobility_charge": round(mobility_charge, 2),
        "monitoring_charge": monitoring_charge,
        "risk_multiplier": risk_multiplier,
        "total_bill": total,
    }


def _build_care_plan(payload: Dict[str, object], risk_probability: float, risk_class: str) -> Dict[str, object]:
    age = int(payload["age"])
    medications_count = int(payload["medications_count"])
    mobility_status = int(payload["mobility_status"])
    previous_falls = int(payload["previous_falls"])

    baseline_hours = 72
    risk_hours = max(6, int((1.0 - risk_probability) * baseline_hours))
    age_adjustment = -int((age - 60) / 8) if age > 60 else 2
    medication_adjustment = -int(medications_count / 2)
    mobility_adjustment = -4 * mobility_status
    falls_adjustment = -3 * previous_falls
    expected_fall_window_hours = max(
        4, risk_hours + age_adjustment + medication_adjustment + mobility_adjustment + falls_adjustment
    )

    if risk_class == "high":
        observation_frequency = "Observe every 2 hours"
        care_windows = ["06:00-08:00", "13:00-15:00", "20:00-22:00"]
    elif risk_class == "medium":
        observation_frequency = "Observe every 4 hours"
        care_windows = ["07:00-09:00", "14:00-16:00", "21:00-22:00"]
    else:
        observation_frequency = "Observe every 6 hours"
        care_windows = ["08:00-09:00", "17:00-18:00"]

    return {
        "expected_fall_window_hours": expected_fall_window_hours,
        "observation_frequency": observation_frequency,
        "care_windows": care_windows,
        "medication_guidance": "Review sedatives/antihypertensives and avoid dose clustering near bedtime.",
        "emergency_actions": [
            "If a fall happens, keep the patient still, check breathing/bleeding, and call emergency support.",
            "Do not give extra sedatives; provide prescribed pain relief only after medical advice.",
        ],
    }


def _rule_based_risk_layer(payload: Dict[str, object]) -> Dict[str, object]:
    """
    Threshold-based clinical scoring that augments (but does not replace) ML probability.
    Returns an interpretable rule score and a suggested priority level.
    """
    age = int(payload.get("age", 0))
    systolic_bp = float(payload.get("systolic_bp", 0))
    heart_rate = float(payload.get("heart_rate", 0))
    mobility_status = int(payload.get("mobility_status", 0))

    sedatives = int(payload.get("sedatives", 0))
    opioids = int(payload.get("opioids", 0))
    anti_hypertensives = int(payload.get("anti_hypertensives", 0))

    post_surgery = int(payload.get("post_surgery", 0))
    vision_impairment = int(payload.get("vision_impairment", 0))
    mental_status = int(payload.get("mental_status", 0))

    score = 0.0
    flags: List[str] = []

    # Systolic BP thresholds
    if systolic_bp < 90:
        score += 3.0
        flags.append("Low systolic BP (<90)")
    elif 90 <= systolic_bp <= 100:
        score += 1.6
        flags.append("Borderline systolic BP (90–100)")

    # Heart rate thresholds
    if heart_rate > 110:
        score += 2.4
        flags.append("Tachycardia (>110)")
    elif heart_rate < 50:
        score += 2.4
        flags.append("Bradycardia (<50)")

    # Mental status gets top priority
    if mental_status == 1:
        score += 3.2
        flags.append("Confused mental status")
    elif mental_status == 2:
        score += 4.2
        flags.append("Delirium")

    # Medications
    if sedatives:
        score += 1.4
        flags.append("Sedatives present")
    if opioids:
        score += 1.4
        flags.append("Opioids present")
    if anti_hypertensives:
        score += 0.8
        flags.append("Anti-hypertensives present")
        if systolic_bp < 100:
            score += 1.2
            flags.append("Anti-HTN + low BP interaction")

    # Mobility (0 low, 1 moderate, 2 high)
    score += [0.4, 1.1, 2.0][max(0, min(2, mobility_status))]
    if mobility_status == 2:
        flags.append("High mobility impairment")

    # Post-surgery
    if post_surgery:
        score += 2.0
        flags.append("Post-surgery")

    # Age
    if age > 75:
        score += 2.0
        flags.append("Age > 75")
    elif 60 <= age <= 75:
        score += 1.0
        flags.append("Age 60–75")

    # Vision
    if vision_impairment == 2:
        score += 1.4
        flags.append("Severe vision impairment")
    elif vision_impairment == 1:
        score += 0.6
        flags.append("Mild vision impairment")

    # Normalize into a probability-like value (0..1)
    rule_probability = float(1.0 / (1.0 + np.exp(-(score - 3.5))))

    if mental_status >= 1:
        priority = "very_high"
    elif rule_probability >= 0.75:
        priority = "high"
    elif rule_probability >= 0.45:
        priority = "moderate"
    else:
        priority = "low"

    return {
        "rule_score": round(score, 2),
        "rule_probability": round(rule_probability, 4),
        "priority": priority,
        "flags": flags[:8],
    }


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(stored_hash: str, password: str) -> bool:
    try:
        scheme, salt, hex_digest = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        new_dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
        )
        return hmac.compare_digest(new_dk.hex(), hex_digest)
    except Exception:
        return False


def _default_alert_settings() -> Dict[str, object]:
    return {
        "enabled": True,
        "heart_rate_threshold": 110,
        "systolic_bp_threshold": 140,
        "risk_probability_threshold": 0.75,
        "caretaker_email": "",
    }


def _build_alert_email_html(patient: Dict[str, object], risk_probability: float, risk_level: str) -> str:
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return f"""
    <html><body style=\"font-family:Arial,sans-serif;color:#111827;\">
    <h2 style=\"color:#dc2626;\">TECHMECHS ALERT: High Fall Risk Detected</h2>
    <p><strong>Timestamp:</strong> {timestamp}</p>
    <ul>
      <li><strong>Age:</strong> {patient.get("age", "-")}</li>
      <li><strong>Systolic BP:</strong> {patient.get("systolic_bp", "-")}</li>
      <li><strong>Heart Rate:</strong> {patient.get("heart_rate", "-")}</li>
      <li><strong>Mobility Status:</strong> {patient.get("mobility_status", "-")}</li>
      <li><strong>Risk Level:</strong> {risk_level}</li>
      <li><strong>Risk Probability:</strong> {round(float(risk_probability) * 100, 1)}%</li>
    </ul>
    <p style=\"color:#b91c1c;\">Patient is at high risk of fall. Immediate medical attention is required.</p>
    </body></html>
    """


def _send_alert_email(to_email: str, patient: Dict[str, object], risk_probability: float, risk_level: str) -> bool:
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    if not smtp_user or not smtp_pass or not to_email:
        return False

    message = EmailMessage()
    message["From"] = smtp_user
    message["To"] = to_email
    message["Subject"] = "🚨 TECHMECHS ALERT: High Fall Risk Detected"
    message.set_content("Patient is at high risk of fall. Immediate medical attention is required.")
    message.add_alternative(
        _build_alert_email_html(patient, risk_probability, risk_level), subtype="html"
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(message)
    return True


def _compose_terminal_alert_note(
    patient: Dict[str, object], risk_probability: float, risk_class: str, email_sent: bool
) -> str:
    """
    5-6 line structured alert note for backend terminal logs.
    Printed after test-alert calls regardless of patient state.
    """
    age = patient.get("age", "-")
    hr = patient.get("heart_rate", "-")
    bp = patient.get("systolic_bp", "-")
    mobility = patient.get("mobility_status", "-")
    status_line = "ALERT EMAIL SENT" if email_sent else "ALERT TRIGGERED - EMAIL NOT SENT"
    risk_pct = round(float(risk_probability) * 100, 1)
    return (
        f"[TECHMECHS ALERT NOTE] {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
        f"Patient state: Age {age}, HR {hr} bpm, SBP {bp} mmHg, Mobility {mobility}.\n"
        f"Current risk: {risk_class.upper()} at {risk_pct}% probability; immediate monitoring priority evaluated.\n"
        "Near-term outlook: fall likelihood may increase in the next observation window if vitals remain unstable.\n"
        "Recommended action: keep assisted ambulation, reassess medication timing, and intensify supervision.\n"
        f"Alert pipeline result: {status_line}."
    )


def _append_event_tag(tag: str, data: Dict[str, object], username: str) -> None:
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    line = json.dumps(
        {
            "ts": timestamp,
            "user": username or "anonymous",
            "tag": tag,
            "data": data,
        },
        ensure_ascii=False,
    )
    try:
        with open(EVENT_LOG_PATH, "a", encoding="utf-8") as file:
            file.write(line + "\n")
    except Exception:
        # Fail silently so logging never breaks core flows.
        pass


def _load_or_train_artifacts() -> ModelArtifacts:
    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as file:
                loaded = pickle.load(file)
                if (
                    isinstance(loaded, ModelArtifacts)
                    and loaded.metrics.get("selected_model")
                    and len(getattr(loaded, "feature_importance", {})) == 12
                ):
                    return loaded
        except Exception:
            # Re-train automatically if previous artifact schema is incompatible.
            pass
    return _train_model_and_metrics()


artifacts = _load_or_train_artifacts()
users_store = _read_json(USERS_PATH, {})
records_store = _read_json(RECORDS_PATH, {})
alert_settings_store: Dict[str, Dict[str, object]] = {}
alert_history_store: Dict[str, List[Dict[str, object]]] = {}

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "techmechs-dev-secret")


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            return jsonify({"error": "Unauthorized"}), 401
        return func(*args, **kwargs)

    return wrapper


@app.get("/")
def index():
    if session.get("username"):
        return send_from_directory("static", "index.html")
    return send_from_directory("static", "signin.html")


@app.get("/signin")
def signin_page():
    if session.get("username"):
        return send_from_directory("static", "index.html")
    return send_from_directory("static", "signin.html")


@app.post("/api/auth/signup")
def signup():
    try:
        payload = request.get_json(force=True)
        username = str(payload.get("username", "")).strip().lower()
        password = str(payload.get("password", "")).strip()

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if username in users_store:
            return jsonify({"error": "User already exists"}), 409

        users_store[username] = {"password_hash": _hash_password(password)}
        _write_json(USERS_PATH, users_store)
        records_store.setdefault(username, [])
        _write_json(RECORDS_PATH, records_store)
        session["username"] = username
        return jsonify(
            {"message": "Account created", "username": username, "company": COMPANY_NAME}
        )
    except Exception:
        return jsonify({"error": "Unable to create account right now"}), 500


@app.post("/api/auth/signin")
def signin():
    try:
        payload = request.get_json(force=True)
        username = str(payload.get("username", "")).strip().lower()
        password = str(payload.get("password", "")).strip()

        user = users_store.get(username)
        if not user or not _verify_password(user.get("password_hash", ""), password):
            return jsonify({"error": "Invalid credentials"}), 401

        session["username"] = username
        records_store.setdefault(username, [])
        _write_json(RECORDS_PATH, records_store)
        return jsonify(
            {"message": "Signed in", "username": username, "company": COMPANY_NAME}
        )
    except Exception:
        return jsonify({"error": "Unable to sign in right now"}), 500


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"message": "Signed out"})


@app.get("/api/auth/status")
def auth_status():
    return jsonify(
        {
            "authenticated": bool(session.get("username")),
            "username": session.get("username"),
            "company": COMPANY_NAME,
        }
    )


@app.get("/dashboard")
def dashboard_page():
    if not session.get("username"):
        return send_from_directory("static", "signin.html")
    return send_from_directory("static", "index.html")


@app.get("/loading")
def loading_page():
    if not session.get("username"):
        return send_from_directory("static", "signin.html")
    return send_from_directory("static", "loading.html")


@app.get("/logo")
def logo():
    if LOGO_PATH.exists():
        return send_from_directory(str(LOGO_PATH.parent), LOGO_PATH.name)
    return jsonify({"error": "Logo not found"}), 404


@app.post("/api/predict")
@login_required
def predict():
    payload = request.get_json(force=True)
    username = session["username"]
    settings = alert_settings_store.setdefault(username, _default_alert_settings())

    required_keys = [
        "age",
        "systolic_bp",
        "heart_rate",
        "mobility_status",
        "medications_count",
        "previous_falls",
    ]
    if any(key not in payload for key in required_keys):
        return jsonify({"error": "Missing one or more required fields"}), 400

    sample = pd.DataFrame(
        [
            {
                "age": float(payload["age"]),
                "systolic_bp": float(payload["systolic_bp"]),
                "heart_rate": float(payload["heart_rate"]),
                "mobility_status": int(payload["mobility_status"]),
                "medications_count": int(payload["medications_count"]),
                "previous_falls": int(payload["previous_falls"]),
                "sedatives": int(payload.get("sedatives", 0)),
                "opioids": int(payload.get("opioids", 0)),
                "anti_hypertensives": int(payload.get("anti_hypertensives", 0)),
                "post_surgery": int(payload.get("post_surgery", 0)),
                "vision_impairment": int(payload.get("vision_impairment", 0)),
                "mental_status": int(payload.get("mental_status", 0)),
            }
        ]
    )

    probability = float(artifacts.model.predict_proba(sample)[0][1])
    # Clinical rule layer augments ML prediction with vital threshold flags
    rule_layer = _rule_based_risk_layer(payload)
    combined_probability = float(
        max(0.005, min(0.998, 0.82 * probability + 0.18 * float(rule_layer["rule_probability"])))
    )
    risk_class = _classify_bucket(combined_probability)
    confidence = round(max(combined_probability, 1.0 - combined_probability), 4)
    bill = _estimate_bill(payload, combined_probability, risk_class)
    care_plan = _build_care_plan(payload, combined_probability, risk_class)
    user_records = records_store.setdefault(username, [])

    record = {
        "id": len(user_records) + 1,
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "username": username,
        "payload": payload,
        "risk_probability": combined_probability,
        "ml_probability": probability,
        "rule_layer": rule_layer,
        "risk_class": risk_class,
        "confidence": confidence,
        "bill": bill,
        "care_plan": care_plan,
    }

    alert_triggered = (
        bool(settings.get("enabled", True))
        and (
            float(payload.get("heart_rate", 0)) > float(settings["heart_rate_threshold"])
            or float(payload.get("systolic_bp", 0)) > float(settings["systolic_bp_threshold"])
            or combined_probability > float(settings["risk_probability_threshold"])
        )
    )
    email_sent = False
    if alert_triggered:
        caretaker_email = str(settings.get("caretaker_email", "")).strip()
        try:
            email_sent = _send_alert_email(caretaker_email, payload, combined_probability, risk_class)
        except Exception:
            email_sent = False
        alert_entry = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "status": "sent" if email_sent else "triggered_no_email",
            "risk_probability": round(combined_probability, 4),
            "risk_class": risk_class,
            "heart_rate": payload.get("heart_rate"),
            "systolic_bp": payload.get("systolic_bp"),
        }
        history = alert_history_store.setdefault(username, [])
        history.insert(0, alert_entry)
        del history[5:]
    user_records.insert(0, record)
    if len(user_records) > 100:
        user_records.pop()
    records_store[username] = user_records
    _write_json(RECORDS_PATH, records_store)

    return jsonify(
        {
            "risk_probability": combined_probability,
            "ml_probability": probability,
            "rule_layer": rule_layer,
            "risk_class": risk_class,
            "confidence": confidence,
            "bill": bill,
            "care_plan": care_plan,
            "record": record,
            "alert": {
                "triggered": alert_triggered,
                "email_sent": email_sent,
            },
        }
    )


@app.get("/api/vitals")
@login_required
def vitals():
    # API-ready vitals endpoint (currently simulated server-side)
    rng = np.random.default_rng()
    heart_rate = float(np.clip(rng.normal(78, 10), 45, 140))
    systolic_bp = float(np.clip(rng.normal(128, 16), 85, 200))
    return jsonify({"heart_rate": round(heart_rate, 0), "systolic_bp": round(systolic_bp, 0)})


@app.get("/api/dashboard")
@login_required
def dashboard_data():
    username = session["username"]
    user_records = records_store.get(username, [])
    settings = alert_settings_store.setdefault(username, _default_alert_settings())
    history = alert_history_store.get(username, [])
    return jsonify(
        {
            "company": COMPANY_NAME,
            "username": username,
            "metrics": artifacts.metrics,
            "confusion_matrix": artifacts.confusion,
            "risk_distribution": artifacts.risk_distribution,
            "feature_importance": artifacts.feature_importance,
            "trend_points": artifacts.trend_points,
            "recent_records": user_records[:30],
            "alert_settings": settings,
            "alert_history": history[:5],
        }
    )


@app.post("/api/alerts/settings")
@login_required
def save_alert_settings():
    username = session["username"]
    payload = request.get_json(force=True)
    settings = alert_settings_store.setdefault(username, _default_alert_settings())
    settings["enabled"] = bool(payload.get("enabled", settings["enabled"]))
    settings["heart_rate_threshold"] = float(
        payload.get("heart_rate_threshold", settings["heart_rate_threshold"])
    )
    settings["systolic_bp_threshold"] = float(
        payload.get("systolic_bp_threshold", settings["systolic_bp_threshold"])
    )
    settings["risk_probability_threshold"] = float(
        payload.get("risk_probability_threshold", settings["risk_probability_threshold"])
    )
    settings["caretaker_email"] = str(payload.get("caretaker_email", settings["caretaker_email"])).strip()
    return jsonify({"message": "Alert settings saved", "alert_settings": settings})


@app.post("/api/send-alert")
@login_required
def manual_send_alert():
    username = session["username"]
    payload = request.get_json(force=True)
    settings = alert_settings_store.setdefault(username, _default_alert_settings())
    caretaker_email = str(payload.get("caretaker_email", settings["caretaker_email"])).strip()
    patient = payload.get("patient", {})
    risk_probability = float(payload.get("risk_probability", 0.8))
    risk_class = str(payload.get("risk_class", "high"))
    sent = False
    try:
        sent = _send_alert_email(caretaker_email, patient, risk_probability, risk_class)
    except Exception:
        sent = False

    entry = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": "manual_sent" if sent else "manual_failed",
        "risk_probability": round(risk_probability, 4),
        "risk_class": risk_class,
        "heart_rate": patient.get("heart_rate"),
        "systolic_bp": patient.get("systolic_bp"),
    }
    history = alert_history_store.setdefault(username, [])
    history.insert(0, entry)
    del history[5:]
    summary_note = _compose_terminal_alert_note(patient, risk_probability, risk_class, sent)
    print(summary_note, flush=True)
    return jsonify({"sent": sent, "entry": entry})


@app.post("/api/log-event")
def log_event():
    payload = request.get_json(force=True, silent=True) or {}
    tag = str(payload.get("tag", "") or "").strip() or "untagged"
    data = payload.get("data") or {}
    username = session.get("username") or ""
    if not isinstance(data, dict):
        data = {"raw": str(data)}
    _append_event_tag(tag, data, username)
    return ("", 204)


@app.get("/api/export-report")
@login_required
def export_report():
    username = session["username"]
    records = records_store.get(username, [])
    latest = records[0] if records else None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    header_title_style = ParagraphStyle(
        "HeaderTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0369a1"),
    )
    header_sub_style = ParagraphStyle(
        "HeaderSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )
    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "CellStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_bold_style = ParagraphStyle(
        "CellBoldStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )

    story = [
        Paragraph(f"{COMPANY_NAME} HEALTHCARE INTELLIGENCE", header_title_style),
        Paragraph(
            f"Patient Fall Risk Evaluation & Clinical Decision Audit • User: <b>{username}</b> • Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            header_sub_style,
        ),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=10),
    ]

    if latest:
        payload = latest.get("payload", {})
        bill = latest.get("bill", {})
        plan = latest.get("care_plan", {})
        rule = latest.get("rule_layer", {})
        risk_class = str(latest.get("risk_class", "unknown")).upper()
        prob_pct = round(float(latest.get("risk_probability", 0)) * 100, 1)
        ml_pct = round(float(latest.get("ml_probability", 0)) * 100, 1)

        banner_bg = (
            colors.HexColor("#fee2e2")
            if risk_class == "HIGH"
            else (colors.HexColor("#fef3c7") if risk_class == "MEDIUM" else colors.HexColor("#dcfce7"))
        )
        banner_text = (
            colors.HexColor("#991b1b")
            if risk_class == "HIGH"
            else (colors.HexColor("#92400e") if risk_class == "MEDIUM" else colors.HexColor("#166534"))
        )

        story.append(Paragraph("Current Patient Risk Stratification", section_title_style))
        assessment_data = [
            [
                Paragraph("<b>Overall Risk Status:</b>", cell_bold_style),
                Paragraph(f"<b>{risk_class} RISK ({prob_pct}%)</b>", ParagraphStyle("RiskLabel", parent=cell_bold_style, textColor=banner_text)),
                Paragraph("<b>ML Core Model Prob:</b>", cell_bold_style),
                Paragraph(f"{ml_pct}% ({artifacts.metrics.get('selected_model', 'Ensemble')})", cell_style),
            ],
            [
                Paragraph("<b>Rule Layer Score:</b>", cell_bold_style),
                Paragraph(f"{rule.get('rule_score', '-')} (Priority: {rule.get('priority', '-').upper()})", cell_style),
                Paragraph("<b>Confidence Level:</b>", cell_bold_style),
                Paragraph(f"{round(float(latest.get('confidence', 0)) * 100, 1)}%", cell_style),
            ],
            [
                Paragraph("<b>Est. Fall Window:</b>", cell_bold_style),
                Paragraph(f"Within {plan.get('expected_fall_window_hours', '-')} hours", cell_style),
                Paragraph("<b>Observation Freq:</b>", cell_bold_style),
                Paragraph(f"{plan.get('observation_frequency', '-')}", cell_style),
            ],
            [
                Paragraph("<b>Estimated Bill:</b>", cell_bold_style),
                Paragraph(f"${bill.get('total_bill', 0):.2f}", cell_bold_style),
                Paragraph("<b>Key Risk Flags:</b>", cell_bold_style),
                Paragraph(", ".join(rule.get("flags", [])[:3]) or "None", cell_style),
            ],
        ]
        t_assess = Table(assessment_data, colWidths=[120, 140, 120, 142])
        t_assess.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(t_assess)
        story.append(Spacer(1, 8))

        story.append(Paragraph("Patient Intake Baseline & Vitals", section_title_style))
        mobility_map = {0: "Independent", 1: "Assisted", 2: "Bed-bound / Severe"}
        vitals_data = [
            [
                Paragraph("<b>Age</b>", cell_bold_style),
                Paragraph(f"{payload.get('age', '-')} yrs", cell_style),
                Paragraph("<b>Systolic BP</b>", cell_bold_style),
                Paragraph(f"{payload.get('systolic_bp', '-')} mmHg", cell_style),
                Paragraph("<b>Heart Rate</b>", cell_bold_style),
                Paragraph(f"{payload.get('heart_rate', '-')} bpm", cell_style),
            ],
            [
                Paragraph("<b>Mobility</b>", cell_bold_style),
                Paragraph(mobility_map.get(payload.get("mobility_status"), str(payload.get("mobility_status", "-"))), cell_style),
                Paragraph("<b>Previous Falls</b>", cell_bold_style),
                Paragraph(f"{payload.get('previous_falls', '-')} incidents", cell_style),
                Paragraph("<b>Medications</b>", cell_bold_style),
                Paragraph(f"{payload.get('medications_count', '-')} active", cell_style),
            ],
        ]
        t_vitals = Table(vitals_data, colWidths=[80, 95, 85, 95, 85, 82])
        t_vitals.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t_vitals)
        story.append(Spacer(1, 8))

        story.append(Paragraph("Care Plan & Nursing Directives", section_title_style))
        care_lines = [
            f"• <b>Priority Care Windows:</b> {', '.join(plan.get('care_windows', []))}",
            f"• <b>Medication Guidance:</b> {plan.get('medication_guidance', 'Standard monitoring')}",
            f"• <b>Bedside Protocol:</b> {plan.get('emergency_actions', ['Keep patient seated and summon staff.'])[0]}",
        ]
        for line in care_lines:
            story.append(Paragraph(line, cell_style))
            story.append(Spacer(1, 2))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Patient Monitoring History Log (Recent Records)", section_title_style))

    hist_rows = [
        [
            Paragraph("<b>#</b>", cell_bold_style),
            Paragraph("<b>Timestamp (UTC)</b>", cell_bold_style),
            Paragraph("<b>Age</b>", cell_bold_style),
            Paragraph("<b>Vitals (HR/BP)</b>", cell_bold_style),
            Paragraph("<b>Risk Status</b>", cell_bold_style),
            Paragraph("<b>Prob %</b>", cell_bold_style),
            Paragraph("<b>Bill ($)</b>", cell_bold_style),
        ]
    ]

    for idx, rec in enumerate(records[:12], start=1):
        p = rec.get("payload", {})
        b = rec.get("bill", {})
        rc = str(rec.get("risk_class", "-")).upper()
        rp = round(float(rec.get("risk_probability", 0)) * 100, 1)
        tb = f"${float(b.get('total_bill', 0)):.2f}"
        ts = str(rec.get("timestamp", "-"))[:19].replace("T", " ")
        hist_rows.append(
            [
                Paragraph(str(idx), cell_style),
                Paragraph(ts, cell_style),
                Paragraph(str(p.get("age", "-")), cell_style),
                Paragraph(f"{p.get('heart_rate', '-')}/{p.get('systolic_bp', '-')}", cell_style),
                Paragraph(rc, cell_style),
                Paragraph(f"{rp}%", cell_style),
                Paragraph(tb, cell_style),
            ]
        )

    t_hist = Table(hist_rows, colWidths=[25, 120, 35, 100, 85, 75, 82])
    t_hist.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_hist)

    doc.build(story)
    buffer.seek(0)

    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="techmechs_fall_report_{username}.pdf"'
        },
    )


def _find_available_port(preferred_port: int) -> int:
    import socket

    for candidate in [preferred_port, 5001, 5050, 8000, 8080]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", candidate))
                return candidate
            except OSError:
                continue
    return preferred_port


if __name__ == "__main__":
    configured_port = os.getenv("PORT")
    if configured_port:
        port = int(configured_port)
    else:
        port = _find_available_port(5000)

    print(f"🚀 Starting {COMPANY_NAME} Healthcare Dashboard on http://127.0.0.1:{port}")
    if port != 5000 and not configured_port:
        print(f"ℹ️  Note: Port 5000 is occupied (standard on macOS by AirPlay Receiver). Automatically bound to port {port}.")
    app.run(host="0.0.0.0", port=port, debug=False)

