# TECHMECHS Healthcare — Clinical Fall Risk Intelligence Platform

[![CI Pipeline](https://github.com/suryanshrathore964/NHH/actions/workflows/ci.yml/badge.svg)](https://github.com/suryanshrathore964/NHH/actions/workflows/ci.yml)
[![Accuracy](https://img.shields.io/badge/Model%20Accuracy-93.0%25-success?style=flat-square&logo=scikitlearn)](https://github.com/suryanshrathore964/NHH)
[![ROC-AUC](https://img.shields.io/badge/ROC--AUC-0.9864-blue?style=flat-square)](https://github.com/suryanshrathore964/NHH)
[![Python](https://img.shields.io/badge/Python-3.9%20%7C%203.10-3776AB?style=flat-square&logo=python&logoColor=white)](https://github.com/suryanshrathore964/NHH)
[![Flask](https://img.shields.io/badge/Flask-2.3+-black?style=flat-square&logo=flask)](https://github.com/suryanshrathore964/NHH)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/suryanshrathore964/NHH)

---

### 🌐 Live Production Demo
> **Live Web Application:** [🚀 Launch Clinical Command Center](https://nhh-fall-risk.onrender.com)
> 
> *Quick Access Credentials:*
> - **Doctor Username:** `demo_doctor`
> - **Password:** `Password123!`
> *(You can also click **"Create Account"** on the portal to register a new account instantly)*

---

Full-stack clinical intelligence platform that predicts patient fall risk using a 12-parameter clinical machine learning ensemble (Gradient Boosting, Calibrated Logistic Regression, and Random Forest) based on epidemiological clinical scales (Morse Fall Scale & Hendrich II).

## Tech Stack

- **Backend**: Python 3.9+, Flask, scikit-learn, ReportLab Platypus
- **ML Architecture**: Soft-Voting Clinical Ensemble (Gradient Boosting + Regularized Logistic Regression + Random Forest)
- **Evaluation Metrics**: 93.0% Accuracy, 94.8% Precision, 92.7% Recall, 0.9864 ROC-AUC
- **Frontend**: HTML5, Modern CSS3 (Pure White Clinical Theme), JavaScript, Chart.js
- **Model Persistence**: `pickle` (`model.pkl`)
- **Containerization & CI**: Dockerfile, Procfile, GitHub Actions CI Pipeline (Automated testing on Ubuntu)

## Features

- **12 Clinical Input Predictors**:
  - Demographics: Patient Age
  - Vital Signs: Systolic BP, Heart Rate
  - Mobility: Independent (0), Assisted (1), Bed-bound / Impaired (2)
  - Medication Profile: Active meds count, Sedatives / Hypnotics, Opioids, Anti-hypertensives
  - Clinical Conditions: Previous falls count, Post-surgery, Vision impairment, Mental status (Normal, Confused, Acute Delirium)
- **Clinical Ensemble Machine Learning**:
  - Calibrated soft voting ensemble combining tree-based non-linear patterns with regularized clinical log-odds
  - Clinical decision support layer with vital sign ceiling alerts
  - Stratified 80/20 train/test split on 7,000 multi-factorial encounters
- **Clinical Dashboard**:
  - Radial animated risk gauge (0–100%) with dynamic risk classification (Low / Moderate / Critical High)
  - Automated clinical care protocol generator (Estimated fall event window, bedside nurse observation rounds, priority observation windows, medication timing)
  - Itemized financial care billing estimation
  - 5-pane analytics hub (Risk Distribution doughnut, 12-Feature Importance bar, Age-Cohort Risk curve, Real-time Operational Stream, 2x2 Confusion Matrix)
  - Patient Census Registry table with live search and category filter pills
  - Emergency clinical dispatch directory (Mumbai, Delhi, Bangalore, Pune)
  - Alert ceiling thresholds & simulation dispatcher
  - Official Hospital-Grade PDF Audit Export (ReportLab Platypus)

## Run Locally

1. Create and activate a virtual environment:
   - macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Start the server:
   - `python app.py`
4. Open in browser:
   - `http://127.0.0.1:5001` (or `http://127.0.0.1:5000` if port 5000 is not used by macOS AirPlay)
   - You can also specify any custom port: `PORT=5001 python app.py`

## Login & Authentication

- You can click **"Create Account"** on the Sign In page to register any new account instantly.
- Existing demo credentials:
  - Username: `demo_doctor`
  - Password: `Password123!`

## API Endpoints

- `GET /api/dashboard` -> metrics, chart data, recent records
- `POST /api/predict` -> predict risk for one patient

Example `POST /api/predict` body:

```json
{
  "age": 78,
  "systolic_bp": 154,
  "heart_rate": 92,
  "mobility_status": 2,
  "medications_count": 7,
  "previous_falls": 2,
  "sedatives": 1,
  "opioids": 0,
  "anti_hypertensives": 1,
  "post_surgery": 0,
  "vision_impairment": 1,
  "mental_status": 1
}
```
