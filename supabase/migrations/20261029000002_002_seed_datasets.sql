-- =============================================================================
-- GeoVerse Model 1: LULC Urban Growth — Seed Datasets
-- Migration: 002_seed_datasets.sql
-- Description: Registers T1 and Gold datasets with explicit training authorization
-- =============================================================================

INSERT INTO datasets (dataset_id, name, description, is_training_allowed, total_samples)
VALUES
    (
        't1',
        'T1 Training and Tuning Dataset',
        'Human-interpreted visual reference dataset for model training, tuning, and internal cross-validation across Pune District (699 samples, 4 epochs).',
        TRUE,
        699
    ),
    (
        'gold',
        'Tier-A Gold Evaluation Benchmark Dataset',
        'Strictly held-out reference evaluation dataset for unbiased scientific reporting (641 samples, 4 epochs). Protected by research-integrity fail-closed guards.',
        FALSE,
        641
    )
ON CONFLICT (dataset_id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_training_allowed = EXCLUDED.is_training_allowed,
    total_samples = EXCLUDED.total_samples,
    updated_at = timezone('utc', now());
