-- =============================================================================
-- GeoVerse Model 1: LULC Urban Growth — Supabase / PostgreSQL Schema Migration
-- Migration: 001_initial_schema.sql
-- Description: Core tables, constraints, foreign keys, indexes, and audit trigger
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- 1. Datasets Table (Dataset Registry & Research Integrity Boundary)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    is_training_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    total_samples INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE datasets IS 'Master registry of reference datasets. Enforces strict training vs evaluation separation.';
COMMENT ON COLUMN datasets.is_training_allowed IS 'Fail-closed guard: TRUE only for training datasets (T1); FALSE for Gold evaluation holdout.';

-- -----------------------------------------------------------------------------
-- 2. Samples Table (Stable 30m Cell Reference Sampling Locations)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS samples (
    id BIGSERIAL PRIMARY KEY,
    dataset_id VARCHAR(32) NOT NULL REFERENCES datasets(dataset_id) ON DELETE RESTRICT,
    anon_id VARCHAR(64) NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    polygon JSONB NOT NULL DEFAULT '[]'::jsonb,
    inside_primary_landsat BOOLEAN NOT NULL DEFAULT TRUE,
    is_double_interpretation BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_samples_dataset_anon UNIQUE (dataset_id, anon_id)
);

CREATE INDEX IF NOT EXISTS idx_samples_dataset_anon ON samples(dataset_id, anon_id);
CREATE INDEX IF NOT EXISTS idx_samples_coords ON samples(lat, lon);
CREATE INDEX IF NOT EXISTS idx_samples_flags ON samples(dataset_id, is_double_interpretation, inside_primary_landsat);

COMMENT ON TABLE samples IS 'Spatial reference sample cells (30m x 30m) across the Pune Metropolitan Region.';
COMMENT ON COLUMN samples.inside_primary_landsat IS 'True if coordinate is within conservative Landsat Path 147 Row 047 4-epoch intersection.';
COMMENT ON COLUMN samples.is_double_interpretation IS 'True if sample is designated for dual independent visual interpretation.';

-- -----------------------------------------------------------------------------
-- 3. Annotations Table (Multi-Epoch Visual Reference Interpretations)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annotations (
    id BIGSERIAL PRIMARY KEY,
    sample_id BIGINT NOT NULL REFERENCES samples(id) ON DELETE RESTRICT,
    dataset_id VARCHAR(32) NOT NULL REFERENCES datasets(dataset_id) ON DELETE RESTRICT,
    anon_id VARCHAR(64) NOT NULL,
    epoch SMALLINT NOT NULL CHECK (epoch IN (1990, 2000, 2010, 2020)),
    status VARCHAR(20) NOT NULL CHECK (status IN ('done', 'unavailable', 'skipped', '')),
    dominant_class VARCHAR(32) CHECK (
        dominant_class IS NULL OR dominant_class IN (
            'built_up', 'agriculture', 'natural_vegetation', 'water', 'bare_sparse',
            'other', 'uncertain', 'ambiguous', 'unavailable'
        )
    ),
    dominant_share_3bins VARCHAR(10) CHECK (
        dominant_share_3bins IS NULL OR dominant_share_3bins IN ('>=75', '50-75', '<50')
    ),
    second_class VARCHAR(32) NOT NULL DEFAULT 'none' CHECK (
        second_class IN (
            'built_up', 'agriculture', 'natural_vegetation', 'water', 'bare_sparse',
            'other', 'none'
        )
    ),
    confidence_1to3 SMALLINT CHECK (
        confidence_1to3 IS NULL OR confidence_1to3 IN (1, 2, 3)
    ),
    imagery_source VARCHAR(32) CHECK (
        imagery_source IS NULL OR imagery_source IN (
            'GEP_historical', 'Landsat_context', 'field', 'Sentinel2_context', 'other_vhr'
        )
    ),
    imagery_date DATE,
    notes TEXT NOT NULL DEFAULT '',
    annotator_id VARCHAR(64) DEFAULT NULL,
    schema_version VARCHAR(16) NOT NULL DEFAULT '1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

    -- Unique constraint per sample and epoch
    CONSTRAINT uq_annotations_dataset_anon_epoch UNIQUE (dataset_id, anon_id, epoch),
    CONSTRAINT uq_annotations_sample_epoch UNIQUE (sample_id, epoch),

    -- Server-side protocol validation rules:
    -- 1. Status done requires dominant_class
    CONSTRAINT chk_status_done_class CHECK (
        status != 'done' OR dominant_class IS NOT NULL
    ),
    -- 2. Unavailable status consistency
    CONSTRAINT chk_status_unavailable CHECK (
        status != 'unavailable' OR dominant_class IS NULL OR dominant_class = 'unavailable'
    ),
    -- 3. Skipped / empty status must not contain a dominant_class
    CONSTRAINT chk_status_skipped CHECK (
        status NOT IN ('skipped', '') OR dominant_class IS NULL
    ),
    -- 4. Mandatory notes for 'other' and 'ambiguous'
    CONSTRAINT chk_notes_mandatory CHECK (
        dominant_class NOT IN ('other', 'ambiguous') OR length(trim(notes)) > 0
    ),
    -- 5. Definite classes require share bin and confidence
    CONSTRAINT chk_definite_share_conf CHECK (
        dominant_class NOT IN ('built_up', 'agriculture', 'natural_vegetation', 'water', 'bare_sparse', 'other')
        OR (dominant_share_3bins IS NOT NULL AND confidence_1to3 IS NOT NULL)
    ),
    -- 6. Status done requires imagery source and date
    CONSTRAINT chk_status_done_imagery CHECK (
        status != 'done' OR (imagery_source IS NOT NULL AND imagery_date IS NOT NULL)
    ),
    -- 7. Landsat context caps confidence at 2
    CONSTRAINT chk_landsat_confidence CHECK (
        imagery_source != 'Landsat_context' OR confidence_1to3 IS NULL OR confidence_1to3 <= 2
    ),
    -- 8. Second class cannot equal dominant class (unless 'none')
    CONSTRAINT chk_second_class_distinct CHECK (
        second_class = 'none' OR second_class != dominant_class
    ),
    -- 9. Imagery date window: +/- 2 calendar years from epoch
    CONSTRAINT chk_date_window CHECK (
        imagery_date IS NULL OR (
            EXTRACT(YEAR FROM imagery_date) >= epoch - 2
            AND EXTRACT(YEAR FROM imagery_date) <= epoch + 2
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_annotations_lookup ON annotations(dataset_id, anon_id, epoch);
CREATE INDEX IF NOT EXISTS idx_annotations_sample ON annotations(sample_id);
CREATE INDEX IF NOT EXISTS idx_annotations_class ON annotations(dominant_class, epoch);
CREATE INDEX IF NOT EXISTS idx_annotations_status ON annotations(status);

COMMENT ON TABLE annotations IS 'Epoch-isolated human and adjudicated reference labels for Model 1.';

-- -----------------------------------------------------------------------------
-- 4. Annotation History Table (Audit Trail)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS annotation_history (
    history_id BIGSERIAL PRIMARY KEY,
    annotation_id BIGINT REFERENCES annotations(id) ON DELETE SET NULL,
    sample_id BIGINT REFERENCES samples(id) ON DELETE SET NULL,
    dataset_id VARCHAR(32) NOT NULL,
    anon_id VARCHAR(64) NOT NULL,
    epoch SMALLINT NOT NULL,
    action VARCHAR(16) NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE', 'MIGRATE')),
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR(64) NOT NULL DEFAULT 'system',
    change_reason TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_history_dataset_anon ON annotation_history(dataset_id, anon_id, epoch);
CREATE INDEX IF NOT EXISTS idx_history_annotation ON annotation_history(annotation_id);
CREATE INDEX IF NOT EXISTS idx_history_created ON annotation_history(created_at);

COMMENT ON TABLE annotation_history IS 'Immutable audit log of all create, update, delete, and migration events.';

-- -----------------------------------------------------------------------------
-- 5. Quality Reviews Table (Inter-Rater Agreement & Adjudication)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_reviews (
    review_id BIGSERIAL PRIMARY KEY,
    sample_id BIGINT NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    dataset_id VARCHAR(32) NOT NULL REFERENCES datasets(dataset_id) ON DELETE RESTRICT,
    anon_id VARCHAR(64) NOT NULL,
    epoch SMALLINT NOT NULL CHECK (epoch IN (1990, 2000, 2010, 2020)),
    interpreter_a_id VARCHAR(64),
    interpreter_a_class VARCHAR(32),
    interpreter_a_confidence SMALLINT,
    interpreter_b_id VARCHAR(64),
    interpreter_b_class VARCHAR(32),
    interpreter_b_confidence SMALLINT,
    is_agreement BOOLEAN,
    agreement_type VARCHAR(32) CHECK (
        agreement_type IS NULL OR agreement_type IN ('exact_match', 'class_dispute', 'confidence_dispute', 'pending_b')
    ),
    adjudicated_class VARCHAR(32) DEFAULT NULL,
    adjudicated_by VARCHAR(64) DEFAULT NULL,
    adjudicated_at TIMESTAMPTZ DEFAULT NULL,
    review_status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (
        review_status IN ('pending', 'agreed', 'disputed', 'adjudicated')
    ),
    reviewer_notes TEXT DEFAULT NULL,
    reviewed_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_quality_reviews_dataset_anon_epoch UNIQUE (dataset_id, anon_id, epoch)
);

CREATE INDEX IF NOT EXISTS idx_quality_reviews_lookup ON quality_reviews(dataset_id, anon_id, epoch);
CREATE INDEX IF NOT EXISTS idx_quality_reviews_status ON quality_reviews(review_status);

COMMENT ON TABLE quality_reviews IS 'Double-interpretation peer review and arbitration records for QC.';

-- -----------------------------------------------------------------------------
-- 6. Automated Timestamp Updates (BEFORE UPDATE Triggers)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = timezone('utc', now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_updated_at_datasets ON datasets;
CREATE TRIGGER trg_set_updated_at_datasets
BEFORE UPDATE ON datasets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_samples ON samples;
CREATE TRIGGER trg_set_updated_at_samples
BEFORE UPDATE ON samples
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_annotations ON annotations;
CREATE TRIGGER trg_set_updated_at_annotations
BEFORE UPDATE ON annotations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_set_updated_at_quality_reviews ON quality_reviews;
CREATE TRIGGER trg_set_updated_at_quality_reviews
BEFORE UPDATE ON quality_reviews
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- -----------------------------------------------------------------------------
-- 7. Automated Audit Trail Trigger Function (SECURITY DEFINER)
-- -----------------------------------------------------------------------------
-- Declared SECURITY DEFINER to permit authorized authenticated annotators to record
-- audit entries without requiring direct write privileges on annotation_history.
CREATE OR REPLACE FUNCTION record_annotation_history()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO annotation_history (
            annotation_id, sample_id, dataset_id, anon_id, epoch,
            action, old_values, new_values, changed_by, change_reason
        ) VALUES (
            NEW.id, NEW.sample_id, NEW.dataset_id, NEW.anon_id, NEW.epoch,
            'INSERT', NULL, to_jsonb(NEW), coalesce(NEW.annotator_id, 'system'), 'Created record'
        );
        RETURN NEW;
    ELSIF (TG_OP = 'UPDATE') THEN
        -- Only record history if significant annotation fields changed
        IF (OLD.dominant_class IS DISTINCT FROM NEW.dominant_class OR
            OLD.dominant_share_3bins IS DISTINCT FROM NEW.dominant_share_3bins OR
            OLD.second_class IS DISTINCT FROM NEW.second_class OR
            OLD.confidence_1to3 IS DISTINCT FROM NEW.confidence_1to3 OR
            OLD.imagery_source IS DISTINCT FROM NEW.imagery_source OR
            OLD.imagery_date IS DISTINCT FROM NEW.imagery_date OR
            OLD.status IS DISTINCT FROM NEW.status OR
            OLD.notes IS DISTINCT FROM NEW.notes) THEN

            INSERT INTO annotation_history (
                annotation_id, sample_id, dataset_id, anon_id, epoch,
                action, old_values, new_values, changed_by, change_reason
            ) VALUES (
                NEW.id, NEW.sample_id, NEW.dataset_id, NEW.anon_id, NEW.epoch,
                'UPDATE', to_jsonb(OLD), to_jsonb(NEW), coalesce(NEW.annotator_id, 'system'), 'Updated record'
            );
        END IF;
        RETURN NEW;
    ELSIF (TG_OP = 'DELETE') THEN
        INSERT INTO annotation_history (
            annotation_id, sample_id, dataset_id, anon_id, epoch,
            action, old_values, new_values, changed_by, change_reason
        ) VALUES (
            OLD.id, OLD.sample_id, OLD.dataset_id, OLD.anon_id, OLD.epoch,
            'DELETE', to_jsonb(OLD), NULL, 'system', 'Deleted record'
        );
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_record_annotation_history ON annotations;
CREATE TRIGGER trg_record_annotation_history
AFTER INSERT OR UPDATE OR DELETE ON annotations
FOR EACH ROW EXECUTE FUNCTION record_annotation_history();
