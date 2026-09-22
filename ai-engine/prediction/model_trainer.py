"""
Threat Prediction Model Trainer.
Trains RandomForest and LSTM models for fight/surge/breach/access threat prediction.

Usage:
    python -m ai_engine.prediction.model_trainer --model rf   # Train Random Forest
    python -m ai_engine.prediction.model_trainer --model lstm # Train LSTM
    python -m ai_engine.prediction.model_trainer --model all  # Both
"""
import argparse
import os
import pickle
import json
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

MODEL_DIR = "/app/models/prediction"


# ─── Feature extraction ───────────────────────────────────────────────────────

def extract_features_from_db(hours_back: int = 168) -> tuple:
    """Pull historical behavior data and build supervised training set."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    engine = create_engine(settings.SYNC_DATABASE_URL)
    since = datetime.utcnow() - timedelta(hours=hours_back)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                b.camera_id,
                EXTRACT(HOUR FROM b.logged_at)::int        AS hour_of_day,
                EXTRACT(DOW FROM b.logged_at)::int         AS day_of_week,
                b.person_count,
                b.risk_score,
                b.duration_secs,
                b.behavior_type,
                COALESCE(
                    LAG(b.person_count) OVER (PARTITION BY b.camera_id ORDER BY b.logged_at), 0
                )::float                                   AS prev_person_count,
                COALESCE(
                    LAG(b.risk_score) OVER (PARTITION BY b.camera_id ORDER BY b.logged_at), 0
                )::float                                   AS prev_risk,
                COUNT(*) FILTER (WHERE b.behavior_type = 'loitering')
                    OVER (PARTITION BY b.camera_id ORDER BY b.logged_at
                          ROWS BETWEEN 5 PRECEDING AND CURRENT ROW)::float AS recent_loitering,
                COUNT(*) FILTER (WHERE b.behavior_type = 'crowd_density')
                    OVER (PARTITION BY b.camera_id ORDER BY b.logged_at
                          ROWS BETWEEN 5 PRECEDING AND CURRENT ROW)::float AS recent_crowd,
                -- Label: high risk in next 30 min
                LEAD(b.risk_score, 3) OVER (PARTITION BY b.camera_id ORDER BY b.logged_at) AS future_risk
            FROM behavior_logs b
            WHERE b.logged_at >= :since
            ORDER BY b.camera_id, b.logged_at
        """), {"since": since}).fetchall()

    if not rows:
        logger.warning("No training data found — run the data seeder first")
        return np.array([]), np.array([])

    X, y = [], []
    for row in rows:
        if row.future_risk is None:
            continue
        features = [
            row.hour_of_day / 23.0,
            row.day_of_week / 6.0,
            min(row.person_count / 50.0, 1.0),
            row.risk_score,
            min(row.duration_secs / 300.0, 1.0),
            row.prev_person_count / 50.0,
            row.prev_risk,
            row.recent_loitering / 5.0,
            row.recent_crowd / 5.0,
        ]
        label = 1 if row.future_risk > 0.5 else 0
        X.append(features)
        y.append(label)

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int32)


def _synthetic_training_data(n: int = 2000) -> tuple:
    """Generate synthetic data for offline testing when DB isn't available."""
    np.random.seed(42)
    X = np.random.rand(n, 9).astype(np.float32)
    # High person count + high previous risk → threat
    y = ((X[:, 2] > 0.6) & (X[:, 3] > 0.4)).astype(np.int32)
    return X, y


# ─── Random Forest trainer ────────────────────────────────────────────────────

def train_random_forest(X: np.ndarray, y: np.ndarray) -> dict:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report

    if len(X) == 0:
        logger.warning("No data — using synthetic data for RF training")
        X, y = _synthetic_training_data()

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42, stratify=y)

    rf = RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced",
                                 random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)

    gb = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42)
    gb.fit(X_train, y_train)

    rf_score = rf.score(X_test, y_test)
    gb_score = gb.score(X_test, y_test)
    best_model = rf if rf_score >= gb_score else gb
    best_name = "RandomForest" if rf_score >= gb_score else "GradientBoosting"

    logger.info(f"RF accuracy: {rf_score:.3f} | GB accuracy: {gb_score:.3f} → using {best_name}")
    logger.info("\n" + classification_report(y_test, best_model.predict(X_test),
                                              target_names=["safe", "threat"]))

    return {
        "model": best_model,
        "scaler": scaler,
        "accuracy": max(rf_score, gb_score),
        "model_type": best_name,
        "trained_at": datetime.utcnow().isoformat(),
        "feature_names": [
            "hour_of_day", "day_of_week", "person_count_norm", "risk_score",
            "duration_norm", "prev_person_count", "prev_risk",
            "recent_loitering", "recent_crowd"
        ],
    }


# ─── LSTM trainer ─────────────────────────────────────────────────────────────

def train_lstm(X: np.ndarray, y: np.ndarray, seq_len: int = 10) -> dict:
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        logger.warning("PyTorch not installed — skipping LSTM training")
        return {}

    if len(X) < seq_len * 2:
        logger.warning("Not enough data for LSTM — using synthetic")
        X, y = _synthetic_training_data(500)

    # Create sequences
    X_seq, y_seq = [], []
    for i in range(len(X) - seq_len):
        X_seq.append(X[i:i + seq_len])
        y_seq.append(y[i + seq_len])

    X_t = torch.tensor(np.array(X_seq), dtype=torch.float32)
    y_t = torch.tensor(np.array(y_seq), dtype=torch.float32)

    dataset = TensorDataset(X_t, y_t)
    train_size = int(0.8 * len(dataset))
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, len(dataset) - train_size])

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=32)

    class ThreatLSTM(nn.Module):
        def __init__(self, input_size=9, hidden=64, layers=2):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden, layers, batch_first=True, dropout=0.3)
            self.head  = nn.Sequential(
                nn.Linear(hidden, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 1), nn.Sigmoid()
            )
        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :]).squeeze(1)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ThreatLSTM().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.BCELoss()
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    best_val_loss = float("inf")
    best_state = None
    patience, no_improve = 5, 0

    for epoch in range(30):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            loss = criterion(model(xb), yb)
            optimizer.zero_grad(); loss.backward(); optimizer.step()

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                val_loss += criterion(model(xb), yb).item()

        val_loss /= len(val_loader)
        scheduler.step()
        logger.debug(f"LSTM Epoch {epoch+1}/30 — val_loss: {val_loss:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                logger.info(f"Early stopping at epoch {epoch+1}")
                break

    model.load_state_dict(best_state)

    return {
        "model_state": best_state,
        "model_class": "ThreatLSTM",
        "seq_len": seq_len,
        "val_loss": best_val_loss,
        "trained_at": datetime.utcnow().isoformat(),
    }


# ─── Persistence ──────────────────────────────────────────────────────────────

def save_model(bundle: dict, name: str):
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, f"{name}.pkl")
    with open(path, "wb") as f:
        pickle.dump(bundle, f)

    meta_path = os.path.join(MODEL_DIR, f"{name}_meta.json")
    meta = {k: v for k, v in bundle.items() if k not in ("model", "scaler", "model_state")}
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    logger.success(f"Model saved: {path}")
    return path


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["rf", "lstm", "all"], default="rf")
    parser.add_argument("--hours-back", type=int, default=168)
    parser.add_argument("--synthetic", action="store_true", help="Skip DB, use synthetic data")
    args = parser.parse_args()

    if args.synthetic:
        X, y = _synthetic_training_data(3000)
        logger.info("Using 3000 synthetic samples")
    else:
        logger.info(f"Loading training data from last {args.hours_back}h...")
        X, y = extract_features_from_db(args.hours_back)

    pos_rate = y.mean() if len(y) > 0 else 0
    logger.info(f"Dataset: {len(X)} samples | {pos_rate:.1%} positive (threat)")

    if args.model in ("rf", "all"):
        logger.info("Training Random Forest / Gradient Boosting...")
        rf_bundle = train_random_forest(X, y)
        save_model(rf_bundle, "threat_predictor_rf")

    if args.model in ("lstm", "all"):
        logger.info("Training LSTM...")
        lstm_bundle = train_lstm(X, y)
        if lstm_bundle:
            save_model(lstm_bundle, "threat_predictor_lstm")
