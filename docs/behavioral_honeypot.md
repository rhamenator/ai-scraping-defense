# Behavioral Honeypot

The behavioral honeypot records traversal patterns of suspicious clients. Each request is logged to Redis (or an in-memory fallback) by `SessionTracker`. A lightweight model can be trained using `train_behavior_model` which currently extracts simple sequence features and fits either XGBoost or a RandomForest classifier.

The collected sequences and labels can be fed back into the detection pipeline to improve accuracy over time.

### Biometric Scope Note

The behavioral honeypot does not use biometric signals. Biometric-capable
authentication is handled via WebAuthn in the Admin UI, and only cryptographic
credential metadata is stored for verification.

### API Sequence Anomaly Detection

`SequenceAnomalyDetector` provides a lightweight Markov-model approach for detecting unusual API request patterns. Train a model with `train_markov_model` and compute anomaly scores on new sequences.
