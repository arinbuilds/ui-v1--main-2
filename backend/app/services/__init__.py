"""Services / ML layer.

Every model, feature pipeline, graph algorithm and scoring rule lives here —
never in FastAPI route handlers and never in React.

    fraud_service            XGBoost fraud classification + orchestration
    repayment_service        XGBoost repayment-risk prediction
    anomaly_service          Isolation Forest anomaly detection
    scam_classification_service  XGBoost scam-category classification
    explanation_service      SHAP explainability + plain language rendering
    graph_service            NetworkX money-flow analysis
    intervention_service     recommended interventions + history
    early_warning_service    early financial-stress detection
    dashboard_service        backend aggregation for the dashboard
    feature_store            feature engineering (training == serving)
    training                 model training (XGBoost / Isolation Forest)
    model_registry           artifact loading + fallback contract
    rules                     deterministic fallback + signal attribution
    datagen                  deterministic synthetic demo dataset
"""
